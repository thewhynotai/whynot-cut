# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Every Stage 1 (Gate 4) feature is reachable (plan session 2026-10-18, from the UI coverage map
docs/superpowers/specs/ui-coverage-map.md §2.1: a feature the editor cannot reach is not done). Each S1 verb is in
`reel --help` and is named as `reel <verb>` in at least one skill or agent text Claude reads.

PENDING lists the verbs whose hook set has not landed yet, GAPS the registered verbs no skill names yet. Both are
checked both ways: an entry still there must still be missing, so the test goes red the moment the verb lands and the
entry has to go. At the Gate 4 tag both are empty (a gate check)."""
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _isolation  # noqa: F401,E402

SK = Path(__file__).resolve().parents[1]
CLI = SK / "engine" / "reel" / "cli.py"

S1_VERBS = {
    "auto-approve": "T4.7 autopilot", "needs-you": "T4.7 one checklist", "transcript-verify": "K-T1 risky words first",
    "review-flags": "T4.13 review flags", "review-scan": "M1 review domains (Task 50)", "approve-plan": "approval",
    "removed-review": "K-T2 removed-review clip", "episode-sheet": "T4.4 episode sheet", "rules": "T4.3 client rules",
    "inbox": "T4.8 intake warnings", "preflight": "Task 26 intake normalisation", "conform": "Task 26 conform",
    "clean": "T4.15 free up space", "music": "T4.6 licensed music", "cut-proposals": "Task 25 cut proposals",
    "takes": "K-T7 takes", "safezone-check": "K-T4 safe zones", "client-move": "BL-14 take a copy / bring it back",
    "client-clone": "BL-14 clone", "looks": "Task 28 one suggested look", "ppro-build": "T4.1 smooth zoom + fades",
    "brief": "Task 58 briefs", "client-brief": "Task 59 client brief", "transcript-compact": "Task 58 compact transcript",
}
PENDING = {          # verb -> the hook set that registers it
    "review-scan": r"lane4\hooks\task50 (after Task 50 closes)",
    "rules": r"hooks\S1-T4.3 (security integration with BL-15)",
    "clean": r"hooks\T4.15 r3 (security integration with BL-15)",
    "cut-proposals": r"lane2\hooks\K-T7 (after Task 25 closes)",
    "takes": r"lane2\hooks\K-T7 (after Task 25 closes)",
    "safezone-check": r"lane2\hooks\K-T4",
}
GAPS = {             # registered, but no skill or agent names `reel <verb>` yet
    "removed-review": "edit skill: offer the removed-parts clip before approval",
    "client-clone": "handoff skill: next to client-move",
    "looks": "edit / podcast skill: `reel looks recommend` before the caption look is picked",
}


def help_verbs() -> set:
    out = subprocess.run([sys.executable, "-s", str(CLI), "--help"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=120).stdout
    return set(re.findall(r"(?m)^\s{2,}([a-z][a-z0-9-]+)\s", out)) | set(re.findall(r"[{,]([a-z][a-z0-9-]+)(?=[,}])", out))


def named_in_texts() -> set:
    texts = [p.read_text(encoding="utf-8") for p in [*SK.glob("skills/**/*.md"), *SK.glob("agents/*.md")]]
    return {v for v in S1_VERBS
            if any(re.search(r"reel(?:\.cmd)?\s+" + re.escape(v) + r"(?![\w-])", t) for t in texts)}


class TestS1Reachable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.help = help_verbs()
        cls.named = named_in_texts()

    def test_the_help_lists_the_verbs(self):
        self.assertIn("inbox", self.help)                         # the reader itself works
        self.assertGreater(len(self.help), 40)

    def test_every_s1_verb_is_registered_and_named(self):
        for v in sorted(set(S1_VERBS) - set(PENDING) - set(GAPS)):
            with self.subTest(verb=v, feature=S1_VERBS[v]):
                self.assertIn(v, self.help, "not in `reel --help`")
                self.assertIn(v, self.named, "no skill or agent text names `reel %s`" % v)

    def test_pending_and_gap_entries_are_still_missing(self):
        for v, why in PENDING.items():
            with self.subTest(pending=v):
                self.assertNotIn(v, self.help, f"`{v}` landed: remove it from PENDING ({why})")
        for v, why in GAPS.items():
            with self.subTest(gap=v):
                self.assertIn(v, self.help)
                self.assertNotIn(v, self.named, f"`reel {v}` is now named: remove it from GAPS ({why})")

    def test_the_lists_only_name_s1_verbs(self):
        self.assertLessEqual(set(PENDING) | set(GAPS), set(S1_VERBS))
        self.assertFalse(set(PENDING) & set(GAPS))


if __name__ == "__main__":
    unittest.main()
