# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 53 = Addendum M1-T5: the review-domain eval cases (evals/review-<domain>-<name>/) and their engine pins.

Grader design (executor ruling Q53-1, option C): the eval session has no shell, so the reviewer writes the exact table
`reel review-flags --from` takes to `<item>/review-input.json` with the Write tool. The counted graders read the table
LEFT ON DISK (`target: {source: file, path: <client>/output/projects/<id>/review-input.json}`, resolved in the run's
sandbox cwd; review 6275496 P2-2): each expected (event id, flag, verdict) tuple is one `regex` grader anchored inside
ONE row object of that file; each case has one `not_contains` grader for a flag that must NOT be there and one for two
rows on the same (line, flag), which review_flags.write() refuses ("listed twice").

This file pins, per case, on the case's own planted files (plant/, copied into the eval workspace by the fixture
function add_review_case in evals/_fixtures/example-clinic.sh):
  * the planted review-scan.json IS `review_domains.scan()` of the planted plan (the hints the reviewer reads are true);
  * the expected answer passes `review_flags.write()` on that plan, with every expected tuple in the written file;
  * each wrong answer (a missing flag row) is refused, or leaves that line uncovered for that flag;
  * each case's graders are exactly the ones in GRADERS below (a table kept apart from the grader files), so loosening
    a grader's verdict set or deleting a grader goes red (review 6275496 P2-1); every flagged expected row has exactly
    one grader, and no such grader accepts `ok`; a hadith on screen is never accepted as `ok` (P1, the owner's human
    religious approval gate); a guarantee has one contract in every case (P2-4);
  * every grader passes the expected table (pretty or compact JSON, keys in any order) and fails each mutation: the row
    missing, a wrong verdict, the flag on another line or another flag (a partial key match), keys split across rows,
    near-miss key names, a later overwrite with a wrong table, no file; each negative grader fails on its forbidden
    row; the duplicate grader fails on a contradicting row;
  * 3 positive + 1 negative case per shipped domain (owner decision 2026-10-19), no verse text (no marker and no
    verse-phrase detection), and no domain lacks its eval (`structure_problems()`).
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

