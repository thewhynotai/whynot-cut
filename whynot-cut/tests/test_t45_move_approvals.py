# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 part B, executor ruling (c) on BL-14 Q1 (2026-10-19): a move or "already moved" rewrites the files
an approval or sign-off hashes, so no plan, transcript or fingerprint points at the old folder's media. The approvals
they carried become void ON PURPOSE, and:
  (1) the result (`approvals_to_redo`) and NEEDS-YOU (client_move.still_void) list each one by item and kind, Arabic
      first: «اتنقل العميل: وافق تاني على الخطة / التفريغ / … لـ <item>»;
  (2) nothing re-approves by itself (no approval file is written by a move);
  (3) per hashed kind: the media path is under the new root, the old approval is void, the NEEDS-YOU line is there;
  (4) a clone keeps the source's approvals untouched and starts the copy with none.
Run:  bash tools/test.sh -p test_t45_move_approvals.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import json
import os
import shutil
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import client_move as CM, plan as PL  # noqa: E402
from lib.common import Context, Paths, read_json, use_context, write_json  # noqa: E402
from lib.episode import EpisodePaths  # noqa: E402
from test_t45_client_move import T0, Base  # noqa: E402

MOTION = ("R02", "R03")                         # R03's own files name no path: only the brand tokens void its plan


def sha(f: Path) -> str:
    return hashlib.sha1(f.read_bytes()).hexdigest()


class Approved(Base):
    """A client with one approval of every kind, each holding, each bound to a file that names the client folder."""
    def setUp(self):
        super().setUp()
        a = lambda r: str(self.src.joinpath(*r.split("/")))
        clip = a("data/Raw/clip 1.mp4")
        p = Paths(self.src, "R01")
        write_json(p.p("02_transcription/words.json"), {"media": clip, "words": [{"w": "hi", "start_ms": 0}]})
        write_json(p.p("02_transcription/verification.json"), {"verified": True, "by": "editor",
                                                                "words_sha1": sha(p.p("02_transcription/words.json"))})
        write_json(p.p("01_analysis/cut-proposals.json"), {"video_id": "R01", "proposals": [],
                                                           "words_sha1": sha(p.p("02_transcription/words.json"))})
        write_json(p.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor", "format": PL.APPROVAL_FORMAT,
                                                            "plan_fingerprint": PL.plan_fingerprint(p)})
        from lib import review_flags as RF
        with use_context(Context(self.src)):
            kind, _index, fp = RF._current(p)
            write_json(RF.path(p), {"schema": RF.SCHEMA, "plan_kind": kind, "plan_fingerprint": fp,
                                    "domain": RF._domain(), "checked": 0, "lines_total": 0, "ok": [], "items": []})
        q = Paths(self.src, "R04")                                           # a check recorded before words_sha1
        write_json(q.p("02_transcription/words.json"), {"media": clip, "words": []})
        write_json(q.p("02_transcription/verification.json"), {"verified": True, "by": "editor"})
        bt = self.src / "output/client_database/branding/brand-tokens.json"
        write_json(bt, {"roles": {"primary": {"hex": "#112233"}}, "logo": a("assets/Brand/logo.png")})
        for vid in MOTION:
            m = Paths(self.src, vid)
            write_json(m.p("00_inputs/source.json"), {"kind": "motion_reel", "format": "9x16"})
            write_json(m.p("01_analysis/motion-script.json"), {"scenes": [{"image": a("assets/Brand/logo.png")}]}
                       if vid == "R02" else {"scenes": []})
            write_json(m.p("01_analysis/motion-plan.json"), {"scenes": []})
            from lib.motion_plan import fingerprint
            with use_context(Context(self.src)):
                fp = fingerprint(m)
            write_json(m.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor", "kind": "motion",
                                                                "format": PL.APPROVAL_FORMAT, "plan_fingerprint": fp})
            if vid == "R03":         # review 7fcbc1d P3-1: a content review on a motion item, voided by the brand only
                write_json(m.p("01_analysis/motion-plan.json"), {"scenes": [], "fps": 30, "fingerprint": fp})
                with use_context(Context(self.src)):
                    kind, _index, rfp = RF._current(m)
                    write_json(RF.path(m), {"schema": RF.SCHEMA, "plan_kind": kind, "plan_fingerprint": rfp,
                                            "domain": RF._domain(), "checked": 0, "lines_total": 0, "ok": [],
                                            "items": []})
        ep = EpisodePaths(self.src, "EP01")
        write_json(ep.p("01_analysis/reels-plan.json"), {"episode": a("data/Raw/clip 1.mp4"), "reels": []})
        write_json(ep.p("02_transcription/words.json"), {"words": []})
        from lib.reels import reels_plan_fingerprint
        write_json(ep.p("01_analysis/reels-plan-validated.json"), {"fingerprint": reels_plan_fingerprint(ep)})
        for f in self.src.rglob("*"):
            if f.is_file():
                os.utime(f, (T0 + 1000, T0 + 1000))
        self.held = CM.approvals(self.src)

    ALL = [("episodes", "EP01", "reels-plan"),
           ("projects", "R01", "cut-proposals"), ("projects", "R01", "plan"), ("projects", "R01", "review"),
           ("projects", "R01", "transcript"),
           ("projects", "R02", "plan"), ("projects", "R03", "plan"), ("projects", "R03", "review"),
           ("projects", "R04", "transcript")]

    def keys(self, lst) -> list:
        return [(v["folder"], v["item"], v["kind"]) for v in lst]

    def approval_files(self, root: Path) -> dict:
        return {k: root.joinpath(*CM._entry(*k)["file"].split("/")).read_bytes() for k in self.ALL}


