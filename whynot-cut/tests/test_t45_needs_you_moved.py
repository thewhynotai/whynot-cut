# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 part B, executor ruling (c) on BL-14 Q1: NEEDS-YOU lists each approval a client move voided, by
item and kind, Arabic first («اتنقل العميل: وافق تاني على الخطة لـ R01»), until the editor gives it again. Goes with
hooks/BL-14/needs_you.patch (lib/needs_you.py: the `moved` kind and `_moved`; schemas/needs-you.schema.json: the enum).
Run:  bash tools/test.sh -p test_t45_needs_you_moved.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import client_move as CM, needs_you, plan as PL, schemas  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from test_t45_move_approvals import Approved  # noqa: E402
from test_t47_needs_you import JARGON  # noqa: E402


class TestNeedsYouAfterAMove(Approved):
    def move(self):
        self.hold()
        doc = CM.move(self.src, self.dest, apply=True)
        self.assertTrue(doc.get("applied"), doc)

    def moved_items(self, root) -> list:
        return [i for i in needs_you.collect(root)["items"] if i["kind"] == "moved"]

    def test_nothing_before_a_move(self):
        self.assertEqual(self.moved_items(self.src), [])

    def test_each_voided_approval_is_one_line_arabic_first(self):
        self.move()
        doc = needs_you.collect(self.dest)
        self.assertEqual(schemas.validate(doc, "needs-you"), [])
        items = self.moved_items(self.dest)
        self.assertEqual(sorted((i["item"], i["ref"]) for i in items),
                         sorted((k[1], CM._entry(*k)["file"]) for k in self.ALL))
        plan = next(i for i in items if i["item"] == "R01" and i["ref"].endswith("plan-approval.json"))
        self.assertEqual(plan["text_ar"], "اتنقل العميل: وافق تاني على الخطة لـ R01")
        self.assertEqual(plan["text"], "client moved: approve the plan again for R01")
        for i in items:                                # review r1 P2-3: no commands or flags for the editor
            for k in ("text", "text_ar", "why", "why_ar"):
                self.assertIsNone(JARGON.search(i[k]), i[k])
        md = needs_you.render_md(doc)
        self.assertIsNone(JARGON.search(md), JARGON.search(md) and md[JARGON.search(md).start() - 60:][:120])
        self.assertIn("موافقات تتعمل تاني بعد نقل العميل", md)
        self.assertLess(md.index("وافق تاني على الخطة"), md.index("approve the plan again"))     # Arabic first
        self.assertEqual(doc["unread"], [])

    def test_a_line_goes_once_its_approval_is_given_again(self):
        self.move()
        q = Paths(self.dest, "R01")
        write_json(q.p("01_analysis/plan-approval.json"), {"approved": True, "by": "editor",
                                                            "format": PL.APPROVAL_FORMAT,
                                                            "plan_fingerprint": PL.plan_fingerprint(q)})
        refs = [i["ref"] for i in self.moved_items(self.dest)]
        self.assertNotIn("output/projects/R01/01_analysis/plan-approval.json", refs)
        self.assertEqual(len(refs), len(self.ALL) - 1)

    def test_a_damaged_record_is_named_unread_not_hidden(self):
        self.move()
        (self.dest / CM.VOIDED_REL).write_text("{not json", encoding="utf-8")
        doc = needs_you.collect(self.dest)
        self.assertEqual(self.moved_items(self.dest), [])
        self.assertIn(CM.VOIDED_REL, [u["source"] for u in doc["unread"]])


if __name__ == "__main__":
    unittest.main()
