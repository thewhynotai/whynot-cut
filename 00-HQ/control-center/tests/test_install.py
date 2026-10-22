import copy, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import install as I  # noqa: E402

BASE = {"permissions": {"deny": ["Bash(rm -rf*)"]}, "model": "sonnet",
        "hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "other.sh"}]}]}}


class Settings(unittest.TestCase):
    def test_add_is_idempotent_and_keeps_other_hooks(self):
        s = I.add_entries(copy.deepcopy(BASE), "h1")
        s = I.add_entries(s, "h1")
        post = s["hooks"]["PostToolUse"]
        self.assertEqual(len(post), 2)
        self.assertEqual(post[0]["hooks"][0]["command"], "other.sh")
        self.assertIn("ownermsg.py\" hook h1", post[1]["hooks"][0]["command"])
        self.assertEqual(len(s["hooks"]["UserPromptSubmit"]), 1)
        self.assertIn("statusline.py\" h1", s["statusLine"]["command"])
        self.assertEqual(s["permissions"]["deny"][0], "Bash(rm -rf*)")  # existing rules kept first

    def test_helpers_cannot_write_control_center_code_or_state(self):
        deny = I.add_entries(copy.deepcopy(BASE), "h1")["permissions"]["deny"]
        for rule in ("Edit(//d/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/00-HQ/control-center/**)",
                     "Write(//d/0 Work/0 Pegasus IMC Agency/00 TWN/0 TWN AI/Editing Plugin/00-HQ/control-center/**)",
                     "Edit(//d/ClaudeData/control-center/**)", "Write(//d/ClaudeData/control-center/**)",
                     "Bash(*control-center*)"):
            self.assertIn(rule, deny)
        self.assertIn("Bash(rm -rf*)", deny)
        self.assertEqual(len(deny), len(set(deny)))
        again = I.add_entries(I.add_entries(copy.deepcopy(BASE), "h1"), "h1")["permissions"]["deny"]
        self.assertEqual(len(again), len(deny))

    def test_undo_removes_our_rules_even_if_the_state_folder_moved(self):
        s = copy.deepcopy(BASE)
        s["permissions"]["deny"].append("Edit(//e/elsewhere/control-center/**)")
        s["permissions"]["deny"].append("Bash(*control-center*)")
        self.assertEqual(I.remove_entries(s)["permissions"]["deny"], ["Bash(rm -rf*)"])

    def test_undo_restores_exactly(self):
        s = I.remove_entries(I.add_entries(copy.deepcopy(BASE), "h2"))
        self.assertEqual(s, BASE)

    def test_a_foreign_status_line_is_not_replaced(self):
        s = I.add_entries({"statusLine": {"type": "command", "command": "mine.sh"}}, "h1")
        self.assertEqual(s["statusLine"]["command"], "mine.sh")
        self.assertEqual(I.remove_entries(s), {"statusLine": {"type": "command", "command": "mine.sh"}})


if __name__ == "__main__":
    unittest.main()
