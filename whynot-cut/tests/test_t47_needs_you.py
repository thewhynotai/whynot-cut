# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.7 — no-questions autopilot + one checklist.

`reel needs-you [--write]` READS the client's state and aggregates one list of what only the editor can do: words to
confirm by ear, medical / religious approvals, music, fonts and logo missing, the final mix and render, and what the
website run found. Producers write `needs_you: [{kind, text, text_ar?, why, ref}]` into their own state file (the T4.6
motion plan, the Addendum J website run); the rest is derived from state that exists today. `--write` puts
output/NEEDS-YOU.md (Arabic first, then English, editor words) and its JSON twin output/needs-you.json in output/ only,
atomically, byte-identical when nothing changed. `reel auto-approve` records a plan approval `by: "auto"` only for a
client whose preferences say `approval: auto`; medical and religious approvals are never automatic.
Case list: D:/ClaudeData/Temp/wnc-p4/t47/cases.md (case ids in the test names).
Run:  bash tools/test.sh -p test_t47_needs_you.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import common  # noqa: E402
from lib import plat  # noqa: E402
from lib import review_flags as RF  # noqa: E402
from lib import schemas  # noqa: E402
from lib.common import Paths, read_json, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

CLI = SK / "engine/reel/cli.py"
GUARD = SK / "hooks" / "guard.py"
VID = "C0001"
FSI, PDI = "\u2068", "\u2069"
AR_WORD = "الكلى"
AR_PRODUCER = "ضيف مزيكا مرخّصة في data/Music — الموسيقى الحالية مش مرخّصة"
SESSION_ENV = ("WHYNOT_LOCK_SESSION", "CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID")
# developer words the editor must never read in the derived text of NEEDS-YOU.md
JARGON = re.compile(r"(?i)\bjson\b|\.json|\bschema\b|fingerprint|\bref\b|\bkind\b|plan id|stdout|stderr|traceback|"
                    r"\blease\b|\breel [a-z]|(?<![\w-])--[a-z]|\bnull\b|(?-i:\bNone\b|\bTrue\b|\bFalse\b)|\bsource file\b")


def NY():
    from lib import needs_you
    return needs_you


def AP():
    from lib import autopilot
    return autopilot


def cli_module():
    spec = importlib.util.spec_from_file_location("reel_cli_t47", CLI)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def env(session="t47-me"):
    from test_plugin import isolated_env
    e = {k: v for k, v in isolated_env().items() if k not in SESSION_ENV}
    if session:
        e["CLAUDE_CODE_SESSION_ID"] = session
    return e


def reel(root, *argv, session="t47-me"):
    r = subprocess.run([sys.executable, "-B", str(CLI), "--root", str(root), *argv], capture_output=True, text=True,
                       encoding="utf-8", env=env(session))
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = r.stdout
    return r.returncode, doc, r.stderr


def make_client(tmp: Path, name: str = "Dr Test د. تجربة") -> Path:
    root = tmp / name                                    # spaces + Arabic in the client folder
    for d in ("assets/Brand", "data/Raw"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text("{}", encoding="utf-8")
    return root


def prefs(root: Path, **kv) -> Path:
    f = root / ".claude" / "whynot-cut.local.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("---\n" + "".join(f"{k}: {v}\n" for k, v in kv.items()) + "---\n", encoding="utf-8")
    return f


def profile(root: Path, name: str, doc: dict):
    write_json(root / "output/client_database/reel-profile" / name, doc)


def word(i, w, ms, prob=0.95, flagged=None) -> dict:
    d = {"id": i, "word": w, "start_ms": ms, "end_ms": ms + 300, "probability": prob}
    if flagged:
        d["flagged"] = {"note": flagged}
    return d


def put_words(p: Paths, words: list) -> Path:
    return write_json(p.p("02_transcription/words.json"), {"meta": {"language": "ar"}, "words": words})


def verify(p: Paths, by="editor"):
    sha = hashlib.sha1(p.p("02_transcription/words.json").read_bytes()).hexdigest()
    write_json(p.p("02_transcription/verification.json"), {"verified": True, "by": by, "at": "x", "note": "",
                                                            "words_sha1": sha})


def event(eid, a, b, approval=False, **params) -> dict:
    return {"event_id": eid, "decision_id": "D" + eid[1:], "template": "glass_card", "start_ms": a, "end_ms": b,
            "start_frame": a * 30 // 1000, "end_frame": b * 30 // 1000, "params": params,
            "approval_required": approval}


def put_spec(p: Paths, events=None, music="MARKERS_ONLY") -> dict:
    spec = {"fps": 30, "duration_frames": 900, "generated": "2026-10-17T09:00:00+00:00", "main_segments": [],
            "events": events if events is not None else [
                event("G1", 1000, 3500, text="مقدمة"),
                event("G2", 4000, 7250, approval=True, headline="Take 500 mg daily")],
            "music": {"status": music}}
    write_json(p.p("01_analysis/timeline-spec.json"), spec)
    write_json(p.p("01_analysis/plan-validation.json"), {"ok": True, "errors": [], "warnings": []})
    return spec


def full_review(p: Paths, ids=("G1", "G2"), flag="medical") -> dict:
    return RF.write(p, {"items": [{"event_id": i, "flag": flag, "verdict": "ok", "reason": ""} for i in ids]})


def put_motion(p: Paths, needs=None, music=None, approvals=()):
    write_json(p.p("00_inputs/source.json"), {"kind": "motion_reel", "language": "ar"})
    doc = {"reel_id": p.video_id, "fps": 24, "duration_frames": 240, "scenes": [],
           "audio": {"music": music}, "approvals": list(approvals)}
    if needs is not None:
        doc["needs_you"] = needs
    write_json(p.p("01_analysis/motion-plan.json"), doc)
    return doc


def need(kind="music", ref="data/Music", text="Add licensed music", text_ar=AR_PRODUCER, why="no licence") -> dict:
    d = {"kind": kind, "text": text, "why": why, "ref": ref}
    if text_ar is not None:
        d["text_ar"] = text_ar
    return d


def inventory(root: Path, files=()) -> Path:
    return write_json(root / "output/discovery/input-inventory.json", {"files": list(files)})


def inv_file(root: Path, rel: str, role: str, kind: str) -> dict:
    return {"rel": rel, "path": str(root / rel), "role": role, "kind": kind, "size_bytes": 1}


def tree(folder: Path) -> dict:
    out = {}
    for dp, dns, fns in os.walk(folder):
        for n in dns + fns:
            q = Path(dp) / n
            st = q.lstat()
            out[str(q.relative_to(folder))] = (st.st_size, st.st_mtime_ns)
    return out


def dir_link(link: Path, target: Path):
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def by_kind(doc, kind):
    return [i for i in doc["items"] if i["kind"] == kind]


def ar_part(md: str) -> str:
    return md.split("\n# Needs you", 1)[0]


def plain(s: str) -> str:
    return s.replace(FSI, "").replace(PDI, "")


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)
        self.root = make_client(self.tmp)
        common.set_context(self.root)
        self.addCleanup(common.set_context, None, None)
        self.p = Paths(self.root, VID)

    def collect(self):
        return NY().collect(self.root)


