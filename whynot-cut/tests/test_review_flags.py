# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.13 — `reel review-flags`: the medical/religious review as data the panel can show.

The lead writes the medical-reviewer's findings (a table keyed by the plan's event id, or the motion scene id) with
`reel review-flags --from <file|->`; the engine writes `<item>/review-flags.json` (docs/adobe/eng-data-contract.md
§7.6). `text`, `start_s` and `end_s` always come from the compiled plan, never from the reviewer. Coverage model: the file
stores every reviewed line (`items` flagged, `ok` fine) and a write is refused unless EVERY plan line with on-screen text
is covered, by the new table or by the previous usable file with the same id and the same text; `checked` is computed;
the file is replaced whole and atomically; `load()` serves nothing once the plan changed.
Run:  bash tools/test.sh -p test_review_flags.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib import plan  # noqa: E402
from lib import review_flags as RF  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

CLI = SK / "engine/reel/cli.py"
VID = "C0001"
FLAGS = "review-flags.json"
SPEC_G2_TEXT = "Take 500 mg daily / after food"
AR_G1 = "الملح الكتير بيرفع الضغط"                 # logical order, as the speaker said it
AR_REASON = "الجرعة لازم الدكتورة توافق عليها — ٥٠٠ ملجم"


def env():
    from test_plugin import isolated_env
    return isolated_env()


def make_client(tmp: Path, name: str = "Dr Test د. تجربة") -> Path:
    root = tmp / name                                    # spaces + Arabic in the folder the item lives under
    for d in ("assets/Brand", "data/Raw"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text("{}", encoding="utf-8")
    return root


def event(eid: str, a: int, b: int, **params) -> dict:
    return {"event_id": eid, "decision_id": "D" + eid[1:], "template": "glass_card", "start_ms": a, "end_ms": b,
            "params": params}


def timeline_spec(extra_ms: int = 0) -> dict:
    """G1 and G2 have on-screen text; G3 is a transition without any."""
    g3 = event("G3", 7250, 7350)
    g3["template"] = "flash_transition"
    return {"fps": 30, "duration_frames": 900, "generated": "2026-10-16T09:00:00+00:00", "main_segments": [],
            "events": [event("G1", 1000, 3500, text=AR_G1),
                       event("G2", 4000 + extra_ms, 7250, headline="Take 500 mg daily", items=[{"text": "after food"}]),
                       g3]}


def put_timeline(p: Paths, spec: dict | None = None):
    write_json(p.p("01_analysis/timeline-spec.json"), spec or timeline_spec())


def scene(sid: str, a: int, b: int, *texts: str) -> dict:
    return {"id": sid, "type": "title", "start_frame": a, "end_frame": b,
            "elements": [{"kind": "text", "text": t} for t in texts] + [{"kind": "icon", "icon": "heart"}]}


def put_motion(p: Paths, fps: int = 24, dose: str = "500 mg", scenes: list | None = None):
    from lib import motion_plan
    write_json(p.p("00_inputs/source.json"), {"kind": "motion_reel", "language": "ar"})
    doc = {"reel_id": p.video_id, "fps": fps, "duration_frames": 240, "scenes": scenes or [
        scene("S1", 0, 10, AR_G1),
        {"id": "S2", "type": "stat", "start_frame": 10, "end_frame": 100,
         "elements": [{"kind": "text", "text": "Dose"}, {"kind": "counter", "text": dose}]}],
        "fingerprint": motion_plan.fingerprint(p)}
    write_json(p.p("01_analysis/motion-plan.json"), doc)
    return doc


def table(*rows, **extra) -> dict:
    return dict({"items": [{"event_id": e, "flag": f, "verdict": v, "reason": r} for e, f, v, r in rows]}, **extra)


def full(*rows, ids=("G1", "G2")) -> dict:
    """The rows plus an `ok` row for every other line of the plan: a full review."""
    have = {r[0] for r in rows}
    return table(*rows, *[(i, "medical", "ok", "") for i in ids if i not in have])


def fullm(*rows) -> dict:
    return full(*rows, ids=("S1", "S2"))


def filed(r: dict) -> dict:
    """What write() returned minus `dropped` and `cleared` (the result's own fields): the document on disk."""
    return {k: v for k, v in r.items() if k not in ("dropped", "cleared")}


def other_flag_cases():
    """The 6th review's cases: G2's medical flag (or, for tatweel, a flag on AR_G1) is not carried, its words come back
    split, merged, extended or invisibly changed on a new or changed line, and the table reviews that line only under
    the OTHER flag. Each is (name, first plan + first table or None for the default, new plan, table, ids to name)."""
    g1 = timeline_spec()["events"][0]
    dose, food = dict(headline="Take 500 mg daily"), dict(items=[{"text": "after food"}])
    ok = lambda *ids: [(i, "religious", "ok", "") for i in ids]   # noqa: E731
    return [
        ("split keeping the old id", None, [g1, event("G2", 4000, 5500, **food), event("G6", 5500, 7250, **dose)],
         table(("G2", "medical", "ok", ""), *ok("G6")), "G6"),
        ("split with a new id", None, [g1, event("G5", 4000, 5500, **dose), event("G6", 5500, 7250, **food)],
         table(*ok("G5", "G6")), "G5, G6"),
        ("merge", None, [event("G9", 1000, 7250, text=AR_G1, **dose, **food)], table(*ok("G9")), "G9"),
        ("extension", None, [g1, event("G7", 4000, 7250, **dose, items=[{"text": "after food"}, {"text": "for 3 months"}])],
         table(*ok("G7")), "G7"),
        ("zero-width space plus renumber", None, [g1, event("G7", 4000, 7250, headline="Take 500​ mg daily", **food)],
         table(*ok("G7")), "G7"),
        ("tatweel moved, old id reused",
         ([event("G1", 1000, 3500, text="x"), event("G2", 4000, 7250, text=AR_G1)],
          table(("G1", "medical", "ok", ""), ("G2", "medical", "needs-doctor-approval", "salt"))),
         [event("G1", 1000, 3500, text="x"), event("G2", 4000, 5000, text="intro"),
          event("G3", 5000, 7250, text=AR_G1.replace("الكتير", "الكـتير"))],
         table(("G2", "medical", "ok", ""), *ok("G3")), "G3"),
    ]


def setup_case(p: Paths, first):
    """The first review of an other_flag_cases() case (the default: G2 flagged medical, G1 ok)."""
    if first:
        put_timeline(p, dict(timeline_spec(), events=first[0]))
        RF.write(p, first[1])
    else:
        put_timeline(p)
        RF.write(p, full(("G2", "medical", "needs-doctor-approval", "dose")))


def one_json_document(stdout: str) -> dict:
    """The command's whole stdout is exactly one JSON document."""
    doc = json.loads(stdout)
    assert isinstance(doc, dict), stdout
    return doc


class Base(unittest.TestCase):
    DOMAIN = "religious"        # the client's profile domain: religious clients get both checks (DOMAIN_FLAGS)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t413_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(common.set_context, None)
        self.root = make_client(self.tmp)
        self.p = Paths(self.root, VID)
        self.file = self.p.p(FLAGS)
        if self.DOMAIN:
            self.domain(self.DOMAIN)
        common.set_context(self.root)

    def domain(self, d):
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"domain": d})


class TestWrite(Base):
    def setUp(self):
        super().setUp()
        put_timeline(self.p)

    def test_writes_flag_keyed_by_event_id(self):
        p = self.p
        RF.write(p, {"items": [
            {"event_id": "G2", "flag": "medical", "verdict": "needs-doctor-approval", "reason": "dose"},
            {"event_id": "G1", "flag": "medical", "verdict": "ok", "reason": ""}]})
        doc = read_json(p.p("review-flags.json"))
        self.assertEqual([i["event_id"] for i in doc["items"]], ["G2"])
        self.assertEqual((doc["checked"], doc["lines_total"], doc["items"][0]["text"]), (2, 2, SPEC_G2_TEXT))
        self.assertEqual(doc["plan_fingerprint"], plan.plan_fingerprint(p))
        self.assertEqual((doc["schema"], doc["plan_kind"], doc["by"]), (1, "timeline", "lead"))
        self.assertRegex(doc["written_at"], r"^\d{4}-\d\d-\d\dT")
        it = doc["items"][0]
        self.assertEqual(set(it), {"event_id", "flag", "verdict", "text", "start_s", "end_s", "reason"})
        self.assertEqual((it["flag"], it["verdict"], it["reason"]), ("medical", "needs-doctor-approval", "dose"))
        self.assertEqual((it["start_s"], it["end_s"]), (4.0, 7.25))

    def test_ok_lines_are_stored_with_the_plans_words(self):
        RF.write(self.p, full(("G2", "medical", "remove", "r")))
        self.assertEqual(read_json(self.file)["ok"], [{"event_id": "G1", "text": AR_G1, "flags": MED}])
        RF.write(self.p, full(("G1", "medical", "ok", "")))
        doc = read_json(self.file)
        self.assertEqual((doc["items"], doc["ok"]), ([], [{"event_id": "G1", "text": AR_G1, "flags": MED},
                                                           {"event_id": "G2", "text": SPEC_G2_TEXT, "flags": MED}]))

    def test_checked_is_computed_and_an_input_checked_is_ignored(self):
        for given in (0, 1, 99, -3, "x", None, True):
            with self.subTest(given=given):
                r = RF.write(self.p, dict(full(("G2", "medical", "remove", "r")), checked=given))
                self.assertEqual((r["checked"], r["lines_total"]), (2, 2))

    def test_the_first_write_must_list_every_line(self):
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, table(("G2", "medical", "remove", "r")))
        self.assertIn("G1 has not been reviewed", cm.exception.error)
        self.assertRegex(cm.exception.how, r"`ok` row")
        self.assertFalse(self.file.exists())
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, table())
        self.assertIn("G1, G2 have not been reviewed", cm.exception.error)

    def test_a_graphic_without_on_screen_text_does_not_count(self):
        r = RF.write(self.p, full())
        self.assertEqual((r["checked"], r["lines_total"]), (2, 2))
        self.assertEqual([o["event_id"] for o in read_json(self.file)["ok"]], ["G1", "G2"])
        write_json(self.p.p("01_analysis/timeline-spec.json"),
                   dict(timeline_spec(), events=[timeline_spec()["events"][2]]))           # a plan with no text at all
        r = RF.write(self.p, table())
        self.assertEqual((r["checked"], r["lines_total"], r["items"], r["ok"]), (0, 0, [], []))

    def test_a_row_for_a_graphic_without_text_is_refused(self):
        for verdict in ("ok", "remove"):
            with self.subTest(verdict):
                with self.assertRaises(Guidance) as cm:
                    RF.write(self.p, full(("G3", "medical", verdict, "r")))
                self.assertIn("G3", cm.exception.error)
                self.assertIn("no on-screen text", cm.exception.error)
                self.assertFalse(self.file.exists())

    def test_write_returns_the_document_it_wrote(self):
        r = RF.write(self.p, full(("G2", "religious", "remove", "x"), ("G2", "medical", "ok", "")), by="Yunus")
        self.assertEqual(filed(r), read_json(self.file))
        self.assertEqual((r["by"], r["dropped"], r["cleared"]), ("Yunus", [], []))
        self.assertNotIn("cleared", read_json(self.file))

    def test_text_and_times_come_from_the_plan_never_the_reviewer(self):
        row = {"event_id": "G1", "flag": "medical", "verdict": "reword-to-match", "reason": "r",
               "text": "INVENTED", "start_s": 99.0, "end_s": 100.0}
        RF.write(self.p, {"items": [row, {"event_id": "G2", "flag": "medical", "verdict": "ok"}]})
        it = read_json(self.file)["items"][0]
        self.assertEqual((it["text"], it["start_s"], it["end_s"]), (AR_G1, 1.0, 3.5))

    def test_seconds_have_three_decimals(self):
        spec = timeline_spec()
        spec["events"][0].update(start_ms=1234, end_ms=3456)
        put_timeline(self.p, spec)
        RF.write(self.p, full(("G1", "medical", "remove", "r")))
        it = read_json(self.file)["items"][0]
        self.assertEqual((it["start_s"], it["end_s"]), (1.234, 3.456))

    def test_a_numeric_value_on_screen_is_part_of_the_text(self):
        spec = timeline_spec()
        spec["events"][1]["params"] = {"headline": "Success rate", "value": 70, "items": [{"text": 2.5}]}
        put_timeline(self.p, spec)
        RF.write(self.p, full(("G2", "medical", "remove", "r")))
        self.assertEqual(read_json(self.file)["items"][0]["text"], "Success rate / 70 / 2.5")

    def test_rewrite_replaces_the_file_and_the_new_verdict_wins(self):
        RF.write(self.p, full(("G1", "medical", "remove", "first"), ("G2", "religious", "reword-to-match", "first"),
                              ("G2", "medical", "ok", "")))          # G2 is a dose: its own medical row
        RF.write(self.p, table(("G2", "medical", "needs-doctor-approval", "second")))
        doc = read_json(self.file)
        self.assertEqual([(i["event_id"], i["flag"], i["reason"]) for i in doc["items"]],
                         [("G2", "medical", "second"), ("G1", "medical", "first"), ("G2", "religious", "first")])
        self.assertEqual((doc["checked"], doc["lines_total"]), (2, 2))
        self.assertEqual(list(self.file.parent.glob("review-flags.json.*")), [], "no temp file left behind")

    def test_the_same_graphic_may_carry_both_flags(self):
        RF.write(self.p, full(("G1", "medical", "remove", "a"), ("G1", "religious", "remove", "b")))
        self.assertEqual([i["flag"] for i in read_json(self.file)["items"]], ["medical", "religious"])
        self.assertEqual([o["event_id"] for o in read_json(self.file)["ok"]], ["G2"])