# The graders each case must have, kept apart from the grader files (review 6275496 P2-1): case -> (client folder,
# {tuple grader: (event id, accepted flags, accepted verdicts)}, negative grader). A grader whose set is loosened, a
# grader deleted or added, or a case moved to another file path fails test_graders_are_the_pinned_ones.
MED_OK, REL_OK, BIZ_OK = ("medical", "ok"), ("religious|medical", "ok"), ("business", "ok")
GRADERS = {
    "review-medical-dose-claim": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-medical": ("G02", "medical", "reword-to-match|needs-doctor-approval|remove"),
        "g03-ok": ("G03", *MED_OK)}, "no-business-flag-on-g02"),
    "review-medical-general-client": ("example-coach", {
        "g01-ok": ("G01", *MED_OK), "g02-medical": ("G02", "medical", "needs-doctor-approval|remove"),
        "g03-ok": ("G03", *MED_OK)}, "no-medical-ok-on-g02"),
    "review-medical-cure-promise": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-medical": ("G02", "medical", "needs-doctor-approval|remove"),
        "g02-business": ("G02", "business", "needs-approval"), "g03-ok": ("G03", *MED_OK)},
        "no-business-flag-on-g01-g03"),
    "review-medical-negative-clean": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-ok": ("G02", *MED_OK), "g03-ok": ("G03", *MED_OK)},
        "no-medical-flag-on-g01-g02-g03"),
    "review-religious-hadith-attribution": ("example-talks", {
        "g01-ok": ("G01", *REL_OK), "g02-religious": ("G02", "religious", "reword-to-match|needs-approval|remove"),
        "g03-ok": ("G03", *REL_OK)}, "no-business-flag-on-g02"),
    "review-religious-ruling": ("example-talks", {
        "g01-ok": ("G01", *REL_OK), "g02-religious": ("G02", "religious", "needs-approval|reword-to-match|remove"),
        "g03-ok": ("G03", *REL_OK)}, "no-business-flag-on-g02"),
    "review-religious-hadith-and-dose": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-religious": ("G02", "religious", "needs-approval"),
        "g02-medical": ("G02", "medical", "reword-to-match|needs-doctor-approval|remove"), "g03-ok": ("G03", *MED_OK)},
        "no-business-flag-on-g02"),
    "review-religious-business-word-in-hadith": ("example-talks", {
        "g01-ok": ("G01", *REL_OK), "g02-religious": ("G02", "religious", "needs-approval"),
        "g03-ok": ("G03", *REL_OK)}, "no-business-flag-on-g01-g02-g03"),
    "review-business-roi": ("example-clinic", {
        "g01-ok": ("G01", *BIZ_OK), "g02-business": ("G02", "business", "needs-evidence"), "g03-ok": ("G03", *BIZ_OK)},
        "no-medical-flag-on-g02"),
    "review-business-guarantee": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-business": ("G02", "business", "needs-approval"), "g03-ok": ("G03", *MED_OK)},
        "no-business-flag-on-g01-g03"),
    "review-business-doctor-price": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-business": ("G02", "business", "reword-to-match|needs-approval"),
        "g03-ok": ("G03", *MED_OK)}, "no-business-flag-on-g01-g03"),
    "review-business-negative-clean": ("example-clinic", {
        "g01-ok": ("G01", *BIZ_OK), "g02-ok": ("G02", *BIZ_OK), "g03-ok": ("G03", *BIZ_OK)},
        "no-business-flag-on-g01-g02-g03"),
    "review-ai-accuracy-claim": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-ai": ("G02", "ai", "needs-approval"), "g03-ok": ("G03", *MED_OK)},
        "no-ai-flag-on-g01-g03"),
    "review-ai-broll-no-label": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-ai": ("G02", "ai", "needs-disclosure"), "g03-ok": ("G03", *MED_OK)},
        "no-ai-flag-on-g01-g03"),
    "review-ai-voice-claim": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-ai": ("G02", "ai", "reword-to-match|remove|needs-approval"),
        "g03-ok": ("G03", *MED_OK)}, "no-ai-flag-on-g01-g03"),
    "review-ai-negative-clean": ("example-clinic", {
        "g01-ok": ("G01", *MED_OK), "g02-ok": ("G02", *MED_OK), "g03-ok": ("G03", *MED_OK)},
        "no-ai-flag-on-g01-g02-g03"),
}
COMMON = {"skill-fired", "no-gate-jargon", "criteria", "no-duplicate-rows"}
CITATION_LINES = {"review-religious-hadith-attribution": "G02", "review-religious-hadith-and-dose": "G02",
                  "review-religious-business-word-in-hadith": "G02"}      # «قال رسول الله ﷺ …» on screen
WAITS_FOR_TASK52 = {"review-business-guarantee": "business-claims.md",          # P2-5; cure-promise since P2-4
                    "review-medical-cure-promise": "business-claims.md",
                    "review-ai-broll-no-label": "ai-claims-and-disclosure.md"}
# expected flagged rows a case deliberately does not grade: the medical side of a business or AI claim (the
# judge text says the doctor "may be named too"; the reviewer may also clear it)
UNGRADED = {("review-business-guarantee", "G02", "medical"), ("review-ai-accuracy-claim", "G02", "medical")}


def without(rows: list, drop: list) -> list:
    """rows minus every row of a dropped event id (a str) or of a dropped (event id, flag)."""
    def gone(r):
        return any(r["event_id"] == d if isinstance(d, str) else (r["event_id"], r["flag"]) == tuple(d) for d in drop)
    return [r for r in rows if not gone(r)]


def table(rows: list, *, indent=2, reorder=False) -> str:
    """The review-input.json the reviewer writes (pretty or compact; keys in another order on request)."""
    if reorder:
        rows = [{k: r[k] for k in ("verdict", "reason", "flag", "event_id")} for r in rows]
    return json.dumps({"items": rows}, ensure_ascii=False, indent=indent)


def graders(case: str, *, every=False) -> dict:
    """grader name -> (frontmatter, pattern body): the case's regex graders on review-input.json (every=True: all)."""
    out = {}
    for g in sorted((EVALS / case / "graders").glob("*.md")):
        text = g.read_text(encoding="utf-8")
        fm = ts.frontmatter(text)
        lines = text.splitlines()
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
        body = "\n".join(lines[end + 1:]).strip()
        if every or (fm.get("type") == "regex" and isinstance(fm.get("target"), dict)):
            out[g.stem] = (fm, body)
    return out


