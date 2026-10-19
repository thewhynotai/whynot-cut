# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 53 = Addendum M1-T5: the review-domain eval cases (evals/review-<domain>-<name>/) and their engine pins.

Grader design (executor ruling Q53-1, option C): the eval session has no shell, so the reviewer writes the exact table
`reel review-flags --from` takes to `<item>/review-input.json` with the Write tool. Each expected (event id, flag,
verdict) tuple is one `regex` grader on `target: trace`, anchored inside that Write call's JSON input and inside ONE row
object of the table (a flag on another line, a wrong verdict or a table written anywhere else never matches), and each
case has one `not_contains` grader for a flag that must NOT be there. The runner joins the child's stream-json messages,
each JSON.stringify-ed, one per line (CLI 2.1.299), so the table sits in the trace JSON-escaped (\\" and \\n).

This file pins, per case, on the case's own planted files (plant/, copied into the eval workspace by the fixture
function add_review_case in evals/_fixtures/example-clinic.sh):
  * the planted review-scan.json IS `review_domains.scan()` of the planted plan (the hints the reviewer reads are true);
  * the expected answer passes `review_flags.write()` on that plan, with every expected tuple in the written file;
  * each wrong answer (a missing flag row) is refused, or leaves that line uncovered for that flag;
  * every trace grader passes on the expected answer written with Write (pretty or compact, keys in any order) and
    fails on each mutation: the row missing, a wrong verdict, the flag moved to another line (a partial key match), the
    table written to another file or only seen in a tool result; each negative grader fails when its forbidden row is
    there;
  * 3 positive + 1 negative case per shipped domain (owner decision 2026-10-19), and no domain lacks its eval
    (`structure_problems()`).
Run:  bash tools/test.sh -p test_review_domains_evals.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import copy
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

import test_structure as ts  # noqa: E402
from lib import common  # noqa: E402
from lib import review_domains as RD  # noqa: E402
from lib import review_flags as RF  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from lib.errors import Guidance  # noqa: E402

EVALS = SK / "evals"
SHIPPED_PROFILE = SK / "profiles" / "example-clinic" / "profile.json"
SHIPPED = ("ai", "business", "medical", "religious")


def row(eid: str, flag: str, verdict: str, reason: str = "") -> dict:
    return {"event_id": eid, "flag": flag, "verdict": verdict, "reason": reason or f"{flag}: {verdict}"}


def ok(eid: str, *flags: str) -> list:
    return [row(eid, f, "ok", "مطابق لكلام المتكلم") for f in flags]