class TestRefusals(Base):
    def setUp(self):
        super().setUp()
        put_timeline(self.p)
        RF.write(self.p, full(("G1", "medical", "remove", "kept")))
        self.before = self.file.read_bytes()

    def refused(self, findings, **kw):
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, findings, **kw)
        self.assertTrue(cm.exception.error and cm.exception.how)
        self.assertEqual(self.file.read_bytes(), self.before, "a refusal writes nothing")
        return cm.exception

    def test_unknown_event_refused_nothing_written(self):
        e = self.refused(full(("G99", "medical", "remove", "r")))
        self.assertIn("G99", e.error)
        self.assertIn("G1", e.how)                       # the ids the plan has

    def test_unknown_event_on_a_fresh_item_leaves_no_file(self):
        self.file.unlink()
        with self.assertRaises(Guidance):
            RF.write(self.p, full(("NOPE", "medical", "remove", "r")))
        self.assertFalse(self.file.exists())

    def test_bad_flag_or_verdict_refused(self):
        for flag, verdict in (("legal", "remove"), ("medical", "approved"), ("", "remove"), ("medical", ""),
                              (None, "remove"), ("Medical", "remove")):
            with self.subTest(flag=flag, verdict=verdict):
                self.refused(full(("G1", flag, verdict, "r")))

    def test_malformed_findings_refused(self):
        for bad in (None, [], "text", {"items": "x"}, {}, {"items": [None]}, {"items": [{"flag": "medical"}]},
                    {"items": [{"event_id": 5, "flag": "medical", "verdict": "remove"}]},
                    {"items": [{"event_id": "G1", "flag": "medical", "verdict": "remove", "reason": 7}]}):
            with self.subTest(bad=bad):
                self.refused(bad)

    def test_the_same_graphic_and_flag_twice_refused(self):
        self.refused(full(("G1", "medical", "remove", "a"), ("G1", "medical", "ok", "")))

    def test_reason_is_capped_at_1024_characters(self):
        RF.write(self.p, full(("G1", "medical", "remove", "ر" * 1024)))
        self.assertEqual(len(read_json(self.file)["items"][0]["reason"]), 1024)
        self.before = self.file.read_bytes()
        e = self.refused(full(("G1", "medical", "remove", "x" * 1025)))
        self.assertIn("1024", e.error)

    def test_no_compiled_plan_refused(self):
        self.p.p("01_analysis/timeline-spec.json").unlink()
        e = self.refused(full(("G1", "medical", "remove", "r")))
        self.assertRegex(e.how, r"reel plan")

    def test_no_compiled_motion_plan_refused(self):
        put_motion(self.p)
        self.p.p("01_analysis/motion-plan.json").unlink()
        e = self.refused(fullm(("S1", "medical", "remove", "r")))
        self.assertRegex(e.how, r"motion-plan")

    def test_a_motion_plan_older_than_its_script_refused(self):
        put_motion(self.p)
        write_json(self.p.p("01_analysis/motion-script.json"), {"scenes": []})        # the script changed, no re-compile
        e = self.refused(fullm(("S1", "medical", "remove", "r")))
        self.assertRegex(e.how, r"motion-plan")