class TestMotionPlanReseal(Base):
    """Review 91b6b44 P2-1: motion-validation.json binds the compiled motion-plan.json (plan_sha1). A move rewrites
    the plan's paths and moves the record on, so the plan never reads as edited by hand; a plan already edited before
    the move still reads as edited."""
    def test_a_move_reseals_an_unedited_plan_only(self):
        from lib.motion_plan import plan_edited
        a = lambda r: str(self.src.joinpath(*r.split("/")))
        for vid, edited in (("M1", False), ("M2", True)):
            m = Paths(self.src, vid)
            write_json(m.p("00_inputs/source.json"), {"kind": "motion_reel", "format": "9x16"})
            write_json(m.p("01_analysis/motion-plan.json"), {"scenes": [], "audio": {"dialogue": a("data/Raw/clip 1.mp4")}})
            write_json(m.p("01_analysis/motion-validation.json"), {"ok": True,
                                                                   "plan_sha1": sha(m.p("01_analysis/motion-plan.json"))})
            if edited:
                write_json(m.p("01_analysis/motion-plan.json"), {"scenes": [{"text": "HANDEDITED"}],
                                                                 "audio": {"dialogue": a("data/Raw/clip 1.mp4")}})
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        m1, m2 = Paths(self.dest, "M1"), Paths(self.dest, "M2")
        self.assertEqual(read_json(m1.p("01_analysis/motion-plan.json"))["audio"]["dialogue"],
                         str(self.dest / "data/Raw/clip 1.mp4"))
        with use_context(Context(self.dest)):
            self.assertIsNone(plan_edited(m1))
            self.assertIsNotNone(plan_edited(m2))


class TestFixture(Approved):
    def test_every_approval_holds_before_the_move(self):
        self.assertEqual(sorted(self.held), self.ALL)
        self.assertTrue(all(v is True for v in self.held.values()), self.held)