# case -> (project id, polarity, expected table rows, wrong answers [(what, rows, (event id, flag it leaves out))])
CASES = {
    "review-medical-dose-claim": ("C0301", "+", [
        *ok("G01", "medical"),
        row("G02", "medical", "reword-to-match", "الشاشة ٥٠٠ مجم والمتكلم قال ٢٥٠ مجم"),
        *ok("G03", "medical")],
        [("the dose line not listed", ["G02"], ("G02", "medical"))]),
    "review-medical-general-client": ("C0302", "+", [
        *ok("G01", "medical"),
        row("G02", "medical", "needs-doctor-approval", "ادعاء علاج نهائي للسكر"),
        *ok("G03", "medical")],
        [("the cure claim not listed", ["G02"], ("G02", "medical"))]),
    "review-medical-cure-promise": ("C0303", "+", [
        *ok("G01", "medical"),
        row("G02", "medical", "needs-doctor-approval", "وعد بعلاج نهائي"),
        row("G02", "business", "needs-approval", "ضمان ١٠٠٪"),
        *ok("G03", "medical")],
        [("the guarantee's business row missing", [("G02", "business")], ("G02", "business"))]),
    "review-medical-negative-clean": ("C0304", "-", [
        *ok("G01", "medical"), *ok("G02", "medical"), *ok("G03", "medical")],
        [("a line not listed", ["G02"], ("G02", "medical"))]),
    "review-religious-hadith-attribution": ("C0305", "+", [
        *ok("G01", "religious"),
        row("G02", "religious", "reword-to-match", "المتكلم قالها مثل مش حديث"),
        *ok("G03", "religious")],
        [("the attribution line not listed", ["G02"], ("G02", "religious"))]),
    "review-religious-ruling": ("C0306", "+", [
        *ok("G01", "religious"),
        row("G02", "religious", "needs-approval", "حكم شرعي على الشاشة"),
        *ok("G03", "religious")],
        [("the ruling line not listed", ["G02"], ("G02", "religious"))]),
    "review-religious-hadith-and-dose": ("C0307", "+", [
        *ok("G01", "medical"),
        row("G02", "religious", "needs-approval", "حديث منسوب على الشاشة"),
        row("G02", "medical", "reword-to-match", "الشاشة ٥٠٠ مجم والمتكلم قال ٢٥٠ مجم"),
        *ok("G03", "medical")],
        [("the religious row missing", [("G02", "religious")], ("G02", "religious")),
         ("the medical row missing", [("G02", "medical")], ("G02", "medical"))]),
    "review-religious-business-word-in-hadith": ("C0308", "-", [
        *ok("G01", "religious"),
        row("G02", "religious", "needs-approval", "حديث منسوب: يأكده صاحب المحتوى"),
        *ok("G03", "religious")],
        [("the hadith line not listed", ["G02"], ("G02", "religious"))]),
    "review-business-roi": ("C0309", "+", [
        *ok("G01", "business", "medical"),
        row("G02", "business", "needs-evidence", "ادعاء أرباح من غير دليل"),
        *ok("G02", "medical"),
        *ok("G03", "business", "medical")],
        [("the earnings line's business row missing", [("G02", "business")], ("G02", "business"))]),
    "review-business-guarantee": ("C0310", "+", [
        *ok("G01", "medical"),
        row("G02", "business", "needs-approval", "ضمان نتيجة ١٠٠٪"),
        row("G02", "medical", "needs-doctor-approval", "نتيجة من أول جلسة"),
        *ok("G03", "medical")],
        [("the guarantee's business row missing", [("G02", "business")], ("G02", "business"))]),
    "review-business-doctor-price": ("C0311", "+", [
        *ok("G01", "medical"),
        row("G02", "business", "reword-to-match", "المتكلم قال لحد آخر الشهر"),
        *ok("G02", "medical"),
        *ok("G03", "medical")],
        [("the price line's business row missing", [("G02", "business")], ("G02", "business"))]),
    "review-business-negative-clean": ("C0312", "-", [
        *ok("G01", "business", "medical"), *ok("G02", "business", "medical"), *ok("G03", "business", "medical")],
        [("a line's business row missing", [("G02", "business")], ("G02", "business"))]),
    "review-ai-accuracy-claim": ("C0313", "+", [
        *ok("G01", "medical"),
        row("G02", "ai", "needs-approval", "دقة ٩٩٪ للذكاء الاصطناعي"),
        row("G02", "medical", "needs-doctor-approval", "تشخيص"),
        *ok("G03", "medical")],
        [("the AI claim's ai row missing", [("G02", "ai")], ("G02", "ai"))]),
    "review-ai-broll-no-label": ("C0314", "+", [
        *ok("G01", "medical"),
        row("G02", "ai", "needs-disclosure", "صورة مولّدة بالذكاء الاصطناعي من غير لابل"),
        *ok("G02", "medical"),
        *ok("G03", "medical")],
        [("the AI image's ai row missing", [("G02", "ai")], ("G02", "ai"))]),
    "review-ai-voice-claim": ("C0315", "+", [
        *ok("G01", "medical"),
        row("G02", "ai", "reword-to-match", "المتكلم قال إن صوته حقيقي"),
        *ok("G02", "medical"),
        *ok("G03", "medical")],
        [("the AI voice line's ai row missing", [("G02", "ai")], ("G02", "ai"))]),
    "review-ai-negative-clean": ("C0316", "-", [
        *ok("G01", "medical"), *ok("G02", "medical"), *ok("G03", "medical")],
        [("a line not listed", ["G03"], ("G03", "medical"))]),
}