class TestCarry(Base):
    """The coverage model: every plan line with on-screen text must be covered (listed now, or reviewed before with the
    same id and the same words), so a revise sends only the changed lines and nothing slips through renumbered, edited,
    split or merged."""

    def setUp(self):
        super().setUp()
        put_timeline(self.p)
        RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "dose")))      # G2 flagged, G1 ok

    def items(self):
        return {i["event_id"]: i for i in read_json(self.file)["items"]}

    def spec_with(self, *events):
        spec = timeline_spec()
        spec["events"] = list(events)
        put_timeline(self.p, spec)
        self.before = self.file.read_bytes()

    def refused(self, findings):
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, findings)
        self.assertEqual(self.file.read_bytes(), self.before, "a refusal writes nothing")
        return cm.exception

    def test_a_partial_re_review_carries_both_the_flagged_and_the_ok_lines(self):
        self.before = self.file.read_bytes()
        r = RF.write(self.p, table(("G1", "medical", "reword-to-match", "new wording")))        # only G1 re-read
        its = self.items()
        self.assertEqual(set(its), {"G1", "G2"})
        g2 = its["G2"]
        self.assertIs(g2["carried"], True)
        self.assertEqual((g2["flag"], g2["verdict"], g2["reason"], g2["text"], g2["start_s"], g2["end_s"]),
                         ("medical", "needs-doctor-approval", "dose", SPEC_G2_TEXT, 4.0, 7.25))
        self.assertNotIn("carried", its["G1"])
        doc = read_json(self.file)
        self.assertEqual((doc["checked"], doc["lines_total"]), (2, 2))
        self.assertEqual(filed(r), doc)
        self.assertEqual(RF.load(self.p), filed(r))
        r = RF.write(self.p, table(("G2", "medical", "remove", "now remove")))                  # G1 carried as flagged
        self.assertEqual(sorted(self.items()), ["G1", "G2"])
        self.assertIs(self.items()["G1"]["carried"], True)

    def test_an_ok_line_is_carried_as_ok(self):
        r = RF.write(self.p, table(("G2", "medical", "remove", "now remove")))                  # G1 not listed: ok before
        self.assertEqual((r["checked"], r["ok"]), (2, [{"event_id": "G1", "text": AR_G1, "flags": MED}]))
        self.assertEqual(r["dropped"], [])

    def test_carried_even_when_the_old_file_is_stale(self):
        spec = timeline_spec()
        spec["events"][0]["params"] = {"text": AR_G1 + " جدا"}               # the re-plan changed G1 only
        put_timeline(self.p, spec)
        self.assertIsNone(RF.load(self.p))                                    # stale: not served ...
        RF.write(self.p, table(("G1", "medical", "ok", "")))
        self.assertEqual(set(self.items()), {"G2"})                           # ... but its G2 flag still carries
        self.assertIsNotNone(RF.load(self.p))

    def test_a_carried_row_takes_the_plans_current_times(self):
        put_timeline(self.p, timeline_spec(extra_ms=500))                     # G2 moved, same words
        RF.write(self.p, table())
        self.assertEqual((self.items()["G2"]["start_s"], self.items()["G2"]["end_s"]), (4.5, 7.25))

    def test_an_edited_ok_line_not_listed_is_refused(self):
        spec = timeline_spec()
        spec["events"][0]["params"] = {"text": AR_G1 + " جدا"}                # G1 was ok; new words, nobody looked
        put_timeline(self.p, spec)
        self.before = self.file.read_bytes()
        e = self.refused(table())
        self.assertIn("G1 has not been reviewed", e.error)

    def test_a_reworded_flagged_graphic_is_refused_until_listed(self):
        spec = timeline_spec()
        spec["events"][1]["params"]["headline"] = "Take 1000 mg daily"         # the 500 -> 1000 mg case
        put_timeline(self.p, spec)
        self.before = self.file.read_bytes()
        e = self.refused(table(("G1", "medical", "ok", "")))
        self.assertIn("G2 (medical) was flagged", e.error)
        self.assertIn("wording changed", e.error)
        self.assertIn("G2 has not been reviewed", e.error)
        self.assertRegex(e.how, r"`ok` row")
        r = RF.write(self.p, table(("G2", "medical", "ok", "")))                # looked at again: fine
        self.assertEqual((r["items"], r["checked"]), ([], 2))
        r = RF.write(self.p, table(("G2", "medical", "needs-doctor-approval", "1000 mg")))
        (it,) = r["items"]
        self.assertEqual((it["text"], it["reason"], "carried" in it), ("Take 1000 mg daily / after food", "1000 mg", False))

    def test_a_numeric_change_counts_as_rewording(self):
        spec = timeline_spec()
        spec["events"][1]["params"] = {"headline": "Success rate", "value": 70}
        put_timeline(self.p, spec)
        RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "claim")))
        spec["events"][1]["params"]["value"] = 95
        put_timeline(self.p, spec)
        self.before = self.file.read_bytes()
        e = self.refused(table(("G1", "medical", "ok", "")))
        self.assertIn("G2", e.error)

    def test_a_reworded_graphic_named_with_another_flag_is_still_refused(self):
        spec = timeline_spec()
        spec["events"][1]["params"]["headline"] = "Take 1000 mg daily"
        put_timeline(self.p, spec)
        self.before = self.file.read_bytes()
        e = self.refused(table(("G2", "religious", "ok", "")))              # (G2, religious) is not the flagged (G2, medical)
        self.assertIn("G2 (medical) was flagged", e.error)

    def test_the_carry_is_keyed_by_graphic_and_flag(self):
        r = RF.write(self.p, table(("G2", "religious", "remove", "verse")))
        self.assertEqual(sorted((i["event_id"], i["flag"], "carried" in i) for i in r["items"]),
                         [("G2", "medical", True), ("G2", "religious", False)])

    def test_a_new_ok_row_for_the_same_flag_clears_the_carried_flag(self):
        r = RF.write(self.p, table(("G2", "medical", "ok", "")))
        self.assertEqual(r["items"], [])
        self.assertEqual(r["cleared"], [{"event_id": "G2", "from_event_id": "G2", "flag": "medical",
                                         "verdict": "needs-doctor-approval", "text": SPEC_G2_TEXT}])   # told, never silent
        self.assertNotIn("cleared", read_json(self.file))

    def test_a_new_flag_verdict_or_an_ok_on_new_wording_is_not_a_clearance(self):
        r = RF.write(self.p, table(("G2", "medical", "remove", "now remove")))      # re-verdict: still flagged
        self.assertEqual(r["cleared"], [])
        spec = timeline_spec()
        spec["events"][1]["params"]["headline"] = "Take 1000 mg daily"
        put_timeline(self.p, spec)
        r = RF.write(self.p, table(("G2", "medical", "ok", "")))                    # the new words looked at: fine
        self.assertEqual((r["items"], r["cleared"]), ([], []))

    def test_a_carried_reason_over_the_cap_is_cut_not_dropped(self):
        doc = read_json(self.file)
        doc["items"][0]["reason"] = "x" * 3000
        write_json(self.file, doc)
        r = RF.write(self.p, table())
        self.assertEqual([(i["event_id"], len(i["reason"])) for i in r["items"]], [("G2", 1024)])

    def test_renumbered_graphic_wording_moved_to_another_id_is_refused_by_name(self):
        """A graphic was inserted: the dose line is now G3, and G2 is a harmless intro."""
        dose = event("G3", 4000, 7250, headline="Take 500 mg daily", items=[{"text": "after food"}])
        g1, intro = timeline_spec()["events"][0], event("G2", 3500, 4000, text="Welcome")
        self.spec_with(g1, intro, dose)
        e = self.refused(table(("G2", "medical", "ok", "")))
        self.assertIn("G2's flagged wording (medical) is now on G3", e.error)
        self.assertIn("review G3 for medical", e.error)
        self.assertIn("G3 has not been reviewed", e.error)
        r = RF.write(self.p, table(("G2", "medical", "ok", ""), ("G3", "medical", "needs-doctor-approval", "dose")))
        self.assertEqual([(i["event_id"], i["verdict"]) for i in r["items"]], [("G3", "needs-doctor-approval")])
        self.assertEqual((r["checked"], r["lines_total"]), (3, 3))

    def test_a_moved_flag_is_not_covered_by_listing_its_new_line_under_another_flag(self):
        dose = event("G3", 4000, 7250, headline="Take 500 mg daily", items=[{"text": "after food"}])
        self.spec_with(timeline_spec()["events"][0], event("G2", 3500, 4000, text="Welcome"), dose)
        e = self.refused(table(("G2", "medical", "ok", ""), ("G3", "religious", "ok", "")))
        self.assertIn("G2's flagged wording (medical) is now on G3", e.error)
        self.assertIn("review G3 for medical", e.error)
        self.assertNotIn("not been reviewed: list", e.error)        # G3 is listed; its medical check is what is missing
        self.assertIn("G3 has not been reviewed for medical (its words trigger it: 500 mg)", e.error)

    def test_the_fifth_reviews_case_never_loses_the_medical_flag(self):
        """G2 "B" flagged medical; a revise puts "intro" on G2 and "B" on G3; the table sends `G2 medical ok` and
        `G3 religious ok`. Before the fix this wrote items=[] dropped=[]: the medical flag was lost without a word."""
        self.spec_with(event("G2", 1000, 3000, text="B"))
        RF.write(self.p, table(("G2", "medical", "needs-doctor-approval", "dose")))
        self.spec_with(event("G2", 1000, 2000, text="intro"), event("G3", 2000, 3000, text="B"))
        e = self.refused(table(("G2", "medical", "ok", ""), ("G3", "religious", "ok", "")))
        self.assertIn("G2's flagged wording (medical) is now on G3; review G3 for medical", e.error)
        r = RF.write(self.p, table(("G2", "medical", "ok", ""), ("G3", "religious", "ok", ""),
                                   ("G3", "medical", "needs-doctor-approval", "dose")))
        self.assertEqual([(i["event_id"], i["flag"], i["verdict"]) for i in r["items"]],
                         [("G3", "medical", "needs-doctor-approval")])

    def test_a_moved_flag_may_land_on_a_line_already_ok_with_those_words(self):
        """The one exception: a line an earlier review passed as ok with the same id and the same words carries."""
        same = dict(headline="Take 500 mg daily", items=[{"text": "after food"}])
        self.spec_with(event("G1", 1000, 3500, **same), event("G2", 4000, 7250, **same))
        RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "needs-doctor-approval", "dose")))
        self.spec_with(event("G1", 1000, 3500, **same), event("G2", 4000, 7250, text="Welcome"))
        r = RF.write(self.p, table(("G2", "medical", "ok", "")))
        self.assertEqual((r["items"], [o["event_id"] for o in r["ok"]]), ([], ["G1", "G2"]))

    def test_a_moved_flag_may_land_on_a_line_carrying_the_same_flag(self):
        same = dict(headline="Take 500 mg daily", items=[{"text": "after food"}])
        self.spec_with(event("G1", 1000, 3500, **same), event("G2", 4000, 7250, **same))
        RF.write(self.p, table(("G1", "medical", "remove", "a"), ("G2", "medical", "needs-doctor-approval", "b")))
        self.spec_with(event("G1", 1000, 3500, **same), event("G2", 4000, 7250, text="Welcome"))
        r = RF.write(self.p, table(("G2", "medical", "ok", "")))
        self.assertEqual([(i["event_id"], i.get("carried")) for i in r["items"]], [("G1", True)])

    def test_a_graphic_with_a_new_id_and_the_old_one_gone_is_refused_by_name(self):
        spec = timeline_spec()
        spec["events"][1]["event_id"] = "G7"
        put_timeline(self.p, spec)
        self.before = self.file.read_bytes()
        e = self.refused(table(("G1", "medical", "ok", "")))
        self.assertIn("G2's flagged wording (medical) is now on G7", e.error)
        self.assertIn("G7 has not been reviewed", e.error)
        r = RF.write(self.p, table(("G7", "medical", "ok", "")))                # looked at under G7: passed
        self.assertEqual(r["items"], [])
        self.assertEqual(r["cleared"], [{"event_id": "G7", "from_event_id": "G2", "flag": "medical",
                                         "verdict": "needs-doctor-approval", "text": SPEC_G2_TEXT}])
        self.assertEqual(r["dropped"], [])                                       # reported once, as cleared

    def test_a_flag_cleared_on_the_new_id_its_words_moved_to_is_reported(self):
        self.spec_with(timeline_spec()["events"][0], event("G3", 4000, 7250, headline="Take 500 mg daily",
                                                           items=[{"text": "after food"}]))
        r = RF.write(self.p, table(("G3", "medical", "ok", "")))
        self.assertEqual((r["items"], r["dropped"]), ([], []))
        self.assertEqual(r["cleared"], [{"event_id": "G3", "from_event_id": "G2", "flag": "medical",
                                         "verdict": "needs-doctor-approval", "text": SPEC_G2_TEXT}])

    def test_a_flag_cleared_where_its_words_went_is_reported_when_its_old_id_is_reused(self):
        self.spec_with(timeline_spec()["events"][0], event("G2", 4000, 5000, headline="Hello"),
                       event("G7", 5000, 7250, headline="Take 500 mg daily", items=[{"text": "after food"}]))
        r = RF.write(self.p, table(("G2", "medical", "ok", ""), ("G7", "medical", "ok", "")))
        self.assertEqual([(c["event_id"], c["from_event_id"]) for c in r["cleared"]], [("G7", "G2")])
        self.assertEqual(r["dropped"], [])

    def test_a_split_merged_or_extended_flag_reviewed_only_for_the_other_flag_is_refused(self):
        """The 6th review: no text-similarity guess. While an earlier flag is not carried, every new or changed line
        must be reviewed for THAT flag."""
        for name, first, events, findings, ids in other_flag_cases():
            with self.subTest(name):
                setup_case(self.p, first)
                self.spec_with(*events)
                e = self.refused(findings)
                self.assertIn(f"since G2's medical flag: review {ids} for medical", e.error)
                rows = [(i["event_id"], i["flag"], i["verdict"], i["reason"]) for i in findings["items"]]
                rows += [(i, "medical", "ok", "") for i in ids.split(", ")]     # now reviewed for medical too
                r = RF.write(self.p, table(*rows))
                self.assertEqual(r["checked"], r["lines_total"])

    def test_an_exact_copy_of_a_carried_flags_words_must_be_reviewed_for_it(self):
        spec = timeline_spec()
        spec["events"].append(event("G7", 7400, 8000, headline="Take 500 mg daily", items=[{"text": "after food"}]))
        put_timeline(self.p, spec)
        self.before = self.file.read_bytes()
        e = self.refused(table(("G7", "religious", "ok", "")))                    # G2 carried, its copy on G7
        self.assertIn("G2's flagged wording (medical) is now on G7; review G7 for medical", e.error)
        r = RF.write(self.p, table(("G7", "medical", "needs-doctor-approval", "dose")))
        self.assertEqual(sorted((i["event_id"], bool(i.get("carried"))) for i in r["items"]),
                         [("G2", True), ("G7", False)])

    def test_words_removed_but_graphic_kept_is_dropped_without_a_review(self):
        g2 = event("G2", 4000, 7250)
        g2["template"] = "flash_transition"                                       # same id, no words left
        self.spec_with(timeline_spec()["events"][0], g2)
        r = RF.write(self.p, table())
        self.assertEqual((r["items"], r["checked"], r["lines_total"]), ([], 1, 1))
        self.assertEqual([d["event_id"] for d in r["dropped"]], ["G2"])

    def test_words_moved_and_re_flagged_on_a_new_id_are_not_also_dropped(self):
        self.spec_with(timeline_spec()["events"][0], event("G7", 4000, 7250, headline="Take 500 mg daily",
                                                           items=[{"text": "after food"}]))
        r = RF.write(self.p, table(("G7", "medical", "needs-doctor-approval", "dose")))
        self.assertEqual(([i["event_id"] for i in r["items"]], r["dropped"], r["cleared"]), (["G7"], [], []))

    def test_an_unchanged_line_needs_no_re_listing_while_a_flag_is_open(self):
        dose_a = event("G5", 4000, 5500, headline="Take 500 mg daily")
        self.spec_with(timeline_spec()["events"][0], dose_a, event("G6", 5500, 7250, items=[{"text": "after food"}]))
        r = RF.write(self.p, table(("G5", "medical", "needs-doctor-approval", "dose"), ("G6", "medical", "ok", "")))
        self.assertEqual(([i["event_id"] for i in r["items"]], [o["event_id"] for o in r["ok"]]), (["G5"], ["G1", "G6"]))

    def test_a_flag_re_verdicted_in_place_does_not_hold_up_unrelated_new_lines(self):
        spec = timeline_spec()
        spec["events"].append(event("G7", 7400, 8000, text="Subscribe"))
        put_timeline(self.p, spec)
        r = RF.write(self.p, table(("G2", "medical", "remove", "now remove"), ("G7", "religious", "ok", "")))
        self.assertEqual([(i["event_id"], i["verdict"]) for i in r["items"]], [("G2", "remove")])

    def test_edited_and_renumbered_is_refused_naming_the_new_id(self):
        """The 4th review's case: G2 is edited AND renumbered (500 -> 1000 mg, now G5): nothing matches the old words."""
        self.spec_with(timeline_spec()["events"][0], event("G5", 4000, 7250, headline="Take 1000 mg daily"))
        e = self.refused(table(("G1", "medical", "ok", "")))
        self.assertIn("G5 has not been reviewed", e.error)
        r = RF.write(self.p, table(("G5", "medical", "needs-doctor-approval", "1000 mg")))
        self.assertEqual([i["event_id"] for i in r["items"]], ["G5"])
        self.assertEqual([d["event_id"] for d in r["dropped"]], ["G2"])

    def test_a_split_graphic_is_refused_naming_every_new_line(self):
        self.spec_with(timeline_spec()["events"][0], event("G5", 4000, 5500, headline="Take 500 mg"),
                       event("G6", 5500, 7250, headline="daily after food"))
        e = self.refused(table(("G1", "medical", "ok", "")))
        self.assertIn("G5, G6 have not been reviewed", e.error)

    def test_a_half_split_names_only_the_line_left_out(self):
        self.spec_with(timeline_spec()["events"][0], event("G5", 4000, 5500, headline="Take 500 mg"),
                       event("G6", 5500, 7250, headline="daily after food"))
        e = self.refused(table(("G5", "medical", "needs-doctor-approval", "dose")))
        self.assertIn("G6 has not been reviewed", e.error)
        self.assertNotIn("G5 has not", e.error)

    def test_a_merged_graphic_is_refused(self):
        self.spec_with(event("G9", 1000, 7250, text=AR_G1, headline="Take 500 mg daily"))
        e = self.refused(table())
        self.assertIn("G9 has not been reviewed", e.error)

    def test_a_truly_removed_graphic_is_dropped_and_reported(self):
        self.spec_with(timeline_spec()["events"][0])
        r = RF.write(self.p, table())                                           # G1 carried as ok: all covered
        self.assertEqual((r["items"], r["checked"], r["lines_total"]), ([], 1, 1))
        self.assertEqual(r["dropped"], [{"event_id": "G2", "flag": "medical", "verdict": "needs-doctor-approval",
                                         "text": SPEC_G2_TEXT}])
        self.assertNotIn("dropped", read_json(self.file))

    def test_carrying_repeats_across_reviews(self):
        RF.write(self.p, table(("G1", "religious", "remove", "x")))
        RF.write(self.p, table(("G1", "religious", "ok", "")))
        its = self.items()
        self.assertEqual(set(its), {"G2"})
        self.assertIs(its["G2"]["carried"], True)
        self.assertEqual(read_json(self.file)["checked"], 2)

    def test_an_unusable_old_file_needs_a_full_review(self):
        """An old file that exists but cannot be used (bad JSON, another schema, another plan kind, any damaged row) may
        have held flags: nothing is carried, so a partial review is refused and a full one replaces it."""
        good = read_json(self.file)
        foreign = {"schema": 1, "plan_kind": "motion", "items": []}
        damaged_flag = dict(good, items=good["items"] + [{"event_id": "G1", "flag": "legal", "verdict": "remove",
                                                          "text": AR_G1}])
        damaged_ok = dict(good, ok=good["ok"] + ["x"])
        flagged_also_ok = dict(good, ok=good["ok"] + [{"event_id": "G2", "text": SPEC_G2_TEXT}])
        ok_twice = dict(good, ok=good["ok"] * 2)
        for label, content in (("bad json", "{not json"), ("list", "[]"), ("schema 2", '{"schema": 2, "items": []}'),
                               ("no items", '{"schema": 1}'), ("kind", json.dumps(foreign)),
                               ("damaged flag row", json.dumps(damaged_flag)), ("damaged ok row", json.dumps(damaged_ok)),
                               ("a flagged line also ok", json.dumps(flagged_also_ok)),
                               ("an ok line twice", json.dumps(ok_twice)),
                               ("an id with a stray space", json.dumps(dict(good, items=[dict(good["items"][0],
                                                                                             event_id="G2 ")]))),
                               ("ok verdict stored", json.dumps(dict(good, items=[dict(good["items"][0], verdict="ok")])))):
            with self.subTest(label):
                self.file.write_text(content, encoding="utf-8")
                self.before = self.file.read_bytes()
                e = self.refused(table(("G1", "medical", "ok", "")))              # 1 of the plan's 2 lines
                self.assertIn("can't be read", e.error)
                self.assertIn("G2 has not been reviewed", e.error)
                r = RF.write(self.p, full(("G2", "medical", "remove", "full")))
                self.assertEqual([i["event_id"] for i in r["items"]], ["G2"])
                self.assertEqual(r["checked"], 2)

    def test_a_file_from_before_the_ok_list_still_carries_its_flags(self):
        doc = read_json(self.file)
        doc.pop("ok")
        write_json(self.file, doc)
        spec = timeline_spec()
        spec["events"].append(event("G4", 7400, 8000, text="New line"))           # a line no review has seen
        put_timeline(self.p, spec)
        self.before = self.file.read_bytes()
        e = self.refused(table(("G1", "medical", "ok", "")))
        self.assertIn("G4 has not been reviewed", e.error)
        self.assertNotIn("G2", e.error)                                            # G2's flag carries
        e = self.refused(table(("G4", "medical", "ok", "")))
        self.assertIn("G1 has not been reviewed", e.error)                         # no ok list: no ok line carries
        r = RF.write(self.p, table(("G1", "medical", "ok", ""), ("G4", "medical", "ok", "")))
        self.assertEqual(([i["event_id"] for i in r["items"]], r["checked"]), (["G2"], 3))

    def test_motion_scene_flags_carry_by_scene_id(self):
        shutil.rmtree(self.p.project)
        put_motion(self.p)
        RF.write(self.p, fullm(("S2", "medical", "needs-doctor-approval", "dose")))
        RF.write(self.p, table(("S1", "religious", "remove", "verse")))
        its = self.items()
        self.assertEqual(set(its), {"S1", "S2"})
        self.assertIs(its["S2"]["carried"], True)
        self.assertEqual((its["S2"]["text"], its["S2"]["start_s"], its["S2"]["end_s"]), ("Dose / 500 mg", 0.417, 4.167))
        self.assertEqual(read_json(self.file)["checked"], 2)
        put_motion(self.p, dose="250 mg")                                     # re-planned scene: new words
        self.before = self.file.read_bytes()
        e = self.refused(table(("S1", "religious", "remove", "verse")))
        self.assertIn("S2", e.error)
        RF.write(self.p, table(("S1", "religious", "remove", "verse"), ("S2", "medical", "ok", "")))   # looked at again
        self.assertEqual(set(self.items()), {"S1"})

    def test_motion_renumber_split_and_removed_scene(self):
        shutil.rmtree(self.p.project)
        put_motion(self.p)
        RF.write(self.p, fullm(("S2", "medical", "needs-doctor-approval", "dose")))
        dose = {"id": "S3", "type": "stat", "start_frame": 100, "end_frame": 200,
                "elements": [{"kind": "text", "text": "Dose"}, {"kind": "counter", "text": "500 mg"}]}
        put_motion(self.p, scenes=[scene("S1", 0, 10, AR_G1), scene("S2", 10, 100, "Welcome"), dose])
        self.before = self.file.read_bytes()
        e = self.refused(table(("S2", "medical", "ok", "")))
        self.assertIn("S2's flagged wording (medical) is now on S3", e.error)
        r = RF.write(self.p, table(("S2", "medical", "ok", ""), ("S3", "medical", "remove", "dose")))
        self.assertEqual(([i["event_id"] for i in r["items"]], r["checked"], r["lines_total"]), (["S3"], 3, 3))
        put_motion(self.p, scenes=[scene("S1", 0, 10, AR_G1), scene("S4", 10, 50, "Take"), scene("S5", 50, 100, "500 mg")])
        self.before = self.file.read_bytes()                                  # S3 split into S4 + S5 (and S2 gone)
        e = self.refused(table(("S4", "medical", "ok", "")))
        self.assertIn("S5 has not been reviewed", e.error)
        put_motion(self.p, scenes=[scene("S1", 0, 10, AR_G1)])                 # everything but S1 gone for good
        r = RF.write(self.p, table())
        self.assertEqual((r["items"], r["checked"], r["lines_total"]), ([], 1, 1))
        self.assertEqual(sorted(d["event_id"] for d in r["dropped"]), ["S3"])