# --------------------------------------------------------------------------- inputs and state
class TestInputs(Base):
    def test_C1_empty_client(self):
        doc = self.collect()
        self.assertEqual((doc["items"], doc["total"], doc["unread"], doc["skipped"]), ([], 0, [], []))
        r = NY().write(self.root)
        self.assertTrue(r["ok"])
        md = (self.root / "output/NEEDS-YOU.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith("# مطلوب منك"), md[:40])
        self.assertIn("لا شيء مطلوب منك الآن.", md)
        self.assertIn("Nothing needs you right now.", md)
        self.assertLess(md.index("لا شيء مطلوب منك الآن."), md.index("Nothing needs you right now."))
        twin = read_json(self.root / "output/needs-you.json")
        self.assertEqual(twin["items"], [])
        self.assertEqual(schemas.validate(twin, "needs-you"), [])

    def test_C2_read_only_writes_nothing(self):
        before = tree(self.root)
        code, doc, err = reel(self.root, "needs-you")
        self.assertEqual(code, 0, err)
        self.assertEqual(doc["total"], 0)
        self.assertFalse(doc["written"])
        self.assertEqual(tree(self.root), before)
        self.assertFalse((self.root / "output").exists())

    def test_C3_truncated_state_is_named_not_fatal(self):
        inventory(self.root)                                      # no logo, no fonts -> two items still listed
        self.p.p("02_transcription").mkdir(parents=True)
        self.p.p("02_transcription/words.json").write_text('{"words": [{"id": 1, "wo', encoding="utf-8")
        typ = self.root / "output/client_database/branding/typography.json"
        typ.parent.mkdir(parents=True)
        typ.write_bytes(b"\xff\xfe garbage")
        doc = self.collect()
        srcs = {u["source"] for u in doc["unread"]}
        self.assertIn(f"output/projects/{VID}/02_transcription/words.json", srcs)
        self.assertIn("output/client_database/branding/typography.json", srcs)
        self.assertEqual({i["kind"] for i in doc["items"]}, {"fonts", "logo"})
        NY().write(self.root)
        md = (self.root / "output/NEEDS-YOU.md").read_text(encoding="utf-8")
        self.assertIn("ممكن تكون ناقصة", md)
        self.assertIn("may be missing items", md)
        self.assertIn(VID, md)

    def test_C4_wrong_types(self):
        put_motion(self.p, needs={"kind": "music"})               # needs_you is not a list
        p2 = Paths(self.root, "C0002")
        put_motion(p2, needs=["text", {"kind": "music", "text": 5, "why": "x", "ref": "data/Music"},
                              need(ref="data/Music/a.wav")])
        p3 = Paths(self.root, "C0003")
        put_words(p3, [])
        write_json(p3.p("02_transcription/words.json"), {"words": "abc"})
        doc = self.collect()                                     # never a crash
        skipped = [s["source"] for s in doc["skipped"]]
        self.assertIn(f"output/projects/{VID}/01_analysis/motion-plan.json", skipped)
        self.assertEqual(skipped.count("output/projects/C0002/01_analysis/motion-plan.json"), 2)
        self.assertEqual([i["ref"] for i in by_kind(doc, "music") if i["item"] == "C0002"], ["data/Music/a.wav"])
        self.assertIn("output/projects/C0003/02_transcription/words.json",
                      [u["source"] for u in doc["unread"]] + skipped)
        self.assertEqual(schemas.validate(doc, "needs-you"), [])

    def test_C5_unknown_kind_skipped(self):
        put_motion(self.p, needs=[need(kind="approve"), need(kind="music2"), need()])
        doc = self.collect()
        self.assertEqual([i["kind"] for i in doc["items"]], ["music"])
        whys = " ".join(s["why"] for s in doc["skipped"])
        self.assertIn("approve", whys)
        self.assertIn("music2", whys)

    def test_C6_dedupe_contract_key(self):
        put_motion(self.p, needs=[need(), need(text="again, other words")])          # same (source, kind, ref)
        put_motion(Paths(self.root, "C0002"), needs=[need()])                         # same kind/ref, other source
        doc = self.collect()
        music = by_kind(doc, "music")
        self.assertEqual([(i["item"], i["text"]) for i in music], [(VID, "Add licensed music"),
                                                                    ("C0002", "Add licensed music")])
        self.assertEqual(len({i["id"] for i in doc["items"]}), len(doc["items"]))

    def test_C6b_review_flag_wins_over_spec_flag(self):
        put_spec(self.p)
        RF.write(self.p, {"items": [{"event_id": "G1", "flag": "medical", "verdict": "ok", "reason": ""},
                                    {"event_id": "G2", "flag": "medical", "verdict": "needs-doctor-approval",
                                     "reason": "the dose"}]})
        doc = self.collect()
        med = by_kind(doc, "medical")
        self.assertEqual([(i["ref"], i["source"]) for i in med], [("G2", f"output/projects/{VID}/review-flags.json")])
        self.assertIn("the dose", med[0]["why"])

    def test_C7_refs(self):
        out = self.tmp / "elsewhere"
        out.mkdir()
        put_motion(self.p, needs=[need(ref="data/Music/gone.wav"), need(ref="../outside.txt"),
                                  need(ref=str(out / "x.wav")), need(ref=str(self.root / "data" / "Raw")),
                                  need(ref="data\\Raw\\b.wav"), need(kind="words", ref="S3")])
        doc = self.collect()
        got = {i["ref"]: i.get("ref_exists") for i in doc["items"]}
        self.assertEqual(got, {"data/Music/gone.wav": False, "data/Raw": True, "data/Raw/b.wav": False, "S3": None})
        self.assertNotIn("ref_exists", next(i for i in doc["items"] if i["ref"] == "S3"))
        self.assertEqual(len(doc["skipped"]), 2)

    def test_C8_byte_identical_rerun(self):
        put_spec(self.p)
        put_words(self.p, [word(1, AR_WORD, 1200, flagged="dose?")])
        inventory(self.root)
        r1 = NY().write(self.root)
        md, js = self.root / "output/NEEDS-YOU.md", self.root / "output/needs-you.json"
        b1, t1 = (md.read_bytes(), js.read_bytes()), (md.stat().st_mtime_ns, js.stat().st_mtime_ns)
        self.assertFalse(r1["unchanged"])
        time.sleep(0.05)
        r2 = NY().write(self.root)
        self.assertTrue(r2["unchanged"])
        self.assertEqual((md.read_bytes(), js.read_bytes()), b1)
        self.assertEqual((md.stat().st_mtime_ns, js.stat().st_mtime_ns), t1)
        self.assertNotIn(b"\r\n", b1[0] + b1[1])                 # LF on every platform

    def test_C8b_resolved_items_disappear(self):
        put_words(self.p, [word(1, AR_WORD, 1200, flagged="dose?")])
        put_spec(self.p)
        inventory(self.root)
        NY().write(self.root)
        kinds = {i["kind"] for i in read_json(self.root / "output/needs-you.json")["items"]}
        self.assertEqual(kinds, {"words", "medical", "music", "fonts", "logo"})
        verify(self.p, "editor")                                       # the editor confirmed the words
        put_spec(self.p, events=[event("G1", 1000, 3500, text="مقدمة")], music="PLACED")   # re-plan: approved, music in
        inventory(self.root, [inv_file(self.root, "assets/Logo/logo.png", "logo", "image"),
                              inv_file(self.root, "assets/Fonts/Brand.otf", "font", "font")])
        r = NY().write(self.root)
        self.assertFalse(r["unchanged"])
        self.assertEqual(read_json(self.root / "output/needs-you.json")["items"], [])


class TestWriteSafety(Base):
    def test_C9_other_session_lease_refuses(self):
        import socket
        lock = self.root / "output/.whynot-lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(json.dumps({"session_id": "other-session", "pid": os.getpid(), "host": socket.gethostname(),
                                    "started_at": "2026-10-17T10:00:00+03:00", "command": "reel plan"}),
                        encoding="utf-8")
        code, doc, err = reel(self.root, "needs-you", "--write")
        self.assertEqual(code, 2, (doc, err))
        self.assertIn("blocked", doc)
        self.assertFalse((self.root / "output/NEEDS-YOU.md").exists())
        self.assertFalse((self.root / "output/needs-you.json").exists())

    def test_C9b_atomic_replace_leaves_no_tmp(self):
        put_motion(self.p, needs=[need()])
        NY().write(self.root)
        md = self.root / "output/NEEDS-YOU.md"
        old = md.read_bytes()
        put_motion(self.p, needs=[need(ref="data/Music/x.wav")])
        with mock.patch("os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                NY().write(self.root)
        self.assertEqual(md.read_bytes(), old)                        # the reader still sees the whole old file
        self.assertEqual([f.name for f in (self.root / "output").iterdir() if f.name.endswith(".tmp")], [])

    def test_R1_not_a_client(self):
        nc = self.tmp / "not a client"
        nc.mkdir()
        code, doc, err = reel(nc, "needs-you", "--write")
        self.assertEqual(code, 1, (doc, err))
        self.assertFalse((nc / "output").exists())

    def test_R2_never_into_data_or_assets(self):
        target = self.root / "data" / "out"
        target.mkdir()
        dir_link(self.root / "output", target)
        before = tree(self.root / "data")
        with self.assertRaises(Guidance):
            NY().write(self.root)
        self.assertEqual(tree(self.root / "data"), before)

    def test_R3_invalid_document_is_never_written(self):
        bad = {"schema_version": 1, "client": "x", "items": [{"id": "1", "kind": "nope"}], "counts": {}, "total": 1,
               "unread": [], "skipped": []}
        with mock.patch.object(NY(), "collect", return_value=bad):
            with self.assertRaises(Guidance):
                NY().write(self.root)
        self.assertFalse((self.root / "output/NEEDS-YOU.md").exists())
        self.assertFalse((self.root / "output/needs-you.json").exists())


class TestTextAndLanguage(Base):
    def rich(self):
        put_words(self.p, [word(1, AR_WORD, 1200, flagged="dose?"), word(2, "mg", 61500, prob=0.2)])
        put_spec(self.p)
        common.set_status(self.p, "QC_PASSED", "t")
        inventory(self.root)
        typ = {"families": {"Brand": {}}, "missing_or_uninstalled": [str(self.root / "assets/Fonts/Brand_Bold.otf")]}
        write_json(self.root / "output/client_database/branding/typography.json", typ)
        p2 = Paths(self.root, "C0002")
        put_motion(p2, needs=[need()], approvals=["S3: number 40 written from the spoken words «أربعين»"])

    def test_C10_arabic_and_space_paths(self):
        self.rich()
        r = NY().write(self.root)
        twin = read_json(self.root / "output/needs-you.json")
        self.assertEqual(twin["client"], "Dr Test د. تجربة")
        prod = next(i for i in twin["items"] if i["item"] == "C0002" and i["kind"] == "music")
        self.assertEqual(prod["text_ar"], AR_PRODUCER)                  # verbatim, logical order
        md = (self.root / "output/NEEDS-YOU.md").read_bytes()
        self.assertFalse(md.startswith(b"\xef\xbb\xbf"))
        text = md.decode("utf-8")
        self.assertIn(AR_WORD, text)
        self.assertIn(plain(AR_PRODUCER), plain(text))
        self.assertIn("- C0002: Add licensed music", text)                # a producer line names its video
        self.assertIn("- C0002: " + plain(AR_PRODUCER), plain(text))
        self.assertIn("اسمع كلمتين", text)                                # Arabic number agreement (2 words)
        self.assertEqual(r["files"]["md"], str(self.root / "output" / "NEEDS-YOU.md"))

    def test_C11_bidi_isolates_and_escaping(self):
        self.rich()
        put_motion(Paths(self.root, "C0003"), needs=[need(text="click [here](http://x.example) <b>x</b> `y` *z*",
                                                          text_ar="اضغط [هنا](http://x.example) <img src=x>")])
        put_motion(Paths(self.root, "C0004"), needs=[need(text="see https://evil.example/a?b=1. or www.evil.example now",
                                                          text_ar="شوف https://evil.example/a و www.evil.example")])
        NY().write(self.root)
        md = (self.root / "output/NEEDS-YOU.md").read_text(encoding="utf-8")
        self.assertIn("`https://evil.example/a?b=1`", md)
        self.assertIn("`www.evil.example`", md)
        bare = re.compile(r"(?<!`)(?:https?://|www\.)")                  # every URL starts a code span (no auto-link)
        self.assertEqual([plain(md)[m.start() - 5:m.end() + 10] for m in bare.finditer(plain(md))], [])
        ar = ar_part(md)
        self.assertLess(md.index("# مطلوب منك"), md.index("# Needs you"))
        self.assertIn(f"{FSI}{VID}{PDI}", ar)                            # Latin ids isolated inside Arabic lines
        self.assertNotIn(f"{FSI}{VID}{PDI}", md.split("# Needs you", 1)[1])
        for bad in ("](http", "<b>", "<img", "[here]"):
            self.assertNotIn(bad, md)
        self.assertIn("\\[", md)
        self.assertNotRegex(md, "[\u202a-\u202e]")

    def test_C12_no_developer_words(self):
        self.rich()
        put_motion(Paths(self.root, "C0009"))                            # derived music (no producer key)
        RF.write(self.p, {"items": [{"event_id": "G1", "flag": "medical", "verdict": "reword-to-match", "reason": "x"},
                                    {"event_id": "G2", "flag": "medical", "verdict": "remove", "reason": "y"}]})
        common.set_status(Paths(self.root, "C0002"), "READY_FOR_HUMAN_EDITOR", "t")
        NY().write(self.root)
        md = (self.root / "output/NEEDS-YOU.md").read_text(encoding="utf-8")
        kinds = {i["kind"] for i in read_json(self.root / "output/needs-you.json")["items"]}
        self.assertEqual(kinds, {"words", "medical", "music", "fonts", "logo", "final"})
        self.assertIsNone(JARGON.search(md), JARGON.search(md) and md[max(0, JARGON.search(md).start() - 60):
                                                                       JARGON.search(md).end() + 20])


# --------------------------------------------------------------------------- the sources
class TestSources(Base):
    def test_K1_words(self):
        put_words(self.p, [word(1, AR_WORD, 1200, flagged="dose?"), word(2, "ok", 2000), word(3, "mg", 61500, prob=0.2)])
        it = by_kind(self.collect(), "words")
        self.assertEqual(len(it), 1)
        self.assertEqual((it[0]["item"], it[0]["ref"]), (VID, f"output/projects/{VID}/02_transcription/subtitle-review.md"))
        self.assertIn(AR_WORD, it[0]["text"])
        self.assertIn("1:01", it[0]["text"])                              # the low-confidence word, m:ss
        self.assertNotIn("«ok»", it[0]["text"])
        for by in ("auto", "delegated", "claude", "agent", "transcript-editor", "Yunus", None):   # allow-list: editor
            verify(self.p, by)
            if by is None:
                vf = self.p.p("02_transcription/verification.json")
                write_json(vf, {k: v for k, v in read_json(vf).items() if k != "by"})
            got = by_kind(self.collect(), "words")
            self.assertEqual(len(got), 1, by)
            self.assertIn("may already be on a graphic", got[0]["why"], by)      # honest after another's check
            self.assertIn("ممكن تكون ظهرت على الجرافيك", got[0]["why_ar"], by)
        verify(self.p, "editor")
        self.assertEqual(by_kind(self.collect(), "words"), [])
        put_words(self.p, [word(1, AR_WORD, 1200, flagged="dose?")])     # changed after the check -> back
        self.assertEqual(len(by_kind(self.collect(), "words")), 1)

    def test_K1b_episode_reels_defer_to_the_episode(self):
        from lib.episode import EpisodePaths
        ep = EpisodePaths(self.root, "EP01")
        put_words(ep, [word(1, AR_WORD, 1200, flagged="?")])
        r = Paths(self.root, "EP01_R01")
        write_json(r.p("00_inputs/source.json"), {"kind": "episode_reel", "episode_id": "EP01", "in_ms": 0,
                                                   "out_ms": 5000})
        put_words(r, [word(1, AR_WORD, 1200, flagged="?")])
        self.assertEqual([i["item"] for i in by_kind(self.collect(), "words")], ["EP01"])
        verify(ep, "editor")
        self.assertEqual([i["item"] for i in by_kind(self.collect(), "words")], ["EP01_R01"])

    def test_K2_medical(self):
        put_spec(self.p)
        med = by_kind(self.collect(), "medical")
        self.assertEqual([(i["ref"], i["source"]) for i in med],
                         [("G2", f"output/projects/{VID}/01_analysis/timeline-spec.json")])
        self.assertIn("Take 500 mg daily", med[0]["text"])
        RF.write(self.p, {"items": [{"event_id": "G1", "flag": "medical", "verdict": "reword-to-match", "reason": "r"},
                                    {"event_id": "G2", "flag": "medical", "verdict": "ok", "reason": ""}]})
        self.assertEqual([i["ref"] for i in by_kind(self.collect(), "medical")], ["G1", "G2"])
        put_spec(self.p, events=[event("G1", 1000, 3600, text="مقدمة جديدة")])   # re-plan: the review is stale
        self.assertEqual(by_kind(self.collect(), "medical"), [])

    def test_K3_music(self):
        put_spec(self.p)
        self.assertEqual([(i["ref"], i["item"]) for i in by_kind(self.collect(), "music")], [("data/Music", VID)])
        profile(self.root, "style.json", {"music": "none (talking head only)"})
        self.assertEqual(by_kind(self.collect(), "music"), [])
        m = Paths(self.root, "M0001")
        put_motion(m)                                                     # no producer key, no music: derived
        self.assertEqual([i["item"] for i in by_kind(self.collect(), "music")], ["M0001"])
        put_motion(m, needs=[])                                           # the producer says: nothing needed
        self.assertEqual(by_kind(self.collect(), "music"), [])
        put_motion(m, needs=[need(ref="data/Music/x.wav")])
        self.assertEqual([i["source"] for i in by_kind(self.collect(), "music")],
                         ["output/projects/M0001/01_analysis/motion-plan.json"])

    def test_K4_fonts_logo(self):
        inventory(self.root)
        doc = self.collect()
        self.assertEqual([(i["kind"], i["ref"], i["item"]) for i in doc["items"]],
                         [("fonts", "assets/Fonts", None), ("logo", "assets/Logo", None)])
        inventory(self.root, [inv_file(self.root, "assets/Fonts/Brand_Bold.otf", "font", "font")])
        write_json(self.root / "output/client_database/branding/typography.json",
                   {"families": {}, "missing_or_uninstalled": [str(self.root / "assets/Fonts/Brand_Bold.otf")]})
        write_json(self.root / "output/client_database/asset-manifest.json",
                   {"assets": [{"rel": "assets/Brand/mark.png", "category": "logo"}]})
        doc = self.collect()
        self.assertEqual([(i["kind"], i["ref"]) for i in doc["items"]], [("fonts", "assets/Fonts/Brand_Bold.otf")])
        self.assertIn("Brand_Bold.otf", doc["items"][0]["text"])

    def test_K5_final_and_delivered(self):
        put_spec(self.p, events=[], music="PLACED")
        self.assertEqual(by_kind(self.collect(), "final"), [])
        common.set_status(self.p, "QC_PASSED", "t")
        fin = by_kind(self.collect(), "final")
        self.assertEqual([i["item"] for i in fin], [VID])
        self.assertIn("Premiere", fin[0]["text"])
        put_words(self.p, [word(1, AR_WORD, 1200, flagged="?")])
        common.set_status(self.p, "DELIVERED", "t")
        self.assertEqual([i for i in self.collect()["items"] if i["item"] == VID], [])
        m = Paths(self.root, "M0001")
        put_motion(m, needs=[], music={"file": "data/Music/a.wav"})
        common.set_status(m, "READY_FOR_HUMAN_EDITOR", "t")
        self.assertIn("After Effects", by_kind(self.collect(), "final")[0]["text"])

    def test_K7_review_not_current_never_vanishes(self):
        put_spec(self.p)
        self.assertEqual([i["ref"] for i in by_kind(self.collect(), "medical")], ["G2"])   # general client: no line
        rf_ref = f"output/projects/{VID}/review-flags.json"
        for domain in ("medical", "religious"):
            profile(self.root, "profile.json", {"domain": domain})
            self.p.p("review-flags.json").unlink(missing_ok=True)
            got = [i for i in by_kind(self.collect(), domain) if i["ref"] == rf_ref]      # missing
            self.assertEqual(len(got), 1, domain)
            self.assertIn("not current", got[0]["text"])
            self.assertIn("مش محدّثة", got[0]["text_ar"])
            full_review(self.p)                                                           # current: gone
            self.assertEqual([i for i in self.collect()["items"] if i["ref"] == rf_ref], [], domain)
            put_spec(self.p, events=[event("G1", 1000, 3500, text="مقدمة"),               # re-plan: stale -> back
                                     event("G2", 4000, 7250, approval=True, headline="Take 600 mg daily")])
            self.assertEqual(len([i for i in by_kind(self.collect(), domain) if i["ref"] == rf_ref]), 1, domain)
            self.p.p("review-flags.json").write_text("{broken", encoding="utf-8")         # damaged: line + unread
            doc = self.collect()
            self.assertEqual(len([i for i in by_kind(doc, domain) if i["ref"] == rf_ref]), 1, domain)
            self.assertIn(rf_ref, [u["source"] for u in doc["unread"]])
            put_spec(self.p)

    def test_K8_pick_the_reels(self):
        from lib.episode import EpisodePaths
        ep = EpisodePaths(self.root, "EP01")
        write_json(ep.p("01_analysis/reels-plan-validated.json"), {"ok": True, "candidates": []})
        it = by_kind(self.collect(), "pick")
        self.assertEqual([(i["item"], i["ref"]) for i in it], [("EP01", "output/episodes/EP01/01_analysis/reels-plan.md")])
        self.assertIn("pick the reels", it[0]["text"])
        self.assertIn("اختار الريلز", it[0]["text_ar"])
        write_json(ep.p("01_analysis/selection.json"), {"history": [{"picked": []}]})
        self.assertEqual(len(by_kind(self.collect(), "pick")), 1)
        write_json(ep.p("01_analysis/selection.json"), {"history": [{"picked": ["R01"], "by": "editor"}]})
        self.assertEqual(by_kind(self.collect(), "pick"), [])
        NY().write(self.root)
        md = (self.root / "output/NEEDS-YOU.md").read_text(encoding="utf-8")
        self.assertNotIn("اختار الريلز", md)

    def test_K6_website_producer(self):
        write_json(self.root / "output/from_website/current.json",
                   {"needs_you": [need(kind="website", ref="output/from_website/current.json",
                                       text="Confirm the brand colour #0A7", text_ar="أكّد لون البراند")]})
        it = by_kind(self.collect(), "website")
        self.assertEqual([(i["item"], i["source"]) for i in it], [(None, "output/from_website/current.json")])


# --------------------------------------------------------------------------- approval by auto
class TestAutoApprove(Base):
    def setUp(self):
        super().setUp()
        put_spec(self.p)

    def test_A1_auto_records_by_auto(self):
        f = prefs(self.root, approval="auto")
        rec = AP().approve(self.p)
        self.assertEqual((rec["approved"], rec["by"]), (True, "auto"))
        self.assertEqual(rec["delegation"], {"preference": "approval", "value": "auto", "from": str(f)})
        disk = read_json(self.p.p("01_analysis/plan-approval.json"))
        self.assertEqual(disk["by"], "auto")
        from lib.plan import approval_state
        self.assertEqual(approval_state(self.p)["state"], "current")
        cli_module().require_plan_approval(self.p)                      # the build gate accepts it (no SystemExit)

    def test_A2_ask_refuses(self):
        prefs(self.root, approval="ask")
        r = AP().approve(self.p)
        self.assertIn("refused", r)
        self.assertFalse(self.p.p("01_analysis/plan-approval.json").exists())
        code, doc, _ = reel(self.root, "auto-approve", "--video-id", VID)
        self.assertEqual(code, 2, doc)
        self.assertFalse(self.p.p("01_analysis/plan-approval.json").exists())

    def test_A3_missing_is_ask(self):
        self.assertIn("refused", AP().approve(self.p))
        self.assertFalse(self.p.p("01_analysis/plan-approval.json").exists())

    def test_A4_per_client(self):
        prefs(self.root, approval="auto")
        other = make_client(self.tmp, "Other Client")
        po = Paths(other, VID)
        put_spec(po)
        self.assertIn("refused", AP().approve(po))
        self.assertFalse(po.p("01_analysis/plan-approval.json").exists())
        self.assertTrue(AP().approve(self.p)["approved"])

    def test_A5_medical_religious_never_auto(self):
        prefs(self.root, approval="auto")
        rec = AP().approve(self.p)
        self.assertEqual(rec["not_covered"], [{"event_id": "G2", "kind": "medical"}])
        self.assertEqual([i["ref"] for i in by_kind(self.collect(), "medical")], ["G2"])
        profile(self.root, "profile.json", {"domain": "religious"})
        full_review(self.p, flag="religious")
        rec = AP().approve(self.p)
        self.assertEqual(rec["not_covered"], [{"event_id": "G2", "kind": "religious"}])
        self.assertEqual([i["ref"] for i in by_kind(self.collect(), "religious")], ["G2"])

    def test_A9_failed_replan_is_refused(self):
        prefs(self.root, approval="auto")
        write_json(self.p.p("01_analysis/plan-validation.json"), {"ok": False, "errors": ["G2: bad"], "warnings": []})
        r = AP().approve(self.p)                                        # the old spec is still there: never approved
        self.assertIn("refused", r)
        self.assertIn("reel plan", r["how"])
        self.p.p("01_analysis/plan-validation.json").unlink()
        self.assertIn("refused", AP().approve(self.p))
        self.assertFalse(self.p.p("01_analysis/plan-approval.json").exists())

    def test_A10_review_not_current_is_not_covered(self):
        prefs(self.root, approval="auto")
        for domain in ("medical", "religious"):
            profile(self.root, "profile.json", {"domain": domain})
            self.p.p("review-flags.json").unlink(missing_ok=True)
            rec = AP().approve(self.p)
            self.assertIn({"event_id": None, "kind": domain, "review": "missing or not current"}, rec["not_covered"])
            full_review(self.p, flag="medical")
            rec = AP().approve(self.p)
            self.assertNotIn(None, [n["event_id"] for n in rec["not_covered"]], domain)
        profile(self.root, "profile.json", {"domain": "general"})
        self.p.p("review-flags.json").unlink()
        self.assertNotIn(None, [n["event_id"] for n in AP().approve(self.p)["not_covered"]])

    def test_A6_distinct_from_editor(self):
        prefs(self.root, approval="auto")
        code, doc, err = reel(self.root, "auto-approve", "--video-id", VID)
        self.assertEqual(code, 0, (doc, err))
        self.assertEqual(doc["by"], "auto")
        code, _, err = reel(self.root, "approve-plan", "--video-id", VID, "--by", "auto")
        self.assertEqual(code, 2, err)                                    # not an approve-plan choice
        self.assertEqual(read_json(self.p.p("01_analysis/plan-approval.json"))["by"], "auto")

    def test_A7_motion(self):
        from lib import motion_plan
        prefs(self.root, approval="auto")
        m = Paths(self.root, "M0001")
        put_motion(m, needs=[])
        self.assertIn("refused", AP().approve(m))                         # no validation yet
        write_json(m.p("01_analysis/motion-validation.json"), {"ok": False, "fingerprint": motion_plan.fingerprint(m)})
        self.assertIn("refused", AP().approve(m))
        write_json(m.p("01_analysis/motion-validation.json"), {"ok": True, "fingerprint": motion_plan.fingerprint(m)})
        rec = AP().approve(m)
        self.assertEqual((rec["by"], rec["kind"], rec["plan_fingerprint"]), ("auto", "motion", motion_plan.fingerprint(m)))

    def test_A8_no_plan(self):
        prefs(self.root, approval="auto")
        p2 = Paths(self.root, "C0002")
        r = AP().approve(p2)
        self.assertIn("refused", r)
        self.assertIn("how", r)
        self.assertFalse(p2.p("01_analysis/plan-approval.json").exists())


# --------------------------------------------------------------------------- platforms
class TestPlatforms(Base):
    def test_P1_windows_refs(self):
        put_motion(self.p, needs=[need(ref="data\\Music\\a.wav")])
        self.assertEqual(by_kind(self.collect(), "music")[0]["ref"], "data/Music/a.wav")
        if os.name == "nt":                                               # case-insensitive drive and folders
            up = str(self.root / "data" / "Raw").upper()
            put_motion(self.p, needs=[need(ref=up)])
            self.assertEqual(by_kind(self.collect(), "music")[0]["ref"].lower(), "data/raw")

    def test_P2_darwin_font_hint(self):
        inventory(self.root, [inv_file(self.root, "assets/Fonts/Brand.otf", "font", "font"),
                              inv_file(self.root, "assets/Logo/l.png", "logo", "image")])
        write_json(self.root / "output/client_database/branding/typography.json",
                   {"families": {}, "missing_or_uninstalled": [str(self.root / "assets/Fonts/Brand.otf")]})
        with mock.patch.object(plat, "IS_WIN", False), mock.patch.object(plat, "IS_MAC", True):
            it = by_kind(self.collect(), "fonts")[0]
        self.assertIn("Install Font", it["text"])
        self.assertIn("دبل كليك", it["text_ar"])
        with mock.patch.object(plat, "IS_WIN", True), mock.patch.object(plat, "IS_MAC", False):
            it = by_kind(self.collect(), "fonts")[0]
        self.assertIn("right-click", it["text"])
        self.assertIn("كليك يمين", it["text_ar"])


# --------------------------------------------------------------------------- guard
class TestGuard(Base):
    def hook(self, cmd, agent=None):
        from test_plugin import hook
        p = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.root)}
        if agent:
            p["agent_type"] = agent
        return hook(GUARD, p)

    def test_G1_subagents_never_auto_approve(self):
        cmd = f"reel auto-approve --root . --video-id {VID}"
        self.assertEqual(self.hook(cmd)[0], 0)
        for agent in ("whynot-cut:story-editor", "whynot-cut:premiere-builder", "other-plugin:helper"):
            code, _, err = self.hook(cmd, agent)
            self.assertEqual(code, 2, agent)
            self.assertIn("lead", err)

    def test_G3_transcript_verify_by_allow_list(self):
        """The CLI records a missing --by as the editor: a subagent may only name itself (agent, claude, its role)."""
        for cmd in ("reel transcript-verify --video-id C0001", "reel transcript-verify --by auto",
                    "reel transcript-verify --by delegated", "reel transcript-verify --by Yunus",
                    "reel transcript-verify --by agent --by delegated", "reel transcript-verify --by=",
                    "reel transcript-verify --by editor"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.hook(cmd, "whynot-cut:transcript-editor")[0], 2)
                self.assertEqual(self.hook(cmd)[0], 0)                           # the lead may
        for cmd, agent in (("reel transcript-verify --by agent", "whynot-cut:premiere-builder"),
                           ("reel transcript-verify --by claude", "whynot-cut:story-editor"),
                           ("reel transcript-verify --by transcript-editor", "whynot-cut:transcript-editor"),
                           ("reel transcript-verify --by agent --by=agent --b agent", "other-plugin:x")):
            with self.subTest(allowed=cmd):
                self.assertEqual(self.hook(cmd, agent)[0], 0)
        self.assertEqual(self.hook("reel transcript-verify --by transcript-editor", "whynot-cut:story-editor")[0], 2)

    def test_G2_read_only_reviewers_cannot_write(self):
        w = "reel needs-you --root . --write"
        self.assertEqual(self.hook(w)[0], 0)
        self.assertEqual(self.hook(w, "whynot-cut:story-editor")[0], 0)
        for agent in ("whynot-cut:qc-reviewer", "whynot-cut:intake-inspector", "whynot-cut:setup-doctor",
                      "whynot-cut:medical-reviewer"):
            self.assertEqual(self.hook(w, agent)[0], 2, agent)
            self.assertEqual(self.hook("reel needs-you --root .", agent)[0], 0, agent)