def passes(fm: dict, body: str, content) -> bool:
    """The runner's verdict on the file's content (None: the reviewer wrote no file, so the grader cannot pass)."""
    if content is None:
        return False
    hit = re.search(body, content) is not None
    return hit if fm.get("match", "contains") == "contains" else not hit


def case_passes(case: str, content) -> bool:
    return all(passes(fm, body, content) for fm, body in graders(case).values())


# what a grader's pattern holds (the generator writes every alternative as a (?:...) group)
G_EID = re.compile(r'"event_id"\\s\*:\\s\*"(?:\(\?:)?([G0-9|]+)\)?"')
G_FLAGS = re.compile(r'"flag"\\s\*:\\s\*"\(\?:([a-z|]+)\)"')
G_VERDICTS = re.compile(r'"verdict"\\s\*:\\s\*"\(\?:([a-z|-]+)\)"')
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
        """Owner decision 2026-10-18: no verse in any fixture (the editor adds verses by hand). Markers, and the
        religious lexicon's own verse rules (review 6275496 P3-3: a bare verse without markers)."""
        lex = RD.lexicon("religious")
        verse_rules = {"verse-phrase", "quran-verse"}
        self.assertLessEqual(verse_rules, {r["id"] for r in lex["rules"]} | {z["id"] for z in lex.get("zones", [])})
        for f in EVALS.glob("review-*/**/*"):
            if f.is_file():
                text = f.read_text(encoding="utf-8")
                self.assertNotRegex(text, "[﴾﴿]|قال تعالى|سورة", f)
                for line in text.splitlines():
                    hits = {h["rule"] for h in RD.detect(line).get("religious", [])}
                    self.assertFalse(hits & verse_rules, (f, line))


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

    def test_a_religious_line_passed_as_medical_ok_is_refused_when_detected_and_caught_by_the_eval_when_not(self):
        """Review 6275496 P2-3, fixed in the engine: for a religious client (key ai+medical+religious) a line whose
        words trigger religious (a «قال رسول الله ﷺ …» citation) needs its own religious row, as a triggered ai does
        (`review_flags._cover`): one `medical: ok` row is refused, naming the line and religious, and nothing is
        written. A written lexicon limit stays: the undetected «حرام» ruling is still cleared by that row (T4.13's
        implied coverage on a line nothing triggers), and only the eval's g02-religious grader (and the editor's read)
        catches it. On a medical client the same row is refused too («list G02 for religious»)."""
        for case in ("review-religious-ruling", "review-religious-hadith-attribution",
                     "review-religious-business-word-in-hadith"):
            with self.subTest(case=case):
                vid, _pol, rows, _w = CASES[case]
                p = self.client(case)
                detected = {x["event_id"]: sorted(x["detected"]) for x in RD.scan(p)["lines"]}
                lazy = without(rows, ["G02"]) + ok("G02", "medical")
                fm, body = graders(case)["g02-religious"]
                self.assertFalse(passes(fm, body, table(lazy)))
                if case == "review-religious-ruling":                 # the lexicon limit: not detected, so implied
                    self.assertNotIn("religious", detected["G02"])
                    doc = RF.write(p, {"items": lazy}, by="eval")
                    self.assertIn("religious", self.covered(doc, "G02"))
                    continue
                self.assertIn("religious", detected["G02"])          # the citation IS detected: refused
                with self.assertRaises(Guidance) as cm:
                    RF.write(p, {"items": lazy}, by="eval")
                self.assertIn("G02 has not been reviewed for religious", str(cm.exception))
                self.assertFalse(RF.path(p).exists())
        vid, _pol, rows, _w = CASES["review-religious-hadith-and-dose"]       # the medical client: refused
        with self.assertRaises(Guidance) as cm:
            RF.write(self.client("review-religious-hadith-and-dose"),
                     {"items": without(rows, ["G02"]) + ok("G02", "medical")}, by="eval")
        self.assertIn("religious", str(cm.exception))