class TestLoad(Base):
    def setUp(self):
        super().setUp()
        put_timeline(self.p)

    def test_load_serves_the_current_file(self):
        self.assertIsNone(RF.load(self.p))
        r = RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "dose")))
        self.assertEqual(RF.load(self.p), filed(r))

    def test_stale_after_replan(self):
        RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "dose")))
        self.assertIsNotNone(RF.load(self.p))
        put_timeline(self.p, timeline_spec(extra_ms=40))             # the plan moved G2: the old flags are not current
        self.assertIsNone(RF.load(self.p))
        self.assertTrue(self.file.exists(), "load() only reads: the stale file stays for the next write to replace")

    def test_a_recompile_that_changes_nothing_stays_current(self):
        RF.write(self.p, full(("G2", "medical", "remove", "r")))
        spec = timeline_spec()
        spec["generated"] = "2026-10-17T10:00:00+00:00"
        put_timeline(self.p, spec)
        self.assertIsNotNone(RF.load(self.p))

    def test_unreadable_or_foreign_files_load_as_none(self):
        for content in ("", "{not json", "[]", '"x"', '{"schema": 2}', '{"schema": 1}'):
            with self.subTest(content=content):
                self.file.write_text(content, encoding="utf-8")
                self.assertIsNone(RF.load(self.p))
        self.file.write_bytes(b"\xff\xfe\x00bad")
        self.assertIsNone(RF.load(self.p))

    def test_a_hand_edited_or_wiped_file_is_not_served(self):
        good = filed(RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "dose"))))
        g2 = good["items"][0]
        for label, doc in (("an item's verdict set to ok", dict(good, items=[dict(g2, verdict="ok")])),
                           ("items wiped", dict(good, items=[])),
                           ("ok wiped", dict(good, ok=[])),
                           ("checked lowered", dict(good, checked=1)),
                           ("lines_total changed", dict(good, checked=3, lines_total=3)),
                           ("a damaged ok row", dict(good, ok=good["ok"] + ["x"])),
                           ("a bad flag", dict(good, items=[dict(g2, flag="legal")])),
                           ("a flagged line also ok", dict(good, ok=good["ok"] + [{"event_id": "G2", "text": "x"}])),
                           ("no ok list", {k: v for k, v in good.items() if k != "ok"}),
                           ("an item's words edited", dict(good, items=[dict(g2, text="Take 5 mg")])),
                           ("an ok line's words edited", dict(good, ok=[{"event_id": "G1", "text": "zzz"}])),
                           ("an item for an id not in the plan", dict(good, items=[g2, dict(g2, event_id="G99")])),
                           ("an ok row for an id not in the plan", dict(good, ok=good["ok"] + [{"event_id": "G99",
                                                                                                 "text": "q"}])),
                           ("a row for a graphic without text", dict(good, ok=good["ok"] + [{"event_id": "G3",
                                                                                              "text": ""}])),
                           ("checked as a float", dict(good, checked=2.0))):
            with self.subTest(label):
                write_json(self.file, doc)
                self.assertIsNone(RF.load(self.p))
        write_json(self.file, good)
        self.assertEqual(RF.load(self.p), good)

    def test_a_file_of_the_other_plan_kind_is_not_current(self):
        r = RF.write(self.p, full(("G2", "medical", "remove", "r")))
        write_json(self.file, dict(filed(r), plan_kind="motion"))
        self.assertIsNone(RF.load(self.p))

    def test_load_without_any_plan_is_none(self):
        RF.write(self.p, full(("G2", "medical", "remove", "r")))
        self.p.p("01_analysis/timeline-spec.json").unlink()
        self.assertIsNone(RF.load(self.p))


class TestDomain(Base):
    """The file stores the profile domain the review was done for: a line's ok under medical says nothing about a
    religious check, so a domain change makes the earlier file unusable (a full review) and not current."""

    DOMAIN = None                                        # no profile domain: general

    def setUp(self):
        super().setUp()
        put_timeline(self.p)

    def test_each_domain_flags_itself_and_any_registry_flag_is_allowed(self):
        """M1-T2 (was: each domain allows its own flags): DOMAIN_FLAGS comes from the registry, and any registry flag is
        accepted on any line, so a religious row for a medical client is no longer refused."""
        from lib import review_domains as RD
        reg = RD.registry()
        on = {d for d, e in reg.items() if e["always_on"]}
        self.assertEqual(dict(RF.DOMAIN_FLAGS), {d: tuple(sorted({d} | on)) for d in reg})
        for d in ("medical", "general"):
            with self.subTest(d):
                self.domain(d)
                r = RF.write(self.p, table(("G1", "religious", "ok", ""), ("G1", "medical", "ok", ""),
                                           ("G2", "medical", "ok", "")))
                self.assertEqual((r["domain"], r["checked"]), ("ai+medical", 2))
        self.domain("religious")
        r = RF.write(self.p, table(("G1", "religious", "ok", ""), ("G2", "medical", "remove", "r")))
        self.assertEqual(r["checked"], 2)

    def test_a_new_domain_is_one_registry_entry(self):
        """M1-T2 (was: one new DOMAIN_FLAGS entry): a fifth registry domain is a flag with no code change."""
        from unittest import mock
        from lib import review_domains as RD
        f = SK / "tests" / "fixtures" / "review_domains" / "fifth"
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"review_domains": ["legal"]})
        with mock.patch.multiple(RD, REGISTRY_DIR=f / "registry", REFERENCES_DIR=f / "references",
                                 EVALS_DIR=f / "evals"):
            self.assertEqual(RF.DOMAIN_FLAGS["legal"], ("ai", "legal", "medical"))
            r = RF.write(self.p, table(("G1", "legal", "remove", "claim"), ("G1", "medical", "ok", ""),
                                       ("G2", "medical", "ok", ""), ("G2", "legal", "ok", "")))
            self.assertEqual([(i["event_id"], i["flag"]) for i in r["items"]], [("G1", "legal")])
            self.assertEqual(r["domain"], "ai+legal+medical")
            with self.assertRaises(Guidance) as cm:
                RF.write(self.p, table(("G1", "business", "remove", "x"), ("G2", "medical", "ok", "")))
            self.assertIn("business", cm.exception.error)            # not a domain of this registry

    def test_the_file_stores_the_domain_it_was_reviewed_for(self):
        RF.write(self.p, full(("G2", "medical", "remove", "r")))
        self.assertEqual(read_json(self.file)["domain"], "ai+medical")          # M1-T2: no profile domain: ai+medical
        self.domain("medical")
        RF.write(self.p, full(("G2", "medical", "remove", "r")))
        self.assertEqual(read_json(self.file)["domain"], "ai+medical")          # legacy medical: the same key

    def test_a_domain_change_needs_a_full_review_and_is_not_current(self):
        self.domain("medical")
        RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "dose")))
        self.assertIsNotNone(RF.load(self.p))
        self.domain("religious")
        self.assertIsNone(RF.load(self.p))                                       # never served for the new domain
        before = self.file.read_bytes()
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, table(("G1", "religious", "ok", "")))
        self.assertIn("G2 has not been reviewed", cm.exception.error)
        self.assertIn("medical", cm.exception.error)
        self.assertIn("religious", cm.exception.error)
        self.assertEqual(self.file.read_bytes(), before)
        r = RF.write(self.p, table(("G1", "religious", "ok", ""), ("G2", "religious", "ok", ""), ("G2", "medical", "ok", "")))
        self.assertEqual((r["items"], r["checked"], r["domain"]), ([], 2, "ai+medical+religious"))

    def test_a_file_without_a_domain_carries_nothing(self):
        RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "dose")))
        doc = read_json(self.file)
        doc.pop("domain")
        write_json(self.file, doc)
        self.assertIsNone(RF.load(self.p))
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, table(("G1", "medical", "ok", "")))
        self.assertIn("G2 has not been reviewed", cm.exception.error)


class TestMotion(Base):
    def setUp(self):
        super().setUp()
        self.motion = put_motion(self.p, fps=24)

    def test_motion_item_uses_scene_ids(self):
        r = RF.write(self.p, fullm(("S2", "medical", "needs-doctor-approval", "dose"), ("S1", "religious", "ok", "")))
        doc = read_json(self.file)
        self.assertEqual((doc["plan_kind"], doc["checked"], doc["lines_total"]), ("motion", 2, 2))
        self.assertEqual(filed(r), doc)
        from lib import motion_plan
        self.assertEqual(doc["plan_fingerprint"], motion_plan.fingerprint(self.p))
        (it,) = doc["items"]
        self.assertEqual((it["event_id"], it["text"]), ("S2", "Dose / 500 mg"))
        self.assertEqual((it["start_s"], it["end_s"]), (0.417, 4.167))          # frames 10 and 100 at 24 fps
        self.assertEqual(doc["ok"], [{"event_id": "S1", "text": AR_G1, "flags": ["religious"]}])

    def test_a_scene_the_plan_does_not_have_is_refused(self):
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, table(("G1", "medical", "remove", "r")))              # a clip event id on a motion video
        self.assertIn("S1", cm.exception.how)
        self.assertFalse(self.file.exists())

    def test_arabic_scene_text_is_logical_order(self):
        RF.write(self.p, fullm(("S1", "medical", "reword-to-match", AR_REASON)))
        it = json.loads(self.file.read_text(encoding="utf-8"))["items"][0]
        self.assertEqual((it["text"], it["reason"]), (AR_G1, AR_REASON))

    def test_motion_flags_go_stale_when_the_script_changes(self):
        RF.write(self.p, fullm(("S1", "medical", "remove", "r")))
        self.assertIsNotNone(RF.load(self.p))
        write_json(self.p.p("01_analysis/motion-script.json"), {"scenes": [{"id": "S1"}]})
        self.assertIsNone(RF.load(self.p))