# --------------------------------------------------------------------------- schema, CLI, skill
class TestContract(unittest.TestCase):
    def test_S1_schema_contract(self):
        from contract import check_schema
        self.assertIn("needs-you", schemas.KINDS)
        self.assertEqual(check_schema(schemas.bundled("needs-you")), [])
        s = schemas.bundled("needs-you")
        self.assertEqual(tuple(s["$defs"]["item"]["properties"]["kind"]["enum"]), NY().KINDS)
        self.assertEqual(NY().KINDS, ("pick", "words", "medical", "religious", "music", "fonts", "logo", "website",
                                      "final"))
        self.assertIn("pick", NY().__doc__)
        self.assertEqual(schemas.kind_for("output/needs-you.json"), "needs-you")

    def test_S2_cli_registration(self):
        import argparse
        m = cli_module()
        for name in ("needs-you", "auto-approve"):
            self.assertIn(name, m.command_table())
            self.assertIn(name, m.registered_commands())
        self.assertIn("needs-you", m.NO_ID)
        self.assertNotIn("auto-approve", m.NO_ID)
        self.assertIn("auto-approve", m.CORE_WRITES)
        self.assertIn("needs-you", m.WRITES_IF)
        self.assertNotIn("needs-you", m.CORE_WRITES)
        self.assertTrue(m.WRITES_IF["needs-you"](argparse.Namespace(write=True)))
        self.assertFalse(m.WRITES_IF["needs-you"](argparse.Namespace(write=False)))

    def test_S2b_needs_you_needs_no_video_id(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_client(Path(d))
            for f in ("a.mp4", "b.mp4"):
                (root / "data/Raw" / f).write_bytes(b"x")
            inventory(root, [inv_file(root, "data/Raw/a.mp4", "source_footage", "video"),
                             inv_file(root, "data/Raw/b.mp4", "source_footage", "video")])
            code, doc, err = reel(root, "needs-you", "--write")
            self.assertEqual(code, 0, (doc, err))
            self.assertTrue(doc["written"])
            self.assertTrue((root / "output/NEEDS-YOU.md").is_file())

    def test_S3_autopilot_skill_text(self):
        s = " ".join((SK / "skills/autopilot/SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("reel auto-approve", s)
        self.assertIn("reel needs-you", s)
        self.assertIn("--write", s)
        self.assertIn("output/NEEDS-YOU.md", s)
        self.assertRegex(s, r"(?i)medical and religious approvals (are )?never (automatic|auto)")
        self.assertRegex(s, r"medical and religious approvals needed")              # test_skill_text keeps this
        edit = " ".join((SK / "skills/edit/SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("reel auto-approve", edit)
        ctx = (SK / "hooks/session_context.py").read_text(encoding="utf-8")
        body = ctx[ctx.index("def prefs_line"):ctx.index("def export_options")]
        self.assertIn("auto-approve", body)
        self.assertIn("stay on `output/NEEDS-YOU.md`", body)
        self.assertRegex(s, r"(?i)merged preferences")                                # honest: not only its own file

    def test_S4_autopilot_stops_at_qc_while_approvals_are_open(self):
        """Interim rule until the handoff/READY gate (M1-T4): open medical/religious lines -> no `reel handoff`."""
        s = " ".join((SK / "skills/autopilot/SKILL.md").read_text(encoding="utf-8").split())
        step5 = s[s.index("## 5."):]
        self.assertRegex(step5, r"`not_covered`[^.]{0,200}not empty[^.]{0,200}stop (it|that clip) at QC")
        self.assertRegex(step5, r"(?i)do not run `reel handoff`")
        self.assertIn("pick the reels", " ".join(s.split()).lower())


if __name__ == "__main__":
    unittest.main()
