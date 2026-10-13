"""3.0 T3.9 — `reel settings --allow-reel`: merge Bash(reel *) / PowerShell(reel *) into the clients folder's
.claude/settings.json (other keys kept, idempotent, one timestamped backup before a change, never prompts).
Run:  bash tools/test.sh -p test_allow_reel.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import claude_perms  # noqa: E402

CLI = SK / "engine/reel/cli.py"
RULES = ["Bash(reel *)", "PowerShell(reel *)"]


def run(*argv, env_extra=None):
    """The CLI as the installer calls it: stdin closed (no prompt can be answered), (code, doc or text, stderr)."""
    from test_plugin import isolated_env
    r = subprocess.run([sys.executable, "-B", str(CLI), "settings", "--allow-reel", *argv], capture_output=True,
                       text=True, encoding="utf-8", stdin=subprocess.DEVNULL, env=isolated_env(env_extra), timeout=120)
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = r.stdout
    return r.returncode, doc, r.stderr


class AllowReel(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name) / "Clients"
        (self.root / "Dr A" / "assets").mkdir(parents=True)
        (self.root / "Dr A" / "data").mkdir()
        self.file = self.root / ".claude" / "settings.json"

    def write(self, text, bom=False):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))

    def load(self):
        return json.loads(self.file.read_text(encoding="utf-8"))

    def backups(self):
        return sorted(p.name for p in self.file.parent.glob("settings.json.whynot-backup-*"))

    def test_creates_the_file_without_a_backup(self):
        code, doc, _ = run("--clients-root", str(self.root), "--json")
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc, {"ok": True, "file": str(self.file), "added": RULES, "backup": None, "changed": True})
        self.assertEqual(self.load(), {"permissions": {"allow": RULES}})
        self.assertEqual(self.backups(), [])

    def test_existing_settings_are_kept_and_backed_up(self):
        before = {"model": "opus", "permissions": {"allow": ["Bash(git status)"], "deny": ["Read(.env)"], "defaultMode": "plan"},
                  "env": {"A": "1"}, "hooks": {"Stop": []}, "ناقل": "قيمة"}
        self.write(json.dumps(before, ensure_ascii=False))
        original = self.file.read_bytes()
        code, doc, _ = run("--clients-root", str(self.root))
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["added"], RULES)
        want = json.loads(json.dumps(before))
        want["permissions"]["allow"] += RULES
        self.assertEqual(self.load(), want)                          # every other key and rule survives
        self.assertEqual(list(self.load()), list(before))            # key order too
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(Path(doc["backup"]).read_bytes(), original)  # the backup is the file as it was

    def test_idempotent_and_backup_written_once(self):
        self.write('{"model": "opus"}')
        c1, d1, _ = run("--clients-root", str(self.root))
        first = self.file.read_bytes()
        c2, d2, _ = run("--clients-root", str(self.root))
        c3, d3, _ = run("--clients-root", str(self.root))
        self.assertEqual((c1, c2, c3), (0, 0, 0))
        self.assertEqual(d2["added"], [])
        self.assertIsNone(d2["backup"])
        self.assertFalse(d2["changed"])
        self.assertEqual(d3["added"], [])
        self.assertEqual(self.file.read_bytes(), first)              # untouched by the no-op runs
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(self.load()["permissions"]["allow"], RULES)  # no duplicates

    def test_one_missing_rule_is_added_and_an_equivalent_spelling_counts(self):
        self.write(json.dumps({"permissions": {"allow": ["Bash(reel:*)"]}}))
        code, doc, _ = run("--clients-root", str(self.root))
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["added"], ["PowerShell(reel *)"])
        self.assertEqual(self.load()["permissions"]["allow"], ["Bash(reel:*)", "PowerShell(reel *)"])

    def test_bom_is_tolerated(self):
        self.write('{"model": "opus"}', bom=True)
        code, doc, _ = run("--clients-root", str(self.root))
        self.assertEqual(code, 0, doc)
        self.assertEqual(self.load()["model"], "opus")
        self.assertEqual(self.load()["permissions"]["allow"], RULES)

    def test_malformed_json_is_guidance_and_the_file_is_untouched(self):
        for text in ('{"a": 1,}', '// note\n{"a": 1}', '{"a": ', "not json", ""):
            with self.subTest(text=text):
                self.write(text)
                raw = self.file.read_bytes()
                code, doc, err = run("--clients-root", str(self.root))
                self.assertEqual(code, 1)
                self.assertIs(doc["ok"], False)
                self.assertIn("how", doc)
                self.assertIn("settings.json", doc["error"])
                self.assertIn("nothing was changed", doc["error"])
                self.assertNotIn("Traceback", err + json.dumps(doc))
                self.assertEqual(self.file.read_bytes(), raw)
                self.assertEqual(self.backups(), [])

    def test_wrong_shapes_are_guidance(self):
        for body in ('[1]', '{"permissions": []}', '{"permissions": {"allow": "Bash(x)"}}'):
            with self.subTest(body=body):
                self.write(body)
                code, doc, _ = run("--clients-root", str(self.root))
                self.assertEqual(code, 1)
                self.assertIn("nothing was changed", doc["error"])
                self.assertEqual(self.file.read_text(encoding="utf-8"), body)

    def test_not_a_clients_root_is_refused(self):
        client = self.root / "Dr A"
        other = Path(self._t.name) / "Documents"
        other.mkdir()
        (other / "taxes.pdf").write_text("x")
        for folder, why in ((client, "client folder"), (client / "assets", "client folder"),
                            (Path(self._t.name) / "missing", "not a folder"), (other, "not a WhyNot Cut clients folder")):
            with self.subTest(folder=str(folder)):
                code, doc, _ = run("--clients-root", str(folder))
                self.assertEqual(code, 1)
                self.assertIn(why, doc["error"])
                self.assertIn("nothing was written", doc["error"])
        self.assertFalse((client / ".claude").exists())
        self.assertFalse((other / ".claude").exists())

    def test_an_empty_new_folder_and_the_configured_folder_are_accepted(self):
        empty = Path(self._t.name) / "NewClients"
        empty.mkdir()
        code, doc, _ = run("--clients-root", str(empty))
        self.assertEqual(code, 0, doc)
        other = Path(self._t.name) / "Mine"
        other.mkdir()
        (other / "notes.txt").write_text("x")
        code, doc, _ = run("--clients-root", str(other))
        self.assertEqual(code, 1)
        code, doc, _ = run("--clients-root", str(other), env_extra={"WHYNOT_CLIENTS_ROOT": str(other)})
        self.assertEqual(code, 0, doc)                                # it is the configured clients folder

    def test_default_is_the_configured_clients_folder_and_none_is_guidance(self):
        code, doc, _ = run(env_extra={"WHYNOT_CLIENTS_ROOT": str(self.root)})
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["file"], str(self.file))
        code, doc, _ = run()                                          # the isolation points it at nothing
        self.assertEqual(code, 1)
        self.assertIn("how", doc)

    def test_non_interactive_and_help_documents_the_contract(self):
        code, doc, _ = run("--clients-root", str(self.root))          # stdin is DEVNULL: a prompt would fail or hang
        self.assertEqual(code, 0, doc)
        from test_plugin import isolated_env
        h = subprocess.run([sys.executable, "-B", str(CLI), "settings", "--help"], capture_output=True, text=True,
                           encoding="utf-8", env=isolated_env(), timeout=120).stdout
        for word in ("--allow-reel", "--clients-root", "--json", "backup", "never asks"):
            self.assertIn(word, " ".join(h.split()))

    def test_module_merge_unit(self):
        doc = {"permissions": {"allow": ["Bash(ls *)"]}}
        self.assertEqual(claude_perms.merge_allow(doc), RULES)
        self.assertEqual(claude_perms.merge_allow(doc), [])
        self.assertEqual(doc["permissions"]["allow"], ["Bash(ls *)"] + RULES)


if __name__ == "__main__":
    unittest.main()