class TestCli(Base):
    def setUp(self):
        super().setUp()
        put_timeline(self.p)

    def reel(self, *argv, stdin: bytes | None = None, root=None):
        cmd = [sys.executable, "-B", str(CLI), "--root", str(root or self.root), "--video-id", VID, *argv]
        e = {k: v for k, v in env().items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}    # prove the bytes path:
        r = subprocess.run(cmd, input=stdin, capture_output=True, env=e)                        # no UTF-8 mode to lean on
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")

    def send(self, body: dict):
        return self.reel("review-flags", "--from", "-", stdin=json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def test_classified_as_a_writer_and_listed(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("reel_cli_t413", CLI)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertIn("review-flags", m.CORE_WRITES)
        self.assertIn("review-flags", m.command_table())
        self.assertIn("review-flags", m.registered_commands())
        self.assertTrue(callable(m.cmd_review_flags))

    def test_stdin_and_arabic_roundtrip(self):
        code, out, err = self.send(full(("G1", "medical", "needs-doctor-approval", AR_REASON)))
        self.assertEqual(code, 0, out + err)
        doc = one_json_document(out)
        self.assertTrue(doc["ok"])
        self.assertEqual((doc["checked"], doc["lines_total"], doc["flagged"], doc["carried"], doc["plan_kind"]),
                         (2, 2, 1, 0, "timeline"))
        raw = self.file.read_bytes().decode("utf-8")
        self.assertIn(AR_REASON, raw)                    # not \u-escaped, not mangled: logical-order UTF-8
        self.assertIn(AR_G1, raw)
        it = json.loads(raw)["items"][0]
        self.assertEqual((it["reason"], it["text"]), (AR_REASON, AR_G1))
        self.assertIn("د. تجربة", str(self.file))        # the item folder had spaces and Arabic in its path

    def test_from_a_file_with_a_bom_and_an_arabic_name(self):
        f = self.tmp / "findings قيم.json"
        f.write_bytes(b"\xef\xbb\xbf" + json.dumps(full(("G2", "religious", "remove", AR_REASON), ("G2", "medical", "ok", "")),
                                                  ensure_ascii=False).encode("utf-8"))
        code, out, err = self.reel("review-flags", "--from", str(f))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(read_json(self.file)["items"][0]["reason"], AR_REASON)

    def test_refusals_exit_1_with_one_json_document_and_write_nothing(self):
        cases = {
            "unknown id": full(("G99", "medical", "remove", "r")),
            "bad flag": full(("G1", "legal", "remove", "r")),
            "bad verdict": full(("G1", "medical", "approved", "r")),
            "a line not reviewed": table(("G1", "medical", "ok", "")),
        }
        for name, body in cases.items():
            with self.subTest(name):
                code, out, err = self.send(body)
                self.assertEqual(code, 1, out + err)
                doc = one_json_document(out)
                self.assertIs(doc["ok"], False)
                self.assertTrue(doc["error"] and doc["how"])
                self.assertNotIn("Traceback", out + err)
                self.assertFalse(self.file.exists())

    def test_bad_input_is_guidance_not_a_traceback(self):
        for name, stdin in (("empty", b""), ("not json", b"{nope"), ("a list", b"[1]")):
            with self.subTest(name):
                code, out, err = self.reel("review-flags", "--from", "-", stdin=stdin)
                self.assertEqual(code, 1, out + err)
                doc = one_json_document(out)
                self.assertIs(doc["ok"], False)
                self.assertTrue(doc["how"])
                self.assertNotIn("Traceback", out + err)
        code, out, err = self.reel("review-flags", "--from", str(self.tmp / "missing.json"))
        self.assertEqual(code, 1, out + err)
        self.assertIs(one_json_document(out)["ok"], False)
        self.assertFalse(self.file.exists())

    def test_the_cli_carries_earlier_flags_and_says_so(self):
        self.assertEqual(self.send(full(("G2", "medical", "needs-doctor-approval", "dose")))[0], 0)
        code, out, err = self.send(table(("G1", "medical", "ok", "")))
        self.assertEqual(code, 0, out + err)
        doc = one_json_document(out)
        self.assertEqual((doc["checked"], doc["lines_total"], doc["flagged"], doc["carried"]), (2, 2, 1, 1))
        self.assertEqual(doc["cleared"], [])
        self.assertEqual([i["event_id"] for i in read_json(self.file)["items"]], ["G2"])

    def test_the_cli_tells_the_editor_a_flag_was_cleared(self):
        self.assertEqual(self.send(full(("G2", "medical", "needs-doctor-approval", "dose")))[0], 0)
        code, out, err = self.send(table(("G2", "medical", "ok", "")))
        self.assertEqual(code, 0, out + err)
        doc = one_json_document(out)
        self.assertEqual((doc["flagged"], doc["cleared"]), (0, [{"event_id": "G2", "from_event_id": "G2",
                                                                 "flag": "medical", "verdict": "needs-doctor-approval",
                                                                 "text": SPEC_G2_TEXT}]))

    def test_a_verdict_its_flag_does_not_have_exits_1(self):
        """M1-T2 (was: a flag the client's domain does not check exits 1): any registry flag is allowed now; a verdict
        outside its own flag's list is what is refused."""
        self.domain("medical")
        code, out, err = self.send(table(("G1", "religious", "needs-doctor-approval", "x"), ("G2", "medical", "ok", "")))
        self.assertEqual(code, 1, out + err)
        self.assertIn("not a verdict of the religious check", one_json_document(out)["error"])
        self.assertFalse(self.file.exists())

    def test_other_flag_reviews_of_a_split_merged_or_extended_flag_exit_1_and_write_nothing(self):
        for name, first, events, findings, ids in other_flag_cases():
            with self.subTest(name):
                setup_case(self.p, first)
                put_timeline(self.p, dict(timeline_spec(), events=events))
                before = self.file.read_bytes()
                code, out, err = self.send(findings)
                self.assertEqual(code, 1, out + err)
                self.assertIn(f"review {ids} for medical", one_json_document(out)["error"])
                self.assertEqual(self.file.read_bytes(), before)

    def test_a_reworded_flagged_graphic_exits_1_and_writes_nothing(self):
        self.assertEqual(self.send(full(("G2", "medical", "needs-doctor-approval", "dose")))[0], 0)
        before = self.file.read_bytes()
        spec = timeline_spec()
        spec["events"][1]["params"]["headline"] = "Take 1000 mg daily"
        put_timeline(self.p, spec)
        code, out, err = self.send(table(("G1", "medical", "ok", "")))
        self.assertEqual(code, 1, out + err)
        doc = one_json_document(out)
        self.assertIs(doc["ok"], False)
        self.assertIn("G2", doc["error"])
        self.assertEqual(self.file.read_bytes(), before)

    def test_the_cli_reports_dropped_and_refuses_a_line_nobody_reviewed(self):
        self.assertEqual(self.send(full(("G2", "medical", "needs-doctor-approval", "dose")))[0], 0)
        spec = timeline_spec()
        spec["events"][1]["event_id"] = "G7"
        put_timeline(self.p, spec)
        before = self.file.read_bytes()
        code, out, err = self.send(table(("G1", "medical", "ok", "")))
        self.assertEqual(code, 1, out + err)
        self.assertIn("G7", one_json_document(out)["error"])
        self.assertEqual(self.file.read_bytes(), before)
        code, out, err = self.send(table(("G7", "medical", "ok", "")))
        self.assertEqual(code, 0, out + err)
        doc = one_json_document(out)
        self.assertEqual(([d["event_id"] for d in doc["dropped"]], [(c["event_id"], c["from_event_id"]) for c in
                                                                     doc["cleared"]]), ([], [("G7", "G2")]))
        self.assertEqual((doc["flagged"], doc["lines_total"], doc["checked"]), (0, 2, 2))
        put_timeline(self.p, timeline_spec())                                    # a flag whose id goes for good: dropped
        self.assertEqual(self.send(full(("G2", "medical", "needs-doctor-approval", "dose")))[0], 0)
        put_timeline(self.p, dict(timeline_spec(), events=timeline_spec()["events"][:1]))
        code, out, err = self.send(table())
        self.assertEqual(code, 0, out + err)
        self.assertEqual([d["event_id"] for d in one_json_document(out)["dropped"]], ["G2"])

    def test_an_empty_table_exits_1_when_the_plan_has_text(self):
        code, out, err = self.reel("review-flags", "--from", "-", stdin=b'{"items": []}')
        self.assertEqual(code, 1, out + err)
        self.assertIn("not been reviewed", one_json_document(out)["error"])
        self.assertFalse(self.file.exists())

    def test_from_is_required(self):
        code, out, err = self.reel("review-flags")
        self.assertEqual(code, 2, out + err)             # argparse: a usage error, nothing written
        self.assertFalse(self.file.exists())

    def test_no_compiled_plan_exits_1(self):
        self.p.p("01_analysis/timeline-spec.json").unlink()
        code, out, err = self.send(full(("G1", "medical", "ok", "")))
        self.assertEqual(code, 1, out + err)
        self.assertRegex(one_json_document(out)["how"], r"reel plan")
        self.assertFalse(self.file.exists())

    def test_motion_through_the_cli(self):
        self.p.p("01_analysis/timeline-spec.json").unlink()
        put_motion(self.p)
        code, out, err = self.send(fullm(("S2", "medical", "remove", "r")))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(one_json_document(out)["plan_kind"], "motion")
        self.assertEqual(read_json(self.file)["items"][0]["event_id"], "S2")


# ---------------------------------------------------------------------------------------------- M1-T2 (Task 51)
BIZ = "الكشف بس بـ ٥٠٠ جنيه"                     # a price: the business lexicon detects it
MED = ["medical"]                                # what a general client's ok row clears (the always-on ai is implied)


def biz_spec(text: str = BIZ, **params) -> dict:
    """The default plan plus G4, a line with a price on it."""
    spec = timeline_spec()
    spec["events"].append(event("G4", 7400, 8600, text=text, **params))
    return spec


def registry() -> dict:
    from lib import review_domains as RD
    return RD.registry()


class TestM1Domains(Base):
    """Addendum M1-T2: the review key is the client set (`ai+business+medical`), any registry flag is allowed on any
    line, every line is covered for the key and for the domains its words trigger (review_detect: review), a medical or
    religious row covers only the T4.13 checks and the always-on ai (never business, never a triggered ai), ok rows
    record the flags they cleared, and every verdict belongs to its own flag's registry list."""

    DOMAIN = None

    def setUp(self):
        super().setUp()
        put_timeline(self.p)

    def prof(self, **kw):
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", kw)

    def refused(self, findings):
        before = self.file.read_bytes() if self.file.exists() else None
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, findings)
        self.assertEqual(self.file.read_bytes() if self.file.exists() else None, before, "a refusal writes nothing")
        return cm.exception

    def ok_flags(self) -> dict:
        return {o["event_id"]: o.get("flags") for o in read_json(self.file)["ok"]}

    def test_every_registry_flag_is_accepted_on_any_line_whatever_review_detect(self):
        for mode in ("review", "suggest", "off"):
            for doms, key in (([], "ai+medical"), (["religious"], "ai+medical+religious"),
                              (["business"], "ai+business+medical")):
                own = ["medical"] + (["business"] if "business" in doms else [])     # rows each line needs
                for flag, entry in registry().items():
                    verdict = [v for v in entry["verdicts"] if v != "ok"][0]
                    with self.subTest(mode=mode, key=key, flag=flag):
                        self.file.unlink(missing_ok=True)
                        self.prof(review_domains=doms, review_detect=mode)
                        rows = [("G1", flag, verdict, "r")] + [("G1", k, "ok", "") for k in own if k != flag]
                        r = RF.write(self.p, table(*rows, *[("G2", k, "ok", "") for k in own]))
                        self.assertEqual((r["domain"], [(i["event_id"], i["flag"]) for i in r["items"]]),
                                         (key, [("G1", flag)]))
                        self.assertNotIn(flag, self.ok_flags().get("G1") or [])
                        self.assertEqual(RF.load(self.p), filed(r))

    def test_a_line_flagged_business_with_an_ok_row_for_medical(self):
        r = RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "business", "needs-evidence", "price"),
                                   ("G2", "medical", "ok", "")))
        self.assertEqual([(i["event_id"], i["flag"]) for i in r["items"]], [("G2", "business")])
        self.assertEqual(self.ok_flags(), {"G1": MED, "G2": MED})
        self.assertEqual(RF.load(self.p), filed(r))
        c = RF.counts(RF.load(self.p))
        self.assertEqual((c["business"], c["medical"], c["ai"]),
                         ({"reviewed": 1, "ok": 0, "flagged": 1}, {"reviewed": 2, "ok": 2, "flagged": 0},
                          {"reviewed": 2, "ok": 2, "flagged": 0}))

    def test_an_ok_row_whose_flags_overlap_its_lines_flag_is_damaged(self):
        good = filed(RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "business", "needs-evidence", "p"),
                                            ("G2", "medical", "ok", ""))))
        ok = {o["event_id"]: o for o in good["ok"]}
        write_json(self.file, dict(good, ok=[ok["G1"], dict(ok["G2"], flags=["business", "medical"])]))
        self.assertIsNone(RF.load(self.p))
        e = self.refused(table(("G1", "medical", "ok", "")))
        self.assertIn("can't be read", e.error)
        self.file.unlink()
        good2 = filed(RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "remove", "dose"))))
        old_style = dict(good2, ok=good2["ok"] + [{"event_id": "G2", "text": SPEC_G2_TEXT}])     # no flags = the key
        write_json(self.file, old_style)
        self.assertIsNone(RF.load(self.p))

    def test_ok_flags_must_be_distinct_registry_flags(self):
        good = filed(RF.write(self.p, full()))
        g1 = good["ok"][0]
        for bad in (["medical", "medical"], ["legal"], [], "medical", [1], ["Medical"], None, ["ai", None]):
            with self.subTest(bad=bad):
                write_json(self.file, dict(good, ok=[dict(g1, flags=bad)] + good["ok"][1:]))
                self.assertIsNone(RF.load(self.p))
                e = self.refused(table(("G1", "medical", "ok", "")))
                self.assertIn("can't be read", e.error)

    def test_trimmed_ok_flags_are_not_served(self):
        good = filed(RF.write(self.p, full()))
        write_json(self.file, dict(good, ok=[dict(o, flags=["ai"]) for o in good["ok"]]))   # medical gone from ok
        self.assertIsNone(RF.load(self.p))

    def test_wiped_items_are_never_served_as_an_all_clear(self):
        """A flag under a key flag next to a passed business check, and a business flag on a line its words trigger,
        next to a medical ok: wiping `items` must leave the file unserved (review round 1, findings 2 and 3)."""
        put_timeline(self.p, biz_spec())
        for name, rows in (("medical flag + business ok", (("G4", "medical", "needs-doctor-approval", "dose"),
                                                           ("G4", "business", "ok", ""))),
                           ("business flag + medical ok", (("G4", "business", "needs-evidence", "price"),
                                                           ("G4", "medical", "ok", "")))):
            with self.subTest(name):
                self.file.unlink(missing_ok=True)
                good = filed(RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "ok", ""), *rows)))
                self.assertEqual(RF.load(self.p), good)
                write_json(self.file, dict(good, items=[]))
                self.assertIsNone(RF.load(self.p))

    def test_an_ai_row_never_stands_in_for_the_medical_check(self):
        """Review round 1, finding 1: ai is in every key, but only a medical (or a religious client's religious) row
        covers medical."""
        for rows in ((("G2", "ai", "ok", ""),), (("G2", "ai", "needs-disclosure", "x"),),
                     (("G2", "religious", "ok", ""),), (("G2", "business", "ok", ""),)):
            with self.subTest(rows=rows):
                e = self.refused(table(("G1", "medical", "ok", ""), *rows))
                self.assertIn("G2 has not been reviewed for", e.error)
                self.assertIn("medical", e.error)
                self.assertFalse(self.file.exists())
        r = RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "ai", "needs-disclosure", "x"),
                                   ("G2", "medical", "ok", "")))
        self.assertEqual(self.ok_flags(), {"G1": MED, "G2": MED})
        self.assertEqual(RF.counts(filed(r))["medical"], {"reviewed": 2, "ok": 2, "flagged": 0})

    def test_a_business_client_needs_a_business_row_on_every_line(self):
        self.prof(review_domains=["business"])
        e = self.refused(full())
        self.assertIn("G1 has not been reviewed for business", e.error)
        self.assertIn("G2 has not been reviewed for business", e.error)
        e = self.refused(table(("G1", "business", "ok", ""), ("G2", "business", "ok", "")))
        self.assertIn("medical", e.error)                       # and a business row never covers medical either
        RF.write(self.p, table(("G1", "business", "ok", ""), ("G2", "business", "ok", ""), ("G1", "medical", "ok", ""),
                               ("G2", "medical", "ok", "")))
        self.assertEqual(self.ok_flags(), {"G1": ["business", "medical"], "G2": ["business", "medical"]})

    def test_an_ai_asset_added_to_a_carried_line_asks_for_its_own_ai_row(self):
        put_timeline(self.p, biz_spec(text="صورة توضيحية"))
        RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "ok", ""), ("G4", "medical", "ok", "")))
        self.assertEqual(self.ok_flags()["G4"], MED)
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [{"rel": "data/Broll/gen.png",
                                                                          "ai_generated": True}]})
        put_timeline(self.p, biz_spec(text="صورة توضيحية", image="data/Broll/gen.png"))    # same words, AI image
        self.assertIsNone(RF.load(self.p))
        e = self.refused(table())
        self.assertIn("G4 has not been reviewed for ai (its words trigger it: data/Broll/gen.png)", e.error)
        self.assertNotIn("G1", e.error)
        RF.write(self.p, table(("G4", "ai", "needs-disclosure", "label it")))
        self.assertEqual([(i["event_id"], i["flag"]) for i in read_json(self.file)["items"]], [("G4", "ai")])
        self.assertEqual(self.ok_flags()["G4"], MED)
        self.assertIsNotNone(RF.load(self.p))

    def test_a_damaged_manifest_refuses_cleanly(self):
        """Review round 1, finding 5: a detection crash is a Guidance naming the cause, and nothing is written."""
        RF.write(self.p, full())
        write_json(self.p.client_db / "asset-manifest.json", ["not", "an", "object"])
        e = self.refused(full())
        self.assertIn("review-domain detection could not run", e.error)
        self.assertIsNone(RF.load(self.p))

    def test_a_carried_ok_row_does_not_cover_a_newly_detected_business_line(self):
        put_timeline(self.p, biz_spec())
        self.prof(review_detect="off")
        RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "ok", ""), ("G4", "medical", "ok", "")))
        self.assertEqual(self.ok_flags()["G4"], MED)
        self.prof(review_detect="review")                      # detection now finds the price on G4
        self.assertIsNone(RF.load(self.p))                     # not a complete review for what the line needs now
        e = self.refused(table())
        self.assertIn("G4 has not been reviewed for business", e.error)
        self.assertNotIn("G1", e.error)                        # no full re-review: only that line, for that flag
        self.assertNotIn("G2", e.error)
        e = self.refused(table(("G4", "medical", "ok", "")))   # a medical row does not stand in for a detected flag
        self.assertIn("G4", e.error)
        r = RF.write(self.p, table(("G4", "business", "ok", "")))
        self.assertEqual(self.ok_flags(), {"G1": MED, "G2": MED, "G4": ["business", "medical"]})
        self.assertEqual(r["checked"], 3)
        RF.write(self.p, table())                              # carried with its business flag: covered now
        self.assertEqual(self.ok_flags()["G4"], ["business", "medical"])

    def test_detected_flags_are_required_only_under_review(self):
        put_timeline(self.p, biz_spec())
        three = (("G1", "medical", "ok", ""), ("G2", "medical", "ok", ""), ("G4", "medical", "ok", ""))
        for mode in ("suggest", "off"):
            with self.subTest(mode):
                self.file.unlink(missing_ok=True)
                self.prof(review_detect=mode)
                RF.write(self.p, table(*three))
                self.assertEqual(self.ok_flags()["G4"], MED)
                self.assertIsNotNone(RF.load(self.p))
        self.file.unlink()
        self.prof()                                            # review is the default
        e = self.refused(table(*three))
        self.assertIn("G4 has not been reviewed for business (its words trigger it: ", e.error)
        self.assertFalse(self.file.exists())
        RF.write(self.p, table(*three, ("G4", "business", "needs-approval", "price as spoken?")))
        self.assertEqual(self.ok_flags()["G4"], MED)
        self.assertEqual([(i["event_id"], i["flag"]) for i in read_json(self.file)["items"]], [("G4", "business")])

    def test_an_old_file_whose_ok_rows_have_no_flags_loads_as_the_key(self):
        r = filed(RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "dose"))))
        old = dict(r, ok=[{"event_id": o["event_id"], "text": o["text"]} for o in r["ok"]])
        write_json(self.file, old)
        self.assertEqual(RF.load(self.p), old)
        c = RF.counts(old)
        self.assertEqual((c["ai"], c["medical"]), ({"reviewed": 2, "ok": 2, "flagged": 0},       # G2's medical row:
                                                   {"reviewed": 2, "ok": 1, "flagged": 1}))      # the key reviewed
        RF.write(self.p, table())                              # G1's old ok row is carried as the key's flags
        self.assertEqual(self.ok_flags(), {"G1": MED})          # its key-implied ai stays implied, never written
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [{"rel": "data/Broll/gen.png",
                                                                          "ai_generated": True}]})
        write_json(self.file, old)                             # again the older file, now with an AI image on G1
        spec = timeline_spec()
        spec["events"][0]["params"]["image"] = "data/Broll/gen.png"
        put_timeline(self.p, spec)
        e = self.refused(table(("G2", "medical", "remove", "r")))
        self.assertIn("G1 has not been reviewed for ai", e.error)   # review round 2, finding 3
        self.file.unlink()                                     # load() reads a flagless row the same way (round 3)
        self.prof(review_detect="off")
        r = filed(RF.write(self.p, full()))
        write_json(self.file, dict(r, ok=[{"event_id": o["event_id"], "text": o["text"]} for o in r["ok"]]))
        self.prof(review_detect="review")
        self.assertIsNone(RF.load(self.p))

    def test_a_lexicon_update_that_drops_a_detection_never_invalidates_a_stored_row(self):
        from unittest import mock
        from lib import review_domains as RD
        put_timeline(self.p, biz_spec())
        r = filed(RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "ok", ""),
                                         ("G4", "medical", "ok", ""), ("G4", "business", "needs-evidence", "p"))))
        real = RD.matchers
        with mock.patch.object(RD, "matchers", lambda: [m for m in real() if m[0] != "business"]):
            self.assertEqual(RF.load(self.p), r)                # the shipped lexicon no longer detects G4
            w = RF.write(self.p, table())
            self.assertEqual([(i["event_id"], i["flag"], i.get("carried")) for i in w["items"]],
                             [("G4", "business", True)])

    def test_a_composite_key_accepts_business_and_ai_rows(self):
        self.prof(review_domains=[" Business", "business", "MEDICAL"])
        r = RF.write(self.p, table(("G1", "business", "needs-approval", "a"), ("G1", "ai", "needs-disclosure", "b"),
                                   ("G1", "medical", "ok", ""), ("G2", "medical", "ok", ""), ("G2", "business", "ok", "")))
        self.assertEqual(r["domain"], "ai+business+medical")
        self.assertEqual(self.ok_flags(), {"G1": ["medical"], "G2": ["business", "medical"]})
        self.assertEqual(RF.load(self.p), filed(r))

    def test_an_unknown_key_part_is_refused_never_mapped_to_general(self):
        RF.write(self.p, full())
        self.prof(review_domains=["legal"])
        e = self.refused(full())
        self.assertIn("legal", e.error)
        self.assertIsNone(RF.load(self.p))
        for key, named in (("ai+legal+medical", "legal"), ("general", "general"), ("legal", "legal")):
            with self.subTest(key), self.assertRaises(Guidance) as cm:
                RF._allowed(key)
            self.assertIn(named, cm.exception.error)

    def test_a_general_clients_dose_line_still_needs_a_medical_row(self):
        e = self.refused(table(("G1", "medical", "ok", ""), ("G2", "business", "needs-evidence", "p")))
        self.assertIn("G2 has not been reviewed for ai; medical (its words trigger it: 500 mg)", e.error)
        self.assertFalse(self.file.exists())
        RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "business", "needs-evidence", "p"),
                               ("G2", "medical", "needs-doctor-approval", "dose")))
        self.assertEqual(sorted((i["event_id"], i["flag"]) for i in read_json(self.file)["items"]),
                         [("G2", "business"), ("G2", "medical")])
        self.assertEqual(self.ok_flags(), {"G1": MED})          # G2's medical row says the key was reviewed
        c = RF.counts(RF.load(self.p))
        self.assertEqual((c["ai"], c["medical"], c["business"]),
                         ({"reviewed": 2, "ok": 2, "flagged": 0}, {"reviewed": 2, "ok": 1, "flagged": 1},
                          {"reviewed": 1, "ok": 0, "flagged": 1}))
        write_json(self.file, dict(read_json(self.file), items=[]))
        self.assertIsNone(RF.load(self.p))                     # wiped flags: G2 is in neither list

    def test_adding_business_to_the_profile_needs_a_full_review(self):
        RF.write(self.p, full(("G2", "medical", "remove", "r")))
        self.prof(review_domains=["business"])
        self.assertIsNone(RF.load(self.p))
        e = self.refused(table(("G1", "medical", "ok", ""), ("G1", "business", "ok", "")))
        self.assertIn("G2 has not been reviewed", e.error)
        self.assertIn("ai+medical", e.error)
        self.assertIn("ai+business+medical", e.error)
        r = RF.write(self.p, table(("G1", "medical", "ok", ""), ("G1", "business", "ok", ""), ("G2", "medical", "ok", ""),
                                   ("G2", "business", "ok", "")))
        self.assertEqual((r["domain"], r["items"]), ("ai+business+medical", []))

    def test_a_legacy_file_needs_one_full_review(self):
        for legacy, key in (("general", "ai+medical"), ("medical", "ai+medical"), ("religious", "ai+medical+religious")):
            with self.subTest(legacy):
                self.prof(domain=legacy)
                r = filed(RF.write(self.p, full(("G2", "medical", "remove", "r"))))
                self.assertEqual(r["domain"], key)
                write_json(self.file, dict(r, domain=legacy, ok=[{"event_id": o["event_id"], "text": o["text"]}
                                                                 for o in r["ok"]]))   # as the T4.13 engine wrote it
                self.assertIsNone(RF.load(self.p))
                e = self.refused(table(("G1", "medical", "ok", "")))
                self.assertIn("G2 has not been reviewed", e.error)
                self.assertIn(f"before review domains (it says {legacy})", e.error)
                self.assertIn(key, e.error)
                self.assertEqual(RF.write(self.p, full())["domain"], key)

    def test_a_verdict_outside_its_flags_list_is_refused(self):
        self.prof(domain="religious")
        for flag, verdict in (("religious", "needs-doctor-approval"), ("medical", "needs-evidence"),
                              ("business", "needs-doctor-approval"), ("ai", "needs-evidence"),
                              ("medical", "needs-disclosure")):
            with self.subTest(flag=flag, verdict=verdict):
                e = self.refused(full(("G1", flag, verdict, "r")))
                self.assertIn(f"{verdict!r} is not a verdict of the {flag} check", e.error)
                self.assertIn(", ".join(registry()[flag]["verdicts"]), e.how)
        for flag, entry in registry().items():
            for verdict in entry["verdicts"]:
                with self.subTest(ok=(flag, verdict)):
                    rows = [("G1", flag, verdict, "r")] + ([("G1", "medical", "ok", "")] if flag != "medical" else [])
                    RF.write(self.p, table(*rows, ("G2", "medical", "ok", "")))

    def test_old_verdicts_still_read(self):
        """VERDICTS stays the union for reading: a T4.13 religious row with needs-doctor-approval loads."""
        self.prof(domain="religious")
        r = filed(RF.write(self.p, full(("G2", "religious", "remove", "r"), ("G2", "medical", "ok", ""))))
        write_json(self.file, dict(r, items=[dict(r["items"][0], verdict="needs-doctor-approval")]))
        self.assertIsNotNone(RF.load(self.p))
        self.assertTrue(set(RF.VERDICTS) >= {v for e in registry().values() for v in e["verdicts"]})

    def test_the_carry_rules_hold_for_every_registry_flag(self):
        """Coverage, carrying, the uncarried-flag re-review and the reworded-flag refusal keep their meaning for every
        registry domain's flag (M1-T2: parameterised over the registry)."""
        for flag, entry in registry().items():
            verdict = [v for v in entry["verdicts"] if v != "ok"][0]
            med = lambda i: [] if flag == "medical" else [(i, "medical", "ok", "")]    # noqa: E731
            with self.subTest(flag):
                self.file.unlink(missing_ok=True)
                put_timeline(self.p)
                RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", flag, verdict, "x"), *med("G2")))
                r = RF.write(self.p, table())                                        # nothing changed: carried
                self.assertEqual([(i["event_id"], i["flag"], i.get("carried")) for i in r["items"]],
                                 [("G2", flag, True)])
                spec = timeline_spec()
                spec["events"][1]["params"]["headline"] = "Take 1000 mg daily"
                put_timeline(self.p, spec)
                e = self.refused(table(("G1", "medical", "ok", "")))
                self.assertIn(f"G2 ({flag}) was flagged in the earlier review and its on-screen wording changed", e.error)
                spec = timeline_spec()
                spec["events"][1]["event_id"] = "G7"
                put_timeline(self.p, spec)
                e = self.refused(table(*(med("G7") or [("G7", "ai", "ok", "")])))
                self.assertIn(f"review G7 for {flag}", e.error)
                r = RF.write(self.p, table(("G7", flag, "ok", ""), *med("G7")))
                self.assertEqual([(c["event_id"], c["from_event_id"], c["flag"]) for c in r["cleared"]],
                                 [("G7", "G2", flag)])

    def test_the_same_table_twice_writes_the_same_file(self):
        put_timeline(self.p, biz_spec())
        t = table(("G1", "medical", "ok", ""), ("G2", "medical", "ok", ""), ("G4", "business", "remove", "x"),
                  ("G4", "medical", "ok", ""))
        a = filed(RF.write(self.p, t))
        b = filed(RF.write(self.p, t))
        a.pop("written_at"), b.pop("written_at")
        self.assertEqual(a, b)