WRITE_PATH = "C:\\Users\\eval\\home\\cwd\\example-clinic\\output\\projects\\{id}\\review-input.json"


def without(rows: list, drop: list) -> list:
    """rows minus every row of a dropped event id (a str) or of a dropped (event id, flag)."""
    def gone(r):
        return any(r["event_id"] == d if isinstance(d, str) else (r["event_id"], r["flag"]) == tuple(d) for d in drop)
    return [r for r in rows if not gone(r)]


def stringify(obj) -> str:
    """JSON.stringify: no spaces, non-ASCII kept, null for None."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def write_trace(rows: list, vid: str, *, indent=2, path: str | None = None, content_first=False, tool="Write",
                reorder=False) -> str:
    """The trace a run leaves when the agent writes `rows` as the review table: system init, the Write tool_use
    (assistant message), its tool_result, and the final answer; one JSON.stringify-ed message per line."""
    if reorder:                                     # keys in another order inside each row
        rows = [{k: r[k] for k in ("verdict", "reason", "flag", "event_id")} for r in rows]
    content = json.dumps({"items": rows}, ensure_ascii=False, indent=indent)
    fp = path if path is not None else WRITE_PATH.format(id=vid)
    inp = {"content": content, "file_path": fp} if content_first else {"file_path": fp, "content": content}
    msgs = [{"type": "system", "subtype": "init", "tools": ["Read", "Glob", "Grep", "Skill", "Write"]},
            {"type": "assistant", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": "m",
                                              "content": [{"type": "tool_use", "id": "toolu_1", "name": tool,
                                                           "input": inp}]},
             "parent_tool_use_id": None, "session_id": "s"},
            {"type": "user", "message": {"role": "user", "content": [
                {"tool_use_id": "toolu_1", "type": "tool_result", "content": "File created successfully at: " + fp}]},
             "parent_tool_use_id": None, "session_id": "s"},
            {"type": "assistant", "message": {"id": "msg_2", "type": "message", "role": "assistant", "model": "m",
                                              "content": [{"type": "text", "text": "تمام"}]},
             "parent_tool_use_id": None, "session_id": "s"}]
    return "\n".join(stringify(m) for m in msgs)


def read_only_trace(rows: list, vid: str) -> str:
    """The table seen only in a Read tool result (never written by the agent)."""
    content = json.dumps({"items": rows}, ensure_ascii=False, indent=2)
    msgs = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_9", "name": "Read",
                                                           "input": {"file_path": WRITE_PATH.format(id=vid)}}]}},
            {"type": "user", "message": {"content": [{"tool_use_id": "toolu_9", "type": "tool_result",
                                                      "content": content}]}}]
    return "\n".join(stringify(m) for m in msgs)


def graders(case: str) -> dict:
    """grader name -> (frontmatter, pattern body) for the case's trace regex graders."""
    out = {}
    for g in sorted((EVALS / case / "graders").glob("*.md")):
        text = g.read_text(encoding="utf-8")
        fm = ts.frontmatter(text)
        lines = text.splitlines()
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
        body = "\n".join(lines[end + 1:]).strip()
        if fm.get("type") == "regex" and fm.get("target") == "trace":
            out[g.stem] = (fm, body)
    return out


def passes(fm: dict, body: str, trace: str) -> bool:
    hit = re.search(body, trace) is not None
    return hit if fm.get("match", "contains") == "contains" else not hit