class TestGraders(unittest.TestCase):
    """The counted decision is a regex on the final review-input.json, one grader per expected row (Q53-1, review
    6275496 P2-1/P2-2)."""

    def setUp(self):
        self.g = {c: graders(c) for c in CASES}

    def parsed(self, body: str):
        return (G_EID.search(body).group(1), G_FLAGS.search(body).group(1), G_VERDICTS.search(body).group(1))

    def test_graders_are_the_pinned_ones(self):
        for case, (folder, tuples, neg) in GRADERS.items():
            with self.subTest(case=case):
                vid = CASES[case][0]
                self.assertEqual(set(graders(case, every=True)), set(tuples) | {neg} | COMMON)
                for n, (fm, body) in self.g[case].items():
                    self.assertEqual(fm["target"], {"source": "file",
                                                    "path": f"{folder}/output/projects/{vid}/review-input.json"}, n)
                    if n in tuples:
                        self.assertEqual(fm.get("match", "contains"), "contains", n)
                        self.assertEqual(self.parsed(body), tuples[n], n)
                    else:
                        self.assertEqual(fm["match"], "not_contains", n)
                sc = (EVALS / case / "scaffold.sh").read_text(encoding="utf-8")
                self.assertIn(f"add_review_case {folder} {vid} ", sc)

    def test_every_flagged_row_has_exactly_one_strict_grader(self):
        for case, (_vid, _pol, rows, _w) in CASES.items():
            tuples = GRADERS[case][1]
            for r in rows:
                mine = [n for n, (eid, flags, v) in tuples.items()
                        if eid == r["event_id"] and r["flag"] in flags.split("|")
                        and (r["verdict"] == "ok") == (v == "ok")]
                if not mine and (r["verdict"] == "ok" or (case, r["event_id"], r["flag"]) in UNGRADED):
                    continue                     # an extra ok row (a business client's medical ok), or UNGRADED
                self.assertEqual(len(mine), 1, (case, r))
                verdicts = tuples[mine[0]][2].split("|")
                self.assertIn(r["verdict"], verdicts, (case, r))
                if r["verdict"] != "ok":
                    self.assertNotIn("ok", verdicts, (case, r))
        for case, eid, flag in UNGRADED:          # each exception is a real, flagged row of the expected table
            self.assertTrue(any((r["event_id"], r["flag"]) == (eid, flag) and r["verdict"] != "ok"
                                for r in CASES[case][2]), (case, eid, flag))

    def test_a_hadith_on_screen_is_never_accepted_as_ok(self):
        """Review 6275496 P1, the owner's rule: the human religious approval gate stays on, so a citation line is
        never cleared as `religious: ok` (the two cases that speak of a cited hadith want needs-approval only)."""
        for case, eid in CITATION_LINES.items():
            with self.subTest(case=case):
                _vid, _pol, rows, _w = CASES[case]
                self.assertTrue(case_passes(case, table(rows)))
                auto = without(rows, [(eid, "religious")]) + [row(eid, "religious", "ok", "x")]
                self.assertFalse(case_passes(case, table(auto)))
                lazy = [dict(r, verdict="ok") for r in rows]           # an all-ok table
                self.assertFalse(case_passes(case, table(lazy)))
        for case in ("review-religious-hadith-and-dose", "review-religious-business-word-in-hadith"):
            self.assertEqual(GRADERS[case][1]["g02-religious"][2], "needs-approval")

    def test_a_guarantee_has_one_contract(self):
        """Review 6275496 P2-4: «نتيجة مضمونة ١٠٠٪» and «علاج نهائي ١٠٠٪» are guarantees: business needs-approval in both
        cases (Task 52's business-claims.md rule 4; the strongest verdict, needs-approval, wins)."""
        got = {c: GRADERS[c][1]["g02-business"][2]
               for c in ("review-business-guarantee", "review-medical-cure-promise")}
        self.assertEqual(set(got.values()), {"needs-approval"}, got)
        for c in got:
            fm, body = self.g[c]["g02-business"]
            self.assertEqual(self.parsed(body)[2], "needs-approval")

    def test_cases_that_wait_for_task52_say_so(self):
        """Review 6275496 P2-5: their verdicts come from Task 52's guidance, which HEAD lacks; tagged pending so the
        >= 2/3 bar does not count them until it lands."""
        for case in CASES:
            text = (EVALS / case / "case.yaml").read_text(encoding="utf-8")
            if case in WAITS_FOR_TASK52:
                self.assertIn("pending", text, case)
                self.assertIn("needs-task52", text, case)
                self.assertIn(WAITS_FOR_TASK52[case], text, case)
            else:
                self.assertNotIn("pending", text, case)

    def test_expected_answer_passes_every_grader(self):
        for case, (_vid, _pol, rows, _wrong) in CASES.items():
            for kw in ({}, {"indent": None}, {"reorder": True}):
                content = table(rows, **kw)
                for n, (fm, body) in self.g[case].items():
                    self.assertTrue(passes(fm, body, content), (case, n, kw))

    def test_each_tuple_grader_fails_on_each_mutation(self):
        for case, (_vid, _pol, rows, _wrong) in CASES.items():
            for n, (fm, body) in self.g[case].items():
                if n not in GRADERS[case][1]:
                    continue
                hits = [r for r in rows if re.search(body, table([r]))]
                self.assertEqual(len(hits), 1, (case, n, hits))          # one grader = one expected row
                r = hits[0]
                _eid, flags, verdicts = self.parsed(body)
                bad_v = next(v for v in ALL_VERDICTS if v not in verdicts.split("|"))
                bad_f = next(f for f in ("business", "religious", "medical", "ai") if f not in flags.split("|"))
                others = [x for x in rows if x is not r]
                muts = {
                    "no file": None,
                    "row missing": table(others),
                    "wrong verdict": table(others + [dict(r, verdict=bad_v)]),
                    "flag on another line": table(others + [dict(r, event_id="G09")]),
                    "another flag": table(others + [dict(r, flag=bad_f)]),
                    "keys split across rows": table(others + [dict(r, flag=bad_f), dict(r, event_id="G09")]),
                    "near-miss key names": table(others + [{"eventid": r["event_id"], "flags": r["flag"],
                                                            "verdict_": r["verdict"], "reason": ""}]),
                }
                if r["verdict"] != "ok":                 # a right first Write, then a wrong overwrite: the file counts
                    muts["overwritten by a later all-ok table"] = table([dict(x, verdict="ok") for x in rows])
                for what, content in muts.items():
                    self.assertFalse(passes(fm, body, content), (case, n, what))

    def test_each_negative_grader_fails_when_its_forbidden_row_is_there(self):
        for case, (_vid, _pol, rows, _wrong) in CASES.items():
            n = GRADERS[case][2]
            fm, body = self.g[case][n]
            m = NEGATIVE.fullmatch(n)
            flag, kind, eids = m.group(1), m.group(2), m.group(3).upper().split("-")
            bad = "ok" if kind == "ok" else next(v for v in RD.registry()[flag]["verdicts"] if v != "ok")
            for eid in eids:
                content = table(without(rows, [(eid, flag)]) + [row(eid, flag, bad, "x")])
                self.assertFalse(passes(fm, body, content), (case, n, eid))
                if kind == "flag":                    # an ok row for that flag is fine (the line was cleared for it)
                    content = table(without(rows, [(eid, flag)]) + [row(eid, flag, "ok", "x")])
                    self.assertTrue(passes(fm, body, content), (case, n, eid))
            self.assertTrue(passes(fm, body, table(rows, indent=None, reorder=True)), (case, n))

    def test_the_duplicate_grader_fails_on_a_contradicting_row(self):
        """Review 6275496 P2-2: a flagged row plus an `ok` row for the same (line, flag) in one table passed every grader;
        review_flags.write() refuses it ("listed twice")."""
        for case, (_vid, _pol, rows, _wrong) in CASES.items():
            fm, body = self.g[case]["no-duplicate-rows"]
            self.assertTrue(passes(fm, body, table(rows)), case)
            for r in rows:
                twin = dict(r, verdict="needs-approval" if r["verdict"] == "ok" else "ok")
                self.assertFalse(passes(fm, body, table(rows + [twin])), (case, r))
                self.assertFalse(passes(fm, body, table([twin] + rows, indent=None)), (case, r))


if __name__ == "__main__":
    unittest.main()