# ------------------------------------------------------------------------- Task 53 leftover (review 6275496 P2-3)
HADITH_PLANT = SK / "evals" / "review-religious-hadith-attribution" / "plant" / "timeline-spec.json"
DOSE_PLANT = SK / "evals" / "review-religious-hadith-and-dose" / "plant" / "timeline-spec.json"
# A file whose `coverage` is not exactly this engine's (an int): its ok rows' medical/religious may be implied.
NO_COVERAGE = object()
UNTRUSTED = (("no coverage", NO_COVERAGE), ("coverage 1", 1), ("coverage 2", 2), ("coverage 3", 3),
             ("coverage '4'", "4"), ("coverage 4.0", 4.0), ("coverage True", True), ("coverage 5", 5))


def hadith_spec() -> dict:
    """The Task 53 eval's planted plan: G01 a greeting, G02 a «قال رسول الله ﷺ …» citation the religious lexicon
    detects, G03 a call to subscribe. Its words are read from that fixture, never copied into this file."""
    return json.loads(HADITH_PLANT.read_text(encoding="utf-8"))


def with_coverage(doc: dict, cov) -> dict:
    out = {k: v for k, v in doc.items() if k != "coverage"}
    if cov is not NO_COVERAGE:
        out["coverage"] = cov
    return out


def as_lazy(good: dict, ids) -> dict:
    """What an engine before coverage 4 wrote for one medical (or religious) `ok` row per line of a religious client:
    no items, every ok row `flags: [medical, religious]` (the implied one stored as named)."""
    text = {o["event_id"]: o["text"] for o in good["ok"]} | {i["event_id"]: i["text"] for i in good["items"]}
    return dict(good, items=[], ok=[{"event_id": i, "text": text[i], "flags": ["medical", "religious"]} for i in ids])


class _Review:
    def refused(self, findings):
        before = self.file.read_bytes() if self.file.exists() else None
        with self.assertRaises(Guidance) as cm:
            RF.write(self.p, findings)
        self.assertEqual(self.file.read_bytes() if self.file.exists() else None, before, "a refusal writes nothing")
        self.assertEqual(cm.exception.where, str(self.file))           # review 9a4fdc7 P3-2: names the file
        return cm.exception

    def ok_flags(self) -> dict:
        return {o["event_id"]: o.get("flags") for o in read_json(self.file)["ok"]}

    def ok_rows(self) -> dict:
        return {o["event_id"]: {k: v for k, v in o.items() if k in ("flags", "implied")} for o in read_json(self.file)["ok"]}

    def prof(self, **kw):
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", kw)