class TestMoveVoidsAndLists(Approved):
    def move(self) -> dict:
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        return doc

    def test_the_dry_run_forecasts_what_the_move_voids(self):
        dry = CM.move(self.src, self.dest)
        self.assertEqual(self.keys(dry["approvals_to_redo"]), self.ALL)
        doc = self.move()
        self.assertEqual(self.keys(doc["approvals_to_redo"]), self.ALL)

    def test_a_motion_review_voided_by_the_brand_tokens_alone_is_forecast_and_listed(self):
        """Review 7fcbc1d P3-1 (mutant K2: `("plan", "review")` -> `("plan",)` in _bound_hit): R03's own files name no
        path, so only the rewritten brand tokens void its content review. The dry run's forecast must say so too."""
        key = ("projects", "R03", "review")
        self.assertIs(self.held[key], True)
        dry = CM.move(self.src, self.dest)
        self.assertNotIn("output/projects/R03/01_analysis/motion-script.json",
                         [r["file"] for r in dry["outside_database"]["rewritten"]])
        self.assertIn(CM.BRAND_TOKENS, [r["file"] for r in dry["outside_database"]["rewritten"]])
        self.assertIn(key, self.keys(dry["approvals_to_redo"]))
        doc = self.move()
        self.assertIn(key, self.keys(doc["approvals_to_redo"]))
        self.assertIn(key, self.keys(CM.still_void(self.dest)))
        from lib import review_flags as RF
        with use_context(Context(self.dest)):
            self.assertIsNone(RF.load(Paths(self.dest, "R03")))

    def test_per_kind_the_media_is_under_the_new_root_and_the_approval_is_void(self):
        doc = self.move()
        d = self.dest
        new_clip = str(d / "data/Raw/clip 1.mp4")
        self.assertEqual(read_json(d / "output/projects/R01/01_analysis/timeline-spec.json")["media"], new_clip)
        self.assertEqual(read_json(d / "output/projects/R01/02_transcription/words.json")["media"], new_clip)
        self.assertEqual(read_json(d / "output/projects/R04/02_transcription/words.json")["media"], new_clip)
        self.assertEqual(read_json(d / "output/projects/R02/01_analysis/motion-script.json")["scenes"][0]["image"],
                         str(d / "assets/Brand/logo.png"))
        self.assertEqual(read_json(d / "output/client_database/branding/brand-tokens.json")["logo"],
                         str(d / "assets/Brand/logo.png"))
        self.assertEqual(read_json(d / "output/episodes/EP01/01_analysis/reels-plan.json")["episode"], new_clip)
        after = CM.approvals(d)
        self.assertEqual(sorted(after), self.ALL)
        self.assertEqual({k: v for k, v in after.items() if v is not False}, {})
        q = Paths(d, "R01")
        from lib import review_flags as RF, transcribe
        self.assertEqual(PL.approval_state(q)["state"], "stale")
        self.assertFalse(transcribe.transcript_verified(q))
        self.assertFalse(transcribe.transcript_verified(Paths(d, "R04")))
        with use_context(Context(d)):
            self.assertIsNone(RF.load(q))
        self.assertEqual(self.keys(doc["approvals_to_redo"]), self.ALL)

    def test_needs_you_lists_each_until_it_is_given_again(self):
        self.move()
        lines = CM.still_void(self.dest)
        self.assertEqual(self.keys(lines), self.ALL)
        plan = next(v for v in lines if v["item"] == "R01" and v["kind"] == "plan")
        self.assertEqual(plan["text_ar"], "اتنقل العميل: وافق تاني على الخطة لـ R01")
        self.assertEqual(plan["text"], "client moved: approve the plan again for R01")
        self.assertEqual(plan["file"], "output/projects/R01/01_analysis/plan-approval.json")
        self.assertIn("reel approve-plan --by editor", plan["how"])                  # the lead's command
        self.assertIn("look at the plan again and approve it", plan["why"])         # the editor's words
        self.assertIn("بص على الخطة تاني ووافق عليها", plan["why_ar"])
        how = {(v["item"], v["kind"]): v["how"] for v in lines}
        self.assertIn("reel motion-plan", how[("R02", "plan")])                      # r1 P3-4
        self.assertEqual(how[("EP01", "reels-plan")], "`reel reels-plan --episode EP01` again, then the editor picks")
        tr = next(v for v in lines if v["item"] == "R01" and v["kind"] == "transcript")
        self.assertEqual(tr["text_ar"], "اتنقل العميل: وافق تاني على التفريغ لـ R01")
        heads = {(v["item"], v["kind"]): (v["text"], v["text_ar"]) for v in lines}          # review r2 N-P3-3
        self.assertEqual(heads[("R01", "cut-proposals")], ("client moved: choose the cuts again for R01",
                                                            "اتنقل العميل: اختار القص تاني لـ R01"))
        self.assertEqual(heads[("EP01", "reels-plan")], ("client moved: pick the reels again for EP01",
                                                          "اتنقل العميل: اختار الريلز تاني لـ EP01"))
        self.assertNotIn("approve", heads[("R01", "review")][0])
        q = Paths(self.dest, "R01")                    # the editor approves the plan again: its line goes
        write_json(q.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                            "format": PL.APPROVAL_FORMAT,
                                                            "plan_fingerprint": PL.plan_fingerprint(q)})
        self.assertNotIn(("projects", "R01", "plan"), self.keys(CM.still_void(self.dest)))
        self.assertEqual(len(CM.still_void(self.dest)), len(self.ALL) - 1)
        shutil.rmtree(self.dest / "output/projects/R04")                  # a deleted item: its line goes too
        self.assertNotIn("R04", [v["item"] for v in CM.still_void(self.dest)])

    def test_nothing_approves_again_by_itself(self):
        before = self.approval_files(self.src)
        self.move()
        after = self.approval_files(self.dest)
        legacy = ("projects", "R04", "transcript")
        self.assertEqual({k: v for k, v in after.items() if k != legacy}, {k: v for k, v in before.items() if k != legacy})
        rec = json.loads(after[legacy])               # the old check, pinned to the words it was given for
        self.assertEqual(rec["words_sha1"], sha(self.src / "output/projects/R04/02_transcription/words.json"))
        self.assertTrue(rec["verified"])
        self.assertEqual(self.approval_files(self.src), before)            # the old folder: untouched, still holds
        self.assertEqual(CM.approvals(self.src), self.held)

    def test_a_second_move_keeps_the_list_and_adds_nothing_twice(self):
        self.move()
        q = Paths(self.dest, "R01")                      # approved again at the first new place, then moved again
        write_json(q.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                            "format": PL.APPROVAL_FORMAT,
                                                            "plan_fingerprint": PL.plan_fingerprint(q)})
        again = self.tmp / "F drive" / "Again"
        again.parent.mkdir()
        self.hold(self.dest)
        doc = CM.move(self.dest, again, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        self.assertEqual(self.keys(doc["outside_database"]["voided"]), [("projects", "R01", "plan")])   # this move
        self.assertEqual(sorted(self.keys(doc["approvals_to_redo"])), self.ALL)            # + the first one's, still due
        rec = read_json(again / CM.VOIDED_REL)["voided"]
        self.assertEqual(sorted((v["folder"], v["item"], v["kind"]) for v in rec), self.ALL)
        self.assertEqual(self.keys(CM.still_void(again)), self.ALL)

    def test_a_damaged_record_is_said_not_hidden(self):
        self.move()
        (self.dest / CM.VOIDED_REL).write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            CM.still_void(self.dest)
        (self.dest / CM.VOIDED_REL).write_text('{"voided": 3}', encoding="utf-8")
        with self.assertRaises(ValueError):
            CM.still_void(self.dest)

    def test_a_hostile_record_names_only_real_items_and_kinds(self):
        self.move()
        write_json(self.dest / CM.VOIDED_REL, {"voided": [
            {"folder": "projects", "item": "../../assets", "kind": "plan"},
            {"folder": "data", "item": "R01", "kind": "plan"},
            {"folder": "projects", "item": "R01", "kind": "rm -rf"},
            {"folder": "projects", "item": "R01", "kind": "plan"}, "x", None]})
        self.assertEqual(self.keys(CM.still_void(self.dest)), [("projects", "R01", "plan")])


class TestAlreadyMovedVoidsAndLists(Approved):
    def test_a_hand_moved_client_voids_and_lists_the_same(self):
        hand = self.tmp / "by hand"
        shutil.copytree(self.src, hand, copy_function=shutil.copy2)
        dry = CM.already_moved(hand)
        self.assertEqual(self.keys(dry["approvals_to_redo"]), self.ALL)
        self.assertFalse((hand / CM.VOIDED_REL).exists())                 # a dry run writes nothing
        self.hold(hand)
        doc = CM.already_moved(hand, apply=True)
        self.assertNotIn("error", doc)
        self.assertEqual(self.keys(doc["approvals_to_redo"]), self.ALL)
        self.assertEqual(self.keys(CM.still_void(hand)), self.ALL)
        self.assertIn("approvals_to_redo", doc["next"])
        self.assertEqual(read_json(hand / "output/projects/R01/01_analysis/timeline-spec.json")["media"],
                         str(hand / "data/Raw/clip 1.mp4"))


class TestCloneStartsUnapproved(Approved):
    def test_the_source_keeps_its_approvals_and_the_copy_has_none(self):
        before = self.approval_files(self.src)
        self.hold()
        sister = self.tmp / "E drive" / "Sister"
        doc = CM.clone(self.src, sister, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        self.assertEqual(self.approval_files(self.src), before)
        self.assertEqual(CM.approvals(self.src), self.held)
        self.assertEqual(CM.approvals(sister), {})
        self.assertEqual(CM.still_void(sister), [])
        self.assertFalse((sister / CM.VOIDED_REL).exists())
        self.assertEqual(doc["outside_database"]["voided"], [])

    def test_a_moved_clients_record_is_not_cloned(self):
        self.hold()
        CM.move(self.src, self.dest, apply=True)
        self.hold(self.dest)
        sister = self.tmp / "E drive" / "Sister"
        self.assertTrue(CM.clone(self.dest, sister, apply=True).get("applied"))
        self.assertFalse((sister / CM.VOIDED_REL).exists())


class TestWhereBeforeIsRead(Approved):
    def test_a_move_reads_the_approvals_in_the_old_folder(self):
        """A fingerprint may read the client folder itself (a motion plan's music): what held is read where it held."""
        from unittest import mock
        self.hold()
        with mock.patch.object(CM, "approvals", wraps=CM.approvals) as spy:
            self.assertTrue(CM.move(self.src, self.dest, apply=True).get("applied"))
        self.assertEqual([Path(c.args[0]) for c in spy.call_args_list], [self.src, self.dest])

    def test_a_stray_reels_file_in_a_clip_folder_is_no_approval(self):
        write_json(Paths(self.src, "R01").p("01_analysis/reels-plan-validated.json"), {"fingerprint": "x"})
        self.assertNotIn(("projects", "R01", "reels-plan"), CM.approvals(self.src))


class TestCantTell(Approved):
    def test_an_approval_that_cant_be_checked_is_listed_never_taken_as_held(self):
        q = Paths(self.src, "R01")
        q.p("01_analysis/cut-proposals.json").write_text("{damaged", encoding="utf-8")
        held = CM.approvals(self.src)
        self.assertIsNone(held[("projects", "R01", "cut-proposals")])
        self.assertEqual(CM._voided(self.src, held, CM.approvals(self.src),
                                    {"output/projects/R01/02_transcription/words.json"}),
                         [CM._entry("projects", "R01", "cut-proposals")])

    def test_one_on_an_item_the_move_did_not_touch_is_not_blamed_on_it(self):
        """Review r1 P3-2: a damaged cut-proposals file whose words name no path: neither forecast nor listed."""
        r5 = Paths(self.src, "R05")
        write_json(r5.p("02_transcription/words.json"), {"words": []})
        r5.p("01_analysis").mkdir(parents=True, exist_ok=True)
        r5.p("01_analysis/cut-proposals.json").write_text("{damaged", encoding="utf-8")
        self.assertIsNone(CM.approvals(self.src)[("projects", "R05", "cut-proposals")])
        dry = CM.move(self.src, self.dest)
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        for d in (dry, doc):
            self.assertNotIn("R05", [v["item"] for v in d["approvals_to_redo"]])


class TestPartialRewrite(Approved):
    """Review r1 P1-1, P1-2, P2-1: a rewrite that fails part way still lists (and records) what it voided; the old
    transcript check is pinned only after its words were rewritten; a damaged check is no new failure."""
    def failing(self, name: str):
        from unittest import mock
        real = CM.linksafe.replace_atomic

        def fake(path, *a, **kw):
            if str(path).replace("\\", "/").endswith(name):
                raise PermissionError(13, "held by another program", str(path))
            return real(path, *a, **kw)
        return mock.patch.object(CM.linksafe, "replace_atomic", fake)

    def hand(self) -> Path:
        hand = self.tmp / "by hand"
        shutil.copytree(self.src, hand, copy_function=shutil.copy2)
        self.hold(hand)
        return hand

    def test_an_error_still_lists_and_records_what_was_voided(self):
        hand = self.hand()
        with self.failing("R01/00_inputs/preflight.json"):
            doc = CM.already_moved(hand, apply=True)
        self.assertIn("preflight.json", doc["error"])
        self.assertEqual(self.keys(doc["approvals_to_redo"]), self.ALL)
        self.assertEqual(self.keys(CM.still_void(hand)), self.ALL)
        self.assertTrue((hand / CM.PENDING_REL).is_file())              # review r3 R3-P2-1: the old folder is kept
        self.assertEqual(CM.unmigrated(hand)["copied_from"], str(self.src))   # still refused before any read
        self.assertNotIn("refused", CM.already_moved(hand, old=str(self.src)))    # --from the old folder: accepted
        self.assertNotIn("refused", CM.already_moved(hand, old=str(self.src) + os.sep))       # r4 P3-2: any spelling
        self.assertIn("did not finish", CM.unmigrated(hand)["refused"])                     # r4 P3-1: says what is true
        again = CM.already_moved(hand, apply=True)                      # the file is free again: the rerun completes
        self.assertNotIn("error", again)
        self.assertEqual(again["old_root"], str(self.src))
        self.assertEqual(read_json(hand / "output/projects/R01/00_inputs/preflight.json")["media"],
                         str(hand / "data/Raw/clip 1.mp4"))                # the rerun really rewrote it
        self.assertFalse((hand / CM.PENDING_REL).exists())
        self.assertIsNone(CM.unmigrated(hand))
        self.assertEqual(self.keys(CM.still_void(hand)), self.ALL)
        self.assertEqual(sorted(self.keys(again["approvals_to_redo"])), self.ALL)     # review r3 P3-4

    def test_a_hostile_pending_marker_is_ignored(self):
        hand = self.hand()
        for bad in ("C:\\", "/", str(Path.home()), str(hand), str(hand.parent), "relative/x", 7,
                    str(hand / "data"), str(hand / "output" / "x")):                  # r4 P3-4: inside the client
            write_json(hand / CM.PENDING_REL, {"old_root": bad})
            self.assertEqual(CM.detect_old_root(hand), str(self.src), bad)
        (hand / CM.PENDING_REL).write_text("{damaged", encoding="utf-8")
        self.assertEqual(CM.detect_old_root(hand), str(self.src))

    def test_a_clean_run_leaves_no_marker_and_a_dry_run_writes_none(self):
        hand = self.hand()
        CM.already_moved(hand)
        self.assertFalse((hand / CM.PENDING_REL).exists())
        self.assertFalse((hand / CM.VOIDED_REL).exists())
        doc = CM.already_moved(hand, apply=True)
        self.assertNotIn("error", doc)
        self.assertFalse((hand / CM.PENDING_REL).exists())

    def test_a_damaged_database_file_does_not_lock_the_client(self):
        """Review r4 P3-1: a damaged typography.json can't be rewritten by a rerun either; `reel client-db` makes it
        again. The run says so, and the client is not refused as an unfinished copy."""
        hand = self.hand()
        (hand / "output/client_database/branding/typography.json").write_text("{damaged", encoding="utf-8")
        doc = CM.already_moved(hand, apply=True)
        self.assertIn("typography.json", doc["error"])
        self.assertFalse((hand / CM.PENDING_REL).exists())
        self.assertIsNone(CM.unmigrated(hand))

    def test_an_older_entrys_hash_is_kept_by_the_forecast(self):
        """Review r4 P3-3: the forecast never replaces an older entry; only a run that voids it again does."""
        hand = self.hand()
        write_json(hand / CM.VOIDED_REL, {"voided": [{"folder": "projects", "item": "R01", "kind": "plan",
                                                      "sha1": "0" * 40}]})
        with self.failing("R01/01_analysis/timeline-spec.json"):
            CM.already_moved(hand, apply=True)
        rec = {(v["folder"], v["item"], v["kind"]): v["sha1"] for v in read_json(hand / CM.VOIDED_REL)["voided"]}
        self.assertEqual(rec[("projects", "R01", "plan")], "0" * 40)

    def test_an_older_entry_is_not_dropped_by_this_runs_forecast(self):
        """Review r3 P3-2: an older move's entry the forecast lists again stays when this run's rewrite failed."""
        hand = self.hand()
        (hand / "output/projects/R01/01_analysis/cut-proposals.json").write_text("{damaged", encoding="utf-8")
        write_json(hand / CM.VOIDED_REL, {"voided": [{"folder": "projects", "item": "R01", "kind": "cut-proposals"}]})
        with self.failing("R01/02_transcription/words.json"):
            CM.already_moved(hand, apply=True)
        rec = read_json(hand / CM.VOIDED_REL)["voided"]
        self.assertIn(("projects", "R01", "cut-proposals"), [(v["folder"], v["item"], v["kind"]) for v in rec])

    def test_the_old_check_is_not_pinned_when_its_words_were_not_rewritten(self):
        hand = self.hand()
        vf = hand / "output/projects/R04/02_transcription/verification.json"
        raw = vf.read_bytes()
        with self.failing("R04/02_transcription/words.json"):
            doc = CM.already_moved(hand, apply=True)
        self.assertIn("words.json", doc["error"])
        self.assertEqual(vf.read_bytes(), raw)                          # never given a hash it was not given for
        self.assertNotIn(("projects", "R04", "transcript"), self.keys(doc["approvals_to_redo"]))

    def test_an_old_check_that_cant_be_pinned_is_listed(self):
        hand = self.hand()
        with self.failing("R04/02_transcription/verification.json"):
            doc = CM.already_moved(hand, apply=True)
        self.assertIn("verification.json", doc["error"])
        self.assertIn(("projects", "R04", "transcript"), self.keys(doc["approvals_to_redo"]))
        self.assertIn(("projects", "R04", "transcript"), self.keys(CM.still_void(hand)))

    def test_a_damaged_check_is_listed_and_the_move_goes_through(self):
        vf = self.src / "output/projects/R04/02_transcription/verification.json"
        vf.write_text("{damaged", encoding="utf-8")
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        self.assertTrue(doc.get("applied"), doc)
        self.assertIn(("projects", "R04", "transcript"), self.keys(doc["approvals_to_redo"]))
        self.assertEqual((self.dest / "output/projects/R04/02_transcription/verification.json").read_text(
            encoding="utf-8"), "{damaged")

    def test_a_linked_check_is_never_written_through(self):
        target = self.tmp / "elsewhere"
        target.mkdir()
        (target / "v.json").write_text('{"verified": true, "by": "editor"}', encoding="utf-8")
        hand = self.hand()
        vf = hand / "output/projects/R04/02_transcription/verification.json"
        vf.unlink()
        try:
            os.symlink(target / "v.json", vf)
        except OSError:
            self.skipTest("file symlinks need Developer Mode / admin on Windows (macOS CI runs it)")
        doc = CM.already_moved(hand, apply=True)
        self.assertIn("is a link", doc["error"])
        self.assertEqual((target / "v.json").read_text(encoding="utf-8"), '{"verified": true, "by": "editor"}')
        self.assertIn(("projects", "R04", "transcript"), self.keys(doc["approvals_to_redo"]))

    def test_a_linked_check_never_given_is_not_listed(self):
        """Review r2 N-P3-2."""
        target = self.tmp / "elsewhere"
        target.mkdir()
        (target / "v.json").write_text('{"verified": false, "by": "editor"}', encoding="utf-8")
        hand = self.hand()
        vf = hand / "output/projects/R04/02_transcription/verification.json"
        vf.unlink()
        try:
            os.symlink(target / "v.json", vf)
        except OSError:
            self.skipTest("file symlinks need Developer Mode / admin on Windows (macOS CI runs it)")
        doc = CM.already_moved(hand, apply=True)
        self.assertNotIn(("projects", "R04", "transcript"), self.keys(doc["approvals_to_redo"]))


class TestStoppedPartWay(Approved):
    """Review r2 N-P2-1: a run stopped part way (an error that escapes, Ctrl+C, a crash) still lists what it voided:
    the forecast is recorded before anything is rewritten."""
    def hand(self) -> Path:
        hand = self.tmp / "by hand"
        shutil.copytree(self.src, hand, copy_function=shutil.copy2)
        self.hold(hand)
        return hand

    def listed_is_what_does_not_hold(self, root: Path):
        """Every approval that no longer holds is listed. The one extra allowed: a transcript check of the old form
        (no hash), listed before its words were rewritten (a rerun rewrites them and voids it anyway)."""
        now = CM.approvals(root)
        want = {k for k in self.ALL if now[k] is not True}
        got = set(self.keys(CM.still_void(root)))
        self.assertTrue(want)
        self.assertLessEqual(want, got)
        self.assertLessEqual(got - want, {("projects", "R04", "transcript")})

    def test_stopped_in_the_middle_of_the_files(self):
        from unittest import mock
        real = CM.linksafe.replace_atomic

        def fake(path, *a, **kw):
            if str(path).replace("\\", "/").endswith("R02/01_analysis/motion-script.json"):
                raise KeyboardInterrupt
            return real(path, *a, **kw)
        hand = self.hand()
        with mock.patch.object(CM.linksafe, "replace_atomic", fake), self.assertRaises(KeyboardInterrupt):
            CM.already_moved(hand, apply=True)
        self.listed_is_what_does_not_hold(hand)
        self.assertIn(("projects", "R01", "plan"), self.keys(CM.still_void(hand)))     # rewritten before the stop
        again = CM.already_moved(hand, apply=True)                     # the rerun names them all (review r3 P3-4)
        self.assertNotIn("error", again)
        self.assertEqual(sorted(self.keys(again["approvals_to_redo"])), self.ALL)

    def test_stopped_between_the_words_and_the_old_check(self):
        from unittest import mock
        hand = self.hand()
        with mock.patch.object(CM, "_pin_transcript_check", side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            CM.already_moved(hand, apply=True)
        from lib import transcribe
        self.assertTrue(transcribe.transcript_verified(Paths(hand, "R04")))          # the old form, not pinned
        self.assertIn(("projects", "R04", "transcript"), self.keys(CM.still_void(hand)))

    def test_a_file_nested_too_deep_is_kept_and_the_run_completes(self):
        hand = self.hand()
        deep = hand / "output/projects/R01/00_inputs/preflight.json"
        deep.write_text("[" * 200000 + json.dumps(str(self.src / "data/Raw/clip 1.mp4")) + "]" * 200000,
                        encoding="utf-8")
        doc = CM.already_moved(hand, apply=True)
        self.assertNotIn("error", doc)
        self.assertIn("output/projects/R01/00_inputs/preflight.json", [k["file"] for k in doc["outside_database"]["kept"]])
        self.assertEqual(self.keys(CM.still_void(hand)), self.ALL)

    def test_stopped_after_the_old_check_was_pinned(self):
        from unittest import mock
        real = CM._voided

        def stop_at_the_end(root, before, after, *a, **kw):
            if after is not None:
                raise KeyboardInterrupt
            return real(root, before, after, *a, **kw)
        hand = self.hand()
        with mock.patch.object(CM, "_voided", stop_at_the_end), self.assertRaises(KeyboardInterrupt):
            CM.already_moved(hand, apply=True)
        self.assertIn("words_sha1", read_json(hand / "output/projects/R04/02_transcription/verification.json"))
        self.assertEqual(self.keys(CM.still_void(hand)), self.ALL)
        rec = {(v["folder"], v["item"], v["kind"]): v["sha1"] for v in read_json(hand / CM.VOIDED_REL)["voided"]}
        self.assertTrue(all(isinstance(h, str) for k, h in rec.items() if k[2] != "transcript"), rec)   # r3 P3-3
        self.assertTrue(all(h is None for k, h in rec.items() if k[2] == "transcript"), rec)

    def test_a_forecast_entry_that_did_not_void_is_dropped(self):
        """A plan whose old-folder path is only in a part its fingerprint leaves out ("generated"): rewritten, still
        approved. The dry run forecasts it (it can't know); the applied run neither lists nor records it."""
        r6 = Paths(self.src, "R06")
        write_json(r6.p("01_analysis/timeline-spec.json"), {"events": [], "generated": f"built in {self.src}"})
        write_json(r6.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                             "format": PL.APPROVAL_FORMAT,
                                                             "plan_fingerprint": PL.plan_fingerprint(r6)})
        hand = self.hand()
        self.assertIn(("projects", "R06", "plan"), self.keys(CM.already_moved(hand)["approvals_to_redo"]))
        doc = CM.already_moved(hand, apply=True)
        self.assertNotIn(("projects", "R06", "plan"), self.keys(doc["approvals_to_redo"]))
        self.assertEqual(PL.approval_state(Paths(hand, "R06"))["state"], "current")
        rec = read_json(hand / CM.VOIDED_REL)["voided"]
        self.assertNotIn(("projects", "R06", "plan"), [(v["folder"], v["item"], v["kind"]) for v in rec])

    def test_the_final_list_replaces_the_forecast(self):
        hand = self.hand()
        CM.already_moved(hand, apply=True)
        rec = read_json(hand / CM.VOIDED_REL)["voided"]
        self.assertEqual(sorted((v["folder"], v["item"], v["kind"]) for v in rec), self.ALL)
        self.assertTrue(all(isinstance(v["sha1"], str) for v in rec), rec)


class TestRecordLifetime(Approved):
    def moved(self):
        self.hold()
        self.assertTrue(CM.move(self.src, self.dest, apply=True).get("applied"))

    def test_given_again_then_replanned_is_no_move_line(self):
        """Review r1 P3-1: once the editor approved again, a later re-plan is the usual flow, not "client moved"."""
        self.moved()
        q = Paths(self.dest, "R01")
        write_json(q.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                            "format": PL.APPROVAL_FORMAT,
                                                            "plan_fingerprint": PL.plan_fingerprint(q)})
        write_json(q.p("01_analysis/timeline-spec.json"), {"media": "data/Raw/clip 1.mp4", "replanned": True})
        self.assertEqual(PL.approval_state(q)["state"], "stale")
        self.assertNotIn(("projects", "R01", "plan"), self.keys(CM.still_void(self.dest)))

    def test_a_replan_before_approving_again_keeps_the_line(self):
        """Review r2 N-P3-1: a re-plan marks the approval "stale"; that is no approval given again."""
        self.moved()
        f = self.dest / "output/projects/R01/01_analysis/plan-approval.json"
        appr = read_json(f)
        appr["stale"] = True
        write_json(f, appr)
        self.assertIn(("projects", "R01", "plan"), self.keys(CM.still_void(self.dest)))

    def test_an_entry_without_a_hash_goes_once_it_holds(self):
        self.moved()
        write_json(self.dest / CM.VOIDED_REL, {"voided": [{"folder": "projects", "item": "R01", "kind": "plan"}]})
        self.assertEqual(self.keys(CM.still_void(self.dest)), [("projects", "R01", "plan")])
        q = Paths(self.dest, "R01")
        write_json(q.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                            "format": PL.APPROVAL_FORMAT,
                                                            "plan_fingerprint": PL.plan_fingerprint(q)})
        self.assertEqual(CM.still_void(self.dest), [])

    def test_an_item_that_climbs_out_is_never_read(self):
        self.moved()
        out = self.dest / "assets" / "x" / "01_analysis"
        out.mkdir(parents=True)
        (out / "plan-approval.json").write_text('{"approved": true}', encoding="utf-8")
        write_json(self.dest / CM.VOIDED_REL, {"voided": [{"folder": "projects", "item": "../../assets/x",
                                                           "kind": "plan"}]})
        self.assertEqual(CM.still_void(self.dest), [])

    def test_a_record_with_hostile_types_breaks_nothing(self):
        """Review r1 P2-2: lists, numbers, nested objects in a record entry are skipped, the move goes through."""
        write_json(self.src / CM.VOIDED_REL, {"voided": [
            {"folder": ["x"], "item": "R01", "kind": "plan"}, {"folder": "projects", "item": {"a": 1}, "kind": "plan"},
            {"folder": "projects", "item": "R01", "kind": ["plan"]}, {"folder": "projects", "item": "R01",
                                                                       "kind": "plan", "sha1": ["x"]}]})
        self.assertEqual(CM.still_void(self.src), [])
        self.moved()
        rec = read_json(self.dest / CM.VOIDED_REL)["voided"]
        self.assertEqual(sorted((v["folder"], v["item"], v["kind"]) for v in rec), self.ALL)
        self.assertEqual(self.keys(CM.still_void(self.dest)), self.ALL)


if __name__ == "__main__":
    unittest.main()