# what a grader's pattern holds (the generator writes every alternative as a (?:...) group)
G_EID = re.compile(r'event_id\\\\"\\s\*:\\s\*\\\\"(?:\(\?:)?([G0-9|]+)\)?\\\\"')
G_FLAGS = re.compile(r'flag\\\\"\\s\*:\\s\*\\\\"\(\?:([a-z|]+)\)\\\\"')
G_VERDICTS = re.compile(r'verdict\\\\"\\s\*:\\s\*\\\\"\(\?:([a-z|-]+)\)\\\\"')
NEGATIVE = re.compile(r"no-([a-z]+)-(flag|ok)-on-((?:g\d\d-?)+)")
ALL_VERDICTS = ("ok", "remove", "reword-to-match", "needs-approval", "needs-evidence", "needs-disclosure",
                "needs-doctor-approval")


class CaseBase(unittest.TestCase):
    def client(self, case: str) -> Paths:
        """A client folder with the case's planted profile, asset manifest and plan, as the scaffold makes it."""
        vid = CASES[case][0]
        plant = EVALS / case / "plant"
        tmp = Path(tempfile.mkdtemp(prefix="t53_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        self.addCleanup(common.set_context, None)
        root = tmp / "example-clinic"
        for d in ("assets", "data/Raw"):
            (root / d).mkdir(parents=True)
        (root / ".whynot-client").write_text("{}", encoding="utf-8")
        prof = plant / "profile.json" if (plant / "profile.json").is_file() else SHIPPED_PROFILE
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", json.loads(prof.read_text(encoding="utf-8")))
        if (plant / "asset-manifest.json").is_file():
            write_json(root / "output/client_database/asset-manifest.json",
                       json.loads((plant / "asset-manifest.json").read_text(encoding="utf-8")))
        p = Paths(root, vid)
        write_json(p.p("01_analysis/timeline-spec.json"),
                   json.loads((plant / "timeline-spec.json").read_text(encoding="utf-8")))
        common.set_context(root)
        return p


class TestCaseLayout(unittest.TestCase):
    def test_three_positive_and_one_negative_case_per_domain(self):
        have = sorted(d.name for d in EVALS.glob("review-*") if d.is_dir())
        self.assertEqual(have, sorted(CASES))
        for dom in SHIPPED:
            mine = [c for c in CASES if c.startswith(f"review-{dom}-")]
            self.assertEqual(sorted(CASES[c][1] for c in mine), ["+", "+", "+", "-"], dom)

    def test_no_domain_lacks_its_eval(self):
        self.assertEqual([p for p in RD.structure_problems() if p["missing"] == "eval"], [])

    def test_each_case_plants_its_own_project_with_the_fixture_function(self):
        ids = [v[0] for v in CASES.values()]
        self.assertEqual(len(set(ids)), len(ids))
        for case, (vid, pol, _rows, _wrong) in CASES.items():
            d = EVALS / case
            sc = (d / "scaffold.sh").read_text(encoding="utf-8")
            self.assertRegex(sc, rf'(?m)^add_review_case example-[a-z]+ {vid} "\$\{{here%/\*\}}"$', case)
            for f in ("timeline-spec.json", "edit-plan.md", "review-scan.json", "transcript.md"):
                self.assertTrue((d / "plant" / f).is_file(), (case, f))
            tags = (d / "case.yaml").read_text(encoding="utf-8")
            self.assertIn("negative" if pol == "-" else "positive", tags, case)
            pm = ts.frontmatter((d / "prompt.md").read_text(encoding="utf-8"))
            self.assertIn("Write", pm["allowed_tools"], case)
            self.assertNotIn("Bash", pm["allowed_tools"], case)            # Q53-1: no shell and no engine in an eval
            self.assertIn("review-input.json", pm["append_system_prompt"], case)
            for leak in d.rglob("*"):                                     # the answer is never planted
                if leak.is_file() and "plant" in leak.parts:
                    self.assertNotIn('"verdict"', leak.read_text(encoding="utf-8"), leak)

    def test_no_verse_text_in_any_case(self):
        """Owner decision 2026-10-18: no verse in any fixture (the editor adds verses by hand)."""
        for f in EVALS.glob("review-*/**/*"):
            if f.is_file():
                text = f.read_text(encoding="utf-8")
                self.assertNotRegex(text, "[\ufd3e\ufd3f]|قال تعالى|سورة", f)


class TestPlantedScan(CaseBase):
    def test_planted_scan_is_the_engine_scan(self):
        for case in CASES:
            with self.subTest(case=case):
                p = self.client(case)
                planted = json.loads((EVALS / case / "plant" / "review-scan.json").read_text(encoding="utf-8"))
                self.assertEqual(planted, RD.scan(p))


class TestEnginePins(CaseBase):
    """The expected answer is legal for the engine; the wrong one (a missing flag) is refused or leaves the line
    uncovered for that flag."""

    def covered(self, doc: dict, eid: str) -> set:
        key = doc["domain"]
        named = {r["flag"] for r in doc["items"] if r["event_id"] == eid}
        for o in doc["ok"]:
            if o["event_id"] == eid:
                named |= RF._named_ok(o, key)
        return RF._cover(named, RF._allowed(key))

    def test_expected_answer_is_written(self):
        for case, (_vid, _pol, rows, _wrong) in CASES.items():
            with self.subTest(case=case):
                p = self.client(case)
                doc = RF.write(p, {"items": copy.deepcopy(rows)}, by="eval")
                got = {(r["event_id"], r["flag"], r["verdict"]) for r in doc["items"]}
                for r in rows:
                    if r["verdict"] == "ok":
                        self.assertIn(r["flag"], self.covered(doc, r["event_id"]), (case, r))
                    else:
                        self.assertIn((r["event_id"], r["flag"], r["verdict"]), got, (case, r))
                self.assertEqual(doc["checked"], doc["lines_total"])
                self.assertIsNotNone(RF.load(p), case)

    def test_wrong_answer_is_refused_or_leaves_the_line_uncovered(self):
        for case, (_vid, _pol, rows, wrong) in CASES.items():
            for what, drop, (eid, flag) in wrong:
                with self.subTest(case=case, wrong=what):
                    p = self.client(case)
                    try:
                        doc = RF.write(p, {"items": without(copy.deepcopy(rows), drop)}, by="eval")
                    except Guidance as g:
                        self.assertIn(eid, str(g))
                        self.assertFalse(RF.path(p).exists())
                        continue
                    self.assertNotIn(flag, self.covered(doc, eid), (case, what))

    def test_a_ruling_passed_as_medical_ok_is_caught_by_the_eval_not_the_engine(self):
        """A known limit, pinned: «حرام» alone is not detected (everyday speech: «حرام عليك تهمل صحتك»), and for a
        religious client a medical row covers religious by T4.13's implied coverage, so the engine accepts a ruling
        passed as `medical: ok`. Only the eval's g02-religious grader catches that answer."""
        case = "review-religious-ruling"
        vid, _pol, rows, _w = CASES[case]
        lazy = without(rows, ["G02"]) + ok("G02", "medical")
        doc = RF.write(self.client(case), {"items": lazy}, by="eval")
        self.assertIn("religious", self.covered(doc, "G02"))
        fm, body = graders(case)["g02-religious"]
        self.assertFalse(passes(fm, body, write_trace(lazy, vid)))


class TestTraceGraders(unittest.TestCase):
    """Every counted decision is a regex on the trace, anchored in the Write call and in one row (Q53-1)."""

    def setUp(self):
        self.g = {c: graders(c) for c in CASES}

    def test_each_case_has_tuple_graders_and_one_negative(self):
        for case, gs in self.g.items():
            neg = [n for n, (fm, _b) in gs.items() if fm.get("match") == "not_contains"]
            pos = [n for n, (fm, _b) in gs.items() if fm.get("match", "contains") == "contains"]
            self.assertEqual(len(neg), 1, case)
            self.assertGreaterEqual(len(pos), 3, case)
            for n, (_fm, body) in gs.items():
                self.assertIn('"name":"Write"', body, (case, n))
                self.assertIn("review-input\\.json", body, (case, n))
                self.assertIn(CASES[case][0], body, (case, n))

    def test_expected_answer_passes_every_trace_grader(self):
        for case, (vid, _pol, rows, _wrong) in CASES.items():
            for kw in ({}, {"indent": None}, {"content_first": True}, {"reorder": True}):
                t = write_trace(rows, vid, **kw)
                for n, (fm, body) in self.g[case].items():
                    self.assertTrue(passes(fm, body, t), (case, n, kw))

    def test_each_tuple_grader_fails_on_each_mutation(self):
        for case, (vid, _pol, rows, _wrong) in CASES.items():
            for n, (fm, body) in self.g[case].items():
                if fm.get("match", "contains") != "contains":
                    continue
                hits = [r for r in rows if re.search(body, write_trace([r], vid))]
                self.assertEqual(len(hits), 1, (case, n, hits))          # one grader = one expected row
                r = hits[0]
                eid, flags, verdicts = (G_EID.search(body).group(1), G_FLAGS.search(body).group(1).split("|"),
                                        G_VERDICTS.search(body).group(1).split("|"))
                self.assertEqual((eid, r["flag"] in flags, r["verdict"] in verdicts), (r["event_id"], True, True))
                self.assertEqual(n, f"{eid.lower()}-{r['flag'] if r['verdict'] != 'ok' else 'ok'}", case)
                bad_v = next(v for v in ALL_VERDICTS if v not in verdicts)
                bad_f = next(f for f in ("business", "religious", "medical", "ai") if f not in flags)
                others = [x for x in rows if x is not r]
                muts = {
                    "row missing": write_trace(others, vid),
                    "wrong verdict": write_trace(others + [dict(r, verdict=bad_v)], vid),
                    "flag on another line": write_trace(others + [dict(r, event_id="G09")], vid),
                    "another flag": write_trace(others + [dict(r, flag=bad_f)], vid),
                    "keys split across rows": write_trace(others + [dict(r, flag=bad_f), dict(r, event_id="G09")],
                                                          vid),
                    "near-miss key names": write_trace(others + [{"eventid": r["event_id"], "flags": r["flag"],
                                                                  "verdict_": r["verdict"], "reason": ""}], vid),
                    "written elsewhere": write_trace(rows, vid, path=WRITE_PATH.format(id=vid).replace(
                        "review-input.json", "notes.json")),
                    "another project": write_trace(rows, vid, path=WRITE_PATH.format(id="C0999")),
                    "only read, never written": read_only_trace(rows, vid),
                    "not the Write tool": write_trace(rows, vid, tool="Edit"),
                }
                for what, t in muts.items():
                    self.assertFalse(passes(fm, body, t), (case, n, what))

    def test_each_negative_grader_fails_when_its_forbidden_row_is_there(self):
        for case, (vid, _pol, rows, _wrong) in CASES.items():
            neg = [(n, fm, b) for n, (fm, b) in self.g[case].items() if fm.get("match") == "not_contains"]
            n, fm, body = neg[0]
            m = NEGATIVE.fullmatch(n)
            self.assertIsNotNone(m, (case, n))
            flag, kind, eids = m.group(1), m.group(2), m.group(3).upper().split("-")
            bad = "ok" if kind == "ok" else next(v for v in RD.registry()[flag]["verdicts"] if v != "ok")
            for eid in eids:
                t = write_trace(without(rows, [(eid, flag)]) + [row(eid, flag, bad, "x")], vid)
                self.assertFalse(passes(fm, body, t), (case, n, eid))
                if kind == "flag":                    # an ok row for that flag is fine (the line was cleared for it)
                    t = write_trace(without(rows, [(eid, flag)]) + [row(eid, flag, "ok", "x")], vid)
                    self.assertTrue(passes(fm, body, t), (case, n, eid))
            self.assertTrue(passes(fm, body, write_trace(rows, vid)), (case, n))
            self.assertTrue(passes(fm, body, write_trace(rows, vid, indent=None, reorder=True)), (case, n))


if __name__ == "__main__":
    unittest.main()