class TestReligiousNeverImplied(_Review, Base):
    """A line whose words trigger religious (a hadith citation, quoted scripture) needs its own `religious` row, as a
    triggered ai does: a religious client's `medical` row never clears it, and (owner rule 2026-10-20, review 9a4fdc7
    P2-1) a detected citation, verse or ruling is never `ok`: it goes to the content owner. A file written before
    coverage 4 is not current once on such a line (its ok row may hold a religious that was only implied)."""

    DOMAIN = "religious"

    def setUp(self):
        super().setUp()
        put_timeline(self.p, hadith_spec())

    def test_the_fixture_line_is_detected_as_a_religious_citation(self):
        from lib import review_domains as RD
        lines = {x["event_id"]: x["detected"] for x in RD.scan(self.p)["lines"]}
        self.assertEqual({i: set(d) for i, d in lines.items()}, {"G01": set(), "G02": {"religious"}, "G03": set()})
        self.assertIn("citation", {h["rule"] for h in lines["G02"]["religious"]})

    def test_a_detected_citation_passed_as_medical_ok_is_refused(self):
        for g02 in (("G02", "medical", "ok", ""), ("G02", "medical", "reword-to-match", "r")):
            with self.subTest(g02[2]):
                e = self.refused(table(("G01", "medical", "ok", ""), g02, ("G03", "medical", "ok", "")))
                self.assertIn("G02 has not been reviewed for religious (its words trigger it: ", e.error)
                self.assertNotIn("G01", e.error)
                self.assertNotIn("G03", e.error)
        self.assertFalse(self.file.exists())

    def test_a_citation_on_screen_is_never_ok(self):
        """Review 9a4fdc7 P2-1: the engine, not only the prompt text, sends a detected citation to the content owner."""
        for extra in ((), (("G02", "medical", "ok", ""),)):
            with self.subTest(extra=extra):
                e = self.refused(table(("G01", "medical", "ok", ""), ("G02", "religious", "ok", ""), *extra,
                                       ("G03", "medical", "ok", "")))
                self.assertIn("G02 shows or cites a religious citation, verse or ruling (its words: ", e.error)
                self.assertIn("it needs the content owner's approval (reword-to-match, needs-approval, remove), never ok",
                              e.error)
                self.assertNotIn("G01", e.error)
        for verdict in ("needs-approval", "reword-to-match", "remove"):
            with self.subTest(verdict):
                self.file.unlink(missing_ok=True)
                r = RF.write(self.p, table(("G01", "medical", "ok", ""), ("G02", "religious", verdict, "x"),
                                           ("G03", "medical", "ok", "")))
                self.assertEqual([(i["event_id"], i["flag"], i["verdict"]) for i in r["items"]],
                                 [("G02", "religious", verdict)])
        self.domain("medical")                                   # the owner rule holds for every client
        self.file.unlink()
        e = self.refused(table(("G01", "medical", "ok", ""), ("G02", "medical", "ok", ""), ("G02", "religious", "ok", ""),
                               ("G03", "medical", "ok", "")))
        self.assertIn("G02 shows or cites a religious citation", e.error)

    def test_a_citation_goes_to_the_content_owner_and_ok_rows_store_only_what_was_named(self):
        r = RF.write(self.p, table(("G01", "medical", "ok", ""), ("G02", "religious", "needs-approval", "hadith"),
                                   ("G03", "medical", "ok", "")))
        self.assertEqual([(i["event_id"], i["flag"], i["verdict"]) for i in r["items"]],
                         [("G02", "religious", "needs-approval")])
        self.assertEqual(r["coverage"], 4)
        self.assertEqual(self.ok_rows(), {"G01": {"flags": MED}, "G03": {"flags": MED}})   # religious implied, not stored
        self.assertIsNotNone(RF.load(self.p))
        RF.write(self.p, table())                                # carried as it is
        self.assertEqual(self.ok_rows(), {"G01": {"flags": MED}, "G03": {"flags": MED}})
        self.assertEqual([(i["event_id"], i.get("carried")) for i in read_json(self.file)["items"]], [("G02", True)])
        self.assertIsNotNone(RF.load(self.p))

    def test_a_medical_client_is_unchanged(self):
        self.domain("medical")
        e = self.refused(table(("G01", "medical", "ok", ""), ("G02", "medical", "ok", ""), ("G03", "medical", "ok", "")))
        self.assertIn("G02 has not been reviewed for religious", e.error)
        RF.write(self.p, table(("G01", "medical", "ok", ""), ("G02", "medical", "ok", ""),
                               ("G02", "religious", "needs-approval", "h"), ("G03", "medical", "ok", "")))
        self.assertEqual(self.ok_flags(), {"G01": MED, "G02": MED, "G03": MED})
        doc = read_json(self.file)
        write_json(self.file, with_coverage(doc, NO_COVERAGE))   # an older file: still current here
        self.assertIsNotNone(RF.load(self.p))                    # (religious is never implied for a medical client)

    def test_an_older_file_is_not_current_once_and_asks_only_the_citation_again(self):
        """load() decision: every engine before coverage 4 stored the implied religious in the ok row's `flags`, so such
        a file cannot tell an explicit religious from an implied one. On a line whose words trigger religious it is not
        current (NEEDS-YOU asks for the review again, autopilot holds it), and the next write asks only that line. The
        same for a flagless row or a row marked implied, whatever the file says (review 9a4fdc7 P3-3, P3-4, P3-7)."""
        good = filed(RF.write(self.p, table(("G01", "medical", "ok", ""), ("G02", "religious", "needs-approval", "h"),
                                            ("G02", "medical", "ok", ""), ("G03", "medical", "ok", ""))))
        self.assertEqual(good["coverage"], 4)                           # the on-disk value (module docstring)
        self.assertEqual(RF.load(self.p), good)
        lazy = as_lazy(good, ("G01", "G02", "G03"))
        cases = [(label, with_coverage(lazy, cov)) for label, cov in UNTRUSTED]
        cases += [("ok rows without flags", dict(lazy, ok=[{"event_id": o["event_id"], "text": o["text"]}
                                                            for o in lazy["ok"]])),
                  ("ok rows marked implied", dict(lazy, ok=[dict(o, implied=True) for o in lazy["ok"]]))]
        for label, doc in cases:
            with self.subTest(label):
                write_json(self.file, doc)
                self.assertIsNone(RF.load(self.p))
                e = self.refused(table())
                self.assertIn("G02 has not been reviewed for religious", e.error)
                self.assertNotIn("G01", e.error)
                self.assertNotIn("G03", e.error)
        RF.write(self.p, table(("G02", "religious", "needs-approval", "h")))   # once: current again
        self.assertEqual(read_json(self.file)["coverage"], 4)
        self.assertIsNotNone(RF.load(self.p))
        self.assertEqual(self.ok_rows(), {"G01": {"flags": ["medical", "religious"], "implied": True},   # never
                                          "G03": {"flags": ["medical", "religious"], "implied": True}})  # re-stamped

    def test_an_older_file_without_a_religious_line_stays_current(self):
        put_timeline(self.p)                                     # the default plan: nothing on it triggers religious
        good = filed(RF.write(self.p, full(("G2", "medical", "needs-doctor-approval", "dose"))))
        write_json(self.file, with_coverage(good, NO_COVERAGE))
        self.assertIsNotNone(RF.load(self.p))
        RF.write(self.p, table())                                # and its rows still carry


class TestMedicalNeverImplied(_Review, Base):
    """Round 2, the mirror gap: a line whose words trigger medical (a dose, a drug, a cure claim) needs its own `medical`
    row on a religious client too: a `religious` row never clears it. Before, one `religious: ok` row cleared a dose for
    medical, so it reached no doctor (NEEDS-YOU, autopilot). A file written before coverage 4 is not current on such a
    line, once."""

    DOMAIN = "religious"

    def setUp(self):
        super().setUp()
        put_timeline(self.p)                                     # G1 no trigger, G2 a dose

    def test_the_dose_line_is_detected_as_medical(self):
        from lib import review_domains as RD
        det = {x["event_id"]: set(x["detected"]) for x in RD.scan(self.p)["lines"]}
        self.assertEqual(det, {"G1": set(), "G2": {"medical"}})

    def test_a_dose_passed_as_religious_is_refused(self):
        for g2 in (("G2", "religious", "ok", ""), ("G2", "religious", "needs-approval", "r")):
            with self.subTest(g2[2]):
                e = self.refused(table(("G1", "religious", "ok", ""), g2))
                self.assertIn("G2 has not been reviewed for medical (its words trigger it: 500 mg)", e.error)
                self.assertNotIn("G1", e.error)
        self.assertFalse(self.file.exists())

    def test_an_explicit_medical_row_is_accepted(self):
        r = RF.write(self.p, table(("G1", "religious", "ok", ""), ("G2", "medical", "needs-doctor-approval", "dose")))
        self.assertEqual([(i["event_id"], i["flag"], i["verdict"]) for i in r["items"]],
                         [("G2", "medical", "needs-doctor-approval")])
        self.assertEqual(self.ok_flags(), {"G1": ["religious"]})   # a line nothing triggers: medical implied, not stored
        self.assertIsNotNone(RF.load(self.p))
        self.file.unlink()
        RF.write(self.p, table(("G1", "religious", "ok", ""), ("G2", "medical", "ok", ""), ("G2", "religious", "ok", "")))
        self.assertEqual(self.ok_flags(), {"G1": ["religious"], "G2": ["medical", "religious"]})
        self.assertIsNotNone(RF.load(self.p))
        RF.write(self.p, table())                    # a file written now carries its named flags: no re-ask
        self.assertEqual(self.ok_flags(), {"G1": ["religious"], "G2": ["medical", "religious"]})
        self.file.unlink()
        RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "ok", "")))   # a medical row still
        self.assertEqual(self.ok_flags(), {"G1": MED, "G2": MED})                          # implies religious here
        self.assertIsNotNone(RF.load(self.p))

    def test_a_medical_client_is_unchanged(self):
        self.domain("medical")
        e = self.refused(table(("G1", "medical", "ok", ""), ("G2", "religious", "ok", "")))
        self.assertIn("G2 has not been reviewed for ai; medical (its words trigger it: 500 mg)", e.error)
        RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "ok", "")))
        self.assertEqual(self.ok_flags(), {"G1": MED, "G2": MED})
        doc = read_json(self.file)
        write_json(self.file, with_coverage(doc, NO_COVERAGE))   # an older file: still current here
        self.assertIsNotNone(RF.load(self.p))                    # (nothing is implied by a medical client's medical row)
        RF.write(self.p, table())                                # and carried as named: nothing to mark implied
        self.assertEqual(self.ok_rows(), {"G1": {"flags": MED}, "G2": {"flags": MED}})

    def test_an_older_file_is_not_current_once_on_a_medical_line(self):
        good = filed(RF.write(self.p, table(("G1", "religious", "ok", ""), ("G2", "medical", "ok", ""),
                                            ("G2", "religious", "ok", ""))))
        self.assertEqual(good["coverage"], 4)
        self.assertEqual(RF.load(self.p), good)
        lazy = as_lazy(good, ("G1", "G2"))                       # what was written for one `religious: ok` per line
        cases = [(label, with_coverage(lazy, cov)) for label, cov in UNTRUSTED]
        cases.append(("ok rows without flags", dict(lazy, ok=[{"event_id": o["event_id"], "text": o["text"]}
                                                               for o in lazy["ok"]])))
        for label, doc in cases:
            with self.subTest(label):
                write_json(self.file, doc)
                self.assertIsNone(RF.load(self.p))
                e = self.refused(table())
                self.assertIn("G2 has not been reviewed for medical", e.error)
                self.assertNotIn("G1", e.error)
        RF.write(self.p, table(("G2", "medical", "ok", "")))           # once: the next write is current again
        self.assertEqual(read_json(self.file)["coverage"], 4)
        self.assertIsNotNone(RF.load(self.p))
        self.assertEqual(self.ok_rows(), {"G1": {"flags": ["medical", "religious"], "implied": True},
                                          "G2": {"flags": MED}})

    def test_a_line_that_triggers_both_is_asked_both(self):
        """The Task 53 eval's planted hadith-and-dose plan (G02 a citation with a dose, G03 a dose), read from its
        fixture: an older file asks G02 for both checks and G03 for medical."""
        put_timeline(self.p, json.loads(DOSE_PLANT.read_text(encoding="utf-8")))
        good = filed(RF.write(self.p, table(("G01", "religious", "ok", ""), ("G02", "religious", "needs-approval", "h"),
                                            ("G02", "medical", "ok", ""), ("G03", "medical", "ok", ""))))
        self.assertEqual(self.ok_flags(), {"G01": ["religious"], "G02": MED, "G03": MED})
        write_json(self.file, with_coverage(as_lazy(good, ("G01", "G02", "G03")), 3))
        self.assertIsNone(RF.load(self.p))
        e = self.refused(table())
        self.assertIn("G02 has not been reviewed: list it", e.error)
        self.assertIn("G03 has not been reviewed for medical (its words trigger it: ", e.error)
        self.assertNotIn("G01", e.error)
        RF.write(self.p, table(("G02", "religious", "needs-approval", "h"), ("G02", "medical", "ok", ""),
                               ("G03", "medical", "ok", "")))
        self.assertIsNotNone(RF.load(self.p))


class TestApprovalOnlyRules(_Review, Base):
    """Review 9a4fdc7 P2-1: each approval-only rule (APPROVAL_ONLY) refuses a religious `ok`; a plain faith word does
    not. The words are read from the shipped religious lexicon at runtime (never a verse: only the citation, ruling
    and faith rules are exercised here; the verse rules are pinned by the set)."""

    DOMAIN = "religious"

    def line(self, words: str):
        put_timeline(self.p, dict(timeline_spec(), events=[event("G1", 1000, 3500, text=words)]))

    def term(self, rule: str, has: str = "") -> str:
        from lib import review_domains as RD
        r = next(r for r in RD.lexicon("religious")["rules"] if r["id"] == rule)
        return next(t for t in r["terms"] if has in t).replace("*", "")

    def rules_on_g1(self) -> set:
        from lib import review_domains as RD
        (x,) = RD.scan(self.p)["lines"]
        return {h["rule"] for h in x["detected"].get("religious", [])}

    def test_each_approval_only_rule_refuses_ok_and_a_faith_word_does_not(self):
        self.assertEqual(RF.APPROVAL_ONLY, {"religious": ("citation", "ruling", "verse-phrase", "quran-verse",
                                                          "quoted-scripture")})
        for rule, has in (("citation", "رسول"), ("ruling", "شرعي")):
            with self.subTest(rule):
                self.file.unlink(missing_ok=True)
                self.line(self.term(rule, has))
                self.assertEqual(self.rules_on_g1(), {rule})
                e = self.refused(table(("G1", "religious", "ok", ""), ("G1", "medical", "ok", "")))
                self.assertIn("G1 shows or cites a religious citation, verse or ruling", e.error)
                RF.write(self.p, table(("G1", "religious", "needs-approval", "x"), ("G1", "medical", "ok", "")))
                self.assertIsNotNone(RF.load(self.p))
        self.file.unlink()
        self.line(self.term("faith"))
        self.assertEqual(self.rules_on_g1(), {"faith"})
        RF.write(self.p, table(("G1", "religious", "ok", "")))
        self.assertEqual(self.ok_flags(), {"G1": ["religious"]})
        self.assertIsNotNone(RF.load(self.p))

    def test_an_ok_on_a_citation_line_never_counts(self):
        """A coverage 4 file whose citation line sits in `ok` (moved there by hand, or by a rule that became approval-
        only in a lexicon update) is not current, and the next write asks that line for religious again."""
        put_timeline(self.p, hadith_spec())
        good = filed(RF.write(self.p, table(("G01", "medical", "ok", ""), ("G02", "religious", "needs-approval", "h"),
                                            ("G02", "medical", "ok", ""), ("G03", "medical", "ok", ""))))
        moved = dict(good, items=[], ok=[dict(o, flags=["medical", "religious"]) if o["event_id"] == "G02" else o
                                         for o in good["ok"]])
        write_json(self.file, moved)
        self.assertIsNone(RF.load(self.p))
        e = self.refused(table())
        self.assertIn("G02 shows or cites a religious citation", e.error)
        self.assertIn("its earlier ok no longer counts", e.error)


class TestRound4(_Review, Base):
    """Review 0aa6e4d: a detected citation is never ok under `review_detect: suggest` either (P2-2); the refusal never
    invites an ok and says "shows or cites" (P3-2); a flagless row is untrusted on every key (P3-4); an older file's
    named ai row still counts on an AI-asset line (P3-6)."""

    DOMAIN = None

    def test_suggest_still_sends_a_detected_citation_to_the_content_owner(self):
        put_timeline(self.p, hadith_spec())
        self.prof(domain="religious", review_detect="suggest")
        rows = [("G01", "medical", "ok", ""), ("G02", "religious", "ok", ""), ("G03", "medical", "ok", "")]
        e = self.refused(table(*rows))
        self.assertIn("G02 shows or cites a religious citation, verse or ruling (its words: ", e.error)
        RF.write(self.p, table(rows[0], ("G02", "religious", "needs-approval", "h"), rows[2]))
        self.assertIsNotNone(RF.load(self.p))
        self.file.unlink()
        self.prof(domain="religious", review_detect="off")       # off: nothing is detected, the reviewer alone decides
        RF.write(self.p, table(*rows))
        self.assertIsNotNone(RF.load(self.p))
        self.prof(domain="religious", review_detect="suggest")   # suggest again: that ok never counts
        self.assertIsNone(RF.load(self.p))

    def test_the_citation_refusal_never_invites_an_ok(self):
        put_timeline(self.p, hadith_spec())
        self.prof(domain="religious")
        e = self.refused(table(("G01", "medical", "ok", ""), ("G02", "religious", "ok", ""), ("G03", "medical", "ok", "")))
        self.assertIn("never ok", e.how)
        self.assertNotIn("an `ok` row once the wording is fine", e.how)

    def test_an_earlier_ok_on_a_line_that_now_holds_a_citation_asks_for_the_content_owner(self):
        put_timeline(self.p, hadith_spec())
        self.prof(domain="religious")
        good = filed(RF.write(self.p, table(("G01", "medical", "ok", ""), ("G02", "religious", "needs-approval", "h"),
                                            ("G02", "medical", "ok", ""), ("G03", "medical", "ok", ""))))
        for flags in (["medical", "religious"], ["religious"]):
            with self.subTest(flags):
                write_json(self.file, dict(good, items=[], ok=[dict(o, flags=flags) if o["event_id"] == "G02" else o
                                                               for o in good["ok"]]))
                self.assertIsNone(RF.load(self.p))
                e = self.refused(table())
                self.assertIn("G02 shows or cites a religious citation, verse or ruling (its words: ", e.error)
                self.assertIn("its earlier ok no longer counts", e.error)
                self.assertNotIn("G02 has not been reviewed", e.error)
                self.assertIn("never ok", e.how)

    def test_a_citation_only_in_the_speech_is_said_so(self):
        from lib import review_domains as RD
        r = next(r for r in RD.lexicon("religious")["rules"] if r["id"] == "citation")
        cited = next(t for t in r["terms"] if "رسول" in t).replace("*", "")
        g1 = dict(event("G1", 1000, 3500, text="مقدمة"), evidence=cited)
        put_timeline(self.p, dict(timeline_spec(), events=[g1]))
        self.prof(domain="religious")
        (x,) = RD.scan(self.p)["lines"]
        self.assertEqual({h["in"] for h in x["detected"]["religious"]}, {"speech"})
        e = self.refused(table(("G1", "religious", "ok", ""), ("G1", "medical", "ok", "")))
        self.assertIn("G1 shows or cites a religious citation, verse or ruling", e.error)

    def test_a_flagless_row_is_untrusted_on_every_key(self):
        put_timeline(self.p)                                     # G2 a dose
        for prof in ({"review_domains": ["business"]}, {}):
            with self.subTest(prof):
                self.file.unlink(missing_ok=True)
                self.prof(**prof)
                key = RF._domain()
                rows = [(i, f, "ok", "") for i in ("G1", "G2") for f in key.split("+") if f != "ai"]
                good = filed(RF.write(self.p, table(*rows)))
                self.assertIsNotNone(RF.load(self.p))
                write_json(self.file, dict(good, ok=[{"event_id": o["event_id"], "text": o["text"]} for o in good["ok"]]))
                self.assertIsNone(RF.load(self.p))               # the dose line's medical is not trusted
                e = self.refused(table())
                self.assertIn("G2 has not been reviewed", e.error)
                self.assertNotIn("G1", e.error)

    def test_a_row_marked_implied_is_untrusted_on_every_key(self):
        """r5 (mutant "untrusted: the implied marker ignored"): `implied: true` makes a row untrusted on a key without
        religious too, not only the missing `flags`: its medical never clears a line whose words trigger medical."""
        put_timeline(self.p)                                     # G2 a dose
        for prof in ({"review_domains": ["business"]}, {}):
            with self.subTest(prof):
                self.file.unlink(missing_ok=True)
                self.prof(**prof)
                key = RF._domain()
                self.assertNotIn("religious", key.split("+"))
                rows = [(i, f, "ok", "") for i in ("G1", "G2") for f in key.split("+") if f != "ai"]
                good = filed(RF.write(self.p, table(*rows)))
                self.assertIsNotNone(RF.load(self.p))
                write_json(self.file, dict(good, ok=[dict(o, implied=True) for o in good["ok"]]))   # flags kept
                self.assertIsNone(RF.load(self.p))               # the dose line's medical is not trusted
                e = self.refused(table())
                self.assertIn("G2 has not been reviewed", e.error)
                self.assertNotIn("G1", e.error)

    def test_an_older_files_named_ai_row_still_counts_on_an_ai_asset_line(self):
        self.prof(domain="religious")
        write_json(self.p.client_db / "asset-manifest.json", {"assets": [{"rel": "data/Broll/gen.png",
                                                                          "ai_generated": True}]})
        put_timeline(self.p, dict(timeline_spec(), events=[timeline_spec()["events"][0],
                                                           event("G4", 7400, 8600, text="صورة توضيحية",
                                                                 image="data/Broll/gen.png")]))
        good = filed(RF.write(self.p, table(("G1", "medical", "ok", ""), ("G4", "ai", "ok", ""),
                                            ("G4", "medical", "ok", ""))))
        self.assertEqual(self.ok_flags(), {"G1": MED, "G4": ["ai", "medical"]})
        for label, cov in UNTRUSTED:
            with self.subTest(label):
                write_json(self.file, with_coverage(good, cov))
                self.assertIsNotNone(RF.load(self.p))           # ai is never implied: a named ai row is always named


class TestImpliedNeverStored(_Review, Base):
    """Review 9a4fdc7 P1-1: an ok row stores only the flags it was named for (coverage 4), so a line that starts
    triggering medical or religious later (review_detect switched to review, a lexicon update) asks for its own row,
    and a row carried from an older file is never re-stamped as named (`implied: true`)."""

    DOMAIN = None

    def setUp(self):
        super().setUp()
        put_timeline(self.p)                                     # G1 no trigger, G2 a dose

    def test_a_dose_found_after_review_detect_is_switched_on(self):
        for mode in ("off", "suggest"):
            with self.subTest(mode):
                self.file.unlink(missing_ok=True)
                self.prof(domain="religious", review_detect=mode)
                RF.write(self.p, table(("G1", "religious", "ok", ""), ("G2", "religious", "ok", "")))
                self.assertEqual(self.ok_flags(), {"G1": ["religious"], "G2": ["religious"]})
                self.assertIsNotNone(RF.load(self.p))
                self.prof(domain="religious")                    # review, the default: same key, same plan
                self.assertIsNone(RF.load(self.p))
                e = self.refused(table())
                self.assertIn("G2 has not been reviewed for medical (its words trigger it: 500 mg)", e.error)
                self.assertNotIn("G1", e.error)

    def test_a_dose_found_by_a_lexicon_update(self):
        from unittest import mock
        from lib import review_domains as RD
        self.prof(domain="religious")
        real = RD.matchers
        with mock.patch.object(RD, "matchers", lambda: [m for m in real() if m[0] != "medical"]):
            RF.write(self.p, table(("G1", "religious", "ok", ""), ("G2", "religious", "ok", "")))
            self.assertIsNotNone(RF.load(self.p))                # the older lexicon does not detect the dose
        self.assertIsNone(RF.load(self.p))                       # the updated one does
        e = self.refused(table())
        self.assertIn("G2 has not been reviewed for medical (its words trigger it: 500 mg)", e.error)

    def test_a_citation_found_after_review_detect_is_switched_on(self):
        put_timeline(self.p, hadith_spec())
        self.prof(domain="religious", review_detect="suggest")
        RF.write(self.p, table(("G01", "medical", "ok", ""), ("G02", "medical", "ok", ""), ("G03", "medical", "ok", "")))
        self.assertEqual(self.ok_flags(), {"G01": MED, "G02": MED, "G03": MED})
        self.prof(domain="religious")
        self.assertIsNone(RF.load(self.p))
        e = self.refused(table())
        self.assertIn("G02 has not been reviewed for religious (its words trigger it: ", e.error)

    def test_a_carried_older_row_is_never_restamped_as_named(self):
        self.prof(domain="religious", review_detect="off")
        good = filed(RF.write(self.p, table(("G1", "medical", "ok", ""), ("G2", "medical", "ok", ""))))
        write_json(self.file, with_coverage(as_lazy(good, ("G1", "G2")), 3))
        self.assertIsNotNone(RF.load(self.p))                    # nothing triggers now: current
        RF.write(self.p, table())                                # carried into a coverage 4 file
        self.assertEqual(read_json(self.file)["coverage"], 4)
        self.assertEqual(self.ok_rows(), {"G1": {"flags": ["medical", "religious"], "implied": True},
                                          "G2": {"flags": ["medical", "religious"], "implied": True}})
        self.prof(domain="religious")                            # the dose is detected now
        self.assertIsNone(RF.load(self.p))
        e = self.refused(table())
        self.assertIn("G2 has not been reviewed for medical", e.error)
        RF.write(self.p, table(("G2", "medical", "ok", "")))
        self.assertEqual(self.ok_rows(), {"G1": {"flags": ["medical", "religious"], "implied": True},
                                          "G2": {"flags": MED}})
        self.assertIsNotNone(RF.load(self.p))

    def test_the_implied_marker_is_checked(self):
        self.prof(domain="religious")
        good = filed(RF.write(self.p, table(("G1", "religious", "ok", ""), ("G2", "medical", "ok", ""))))
        for label, row in (("implied false", {"implied": False}), ("implied text", {"implied": "yes"})):
            with self.subTest(label):
                write_json(self.file, dict(good, ok=[dict(o, **row) for o in good["ok"]]))
                self.assertIsNone(RF.load(self.p))
        write_json(self.file, dict(good, ok=[{"event_id": o["event_id"], "text": o["text"], "implied": True}
                                             for o in good["ok"]]))   # implied on a row without flags
        self.assertIsNone(RF.load(self.p))
        write_json(self.file, dict(good, ok=[dict(o, implied=True) if o["event_id"] == "G1" else o
                                             for o in good["ok"]]))   # well-formed, on a line nothing triggers
        self.assertIsNotNone(RF.load(self.p))
        write_json(self.file, dict(good, ok=[dict(o, implied=True) for o in good["ok"]]))   # G2's medical may be implied
        self.assertIsNone(RF.load(self.p))

    def test_previous_reports_no_coverage_for_a_missing_or_unusable_file(self):
        self.prof(domain="religious")
        key = RF._domain()
        self.assertIsNone(RF._previous(self.p, "timeline", key)[3])
        self.file.write_text("{broken", encoding="utf-8")
        self.assertIsNone(RF._previous(self.p, "timeline", key)[3])


if __name__ == "__main__":
    unittest.main()
