"""3.0 T3.9 — `reel settings --allow-reel`: merge Bash(reel *) / PowerShell(reel *) into the clients folder's AND every
client folder's .claude/settings.json (other keys kept, idempotent, one timestamped backup before a change, under the
per-file lock, never prompts).
Run:  bash tools/test.sh -p test_allow_reel.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first
import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from unittest import mock
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
        self.client = self.root / "Dr A"
        (self.client / "assets").mkdir(parents=True)
        (self.client / "data").mkdir()
        self.file = self.root / ".claude" / "settings.json"

    def write(self, text, bom=False):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.file.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))

    def load(self):
        return json.loads(self.file.read_text(encoding="utf-8"))

    def backups(self, file=None):
        return sorted(p.name for p in (file or self.file).parent.glob("settings.json.whynot-backup-*"))

    def test_creates_the_file_without_a_backup(self):
        code, doc, _ = run("--clients-root", str(self.root), "--json")
        self.assertEqual(code, 0, doc)
        row = {"ok": True, "added": RULES, "backup": None, "changed": True}
        self.assertEqual(doc, {**row, "file": str(self.file),
                               "files": [{**row, "file": str(self.file)},
                                         {**row, "file": str(self.client / ".claude" / "settings.json")}]})
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

    # ---- fix round 1 (T3.9 review) --------------------------------------------------------------------------
    def test_i2_every_client_folder_gets_the_rule_and_a_non_client_does_not(self):
        marker_only = self.root / "عميل بعلامة"
        marker_only.mkdir()
        (marker_only / ".whynot-client").write_text("{}", encoding="utf-8")
        misc = self.root / "Misc"
        (misc / "docs").mkdir(parents=True)
        code, doc, _ = run("--clients-root", str(self.root), "--json")
        self.assertEqual(code, 0, doc)
        want = [self.file, self.client / ".claude" / "settings.json", marker_only / ".claude" / "settings.json"]
        self.assertEqual(sorted(f["file"] for f in doc["files"]), sorted(str(w) for w in want))
        self.assertEqual(doc["files"][0]["file"], str(self.file))           # files[0] is the clients folder
        for w in want:
            self.assertEqual(json.loads(w.read_text(encoding="utf-8")), {"permissions": {"allow": RULES}})
        self.assertFalse((misc / ".claude").exists())
        # a second run is a no-op everywhere: nothing written, no backups, changed false
        code, doc, _ = run("--clients-root", str(self.root))
        self.assertEqual(code, 0, doc)
        self.assertFalse(doc["changed"])
        self.assertTrue(all(not f["changed"] and f["backup"] is None for f in doc["files"]))
        for w in want:
            self.assertEqual(self.backups(w), [])

    def test_i2_changed_is_true_when_only_a_client_file_changed_and_existing_client_settings_are_backed_up(self):
        run("--clients-root", str(self.root))
        cf = self.client / ".claude" / "settings.json"
        cf.write_text(json.dumps({"model": "opus"}), encoding="utf-8")        # the editor reset one client
        code, doc, _ = run("--clients-root", str(self.root))
        self.assertEqual(code, 0, doc)
        self.assertEqual(doc["added"], [])                                    # files[0] (the clients folder): no change
        self.assertTrue(doc["changed"])                                       # ... but a client changed
        row = [f for f in doc["files"] if f["file"] == str(cf)][0]
        self.assertEqual(row["added"], RULES)
        self.assertEqual(len(self.backups(cf)), 1)
        self.assertEqual(json.loads(cf.read_text(encoding="utf-8"))["model"], "opus")

    def test_i2_client_option_targets_one_folder_only(self):
        other = self.root / "Dr B"
        (other / "assets").mkdir(parents=True)
        (other / "data").mkdir()
        code, doc, _ = run("--client", str(self.client), "--json")
        self.assertEqual(code, 0, doc)
        self.assertEqual([f["file"] for f in doc["files"]], [str(self.client / ".claude" / "settings.json")])
        self.assertEqual(doc["file"], doc["files"][0]["file"])
        self.assertFalse(self.file.exists())                                  # not the clients folder
        self.assertFalse((other / ".claude").exists())                        # not the other client
        for bad in (self.root, self.client / "assets", Path(self._t.name) / "missing"):
            with self.subTest(bad=str(bad)):
                code, doc, _ = run("--client", str(bad))
                self.assertEqual(code, 1)
                self.assertIn("nothing was written", doc["error"])
        code, doc, _ = run("--client", str(self.client), "--clients-root", str(self.root))
        self.assertEqual(code, 1)

    def test_i2_one_bad_client_file_does_not_stop_the_others(self):
        bad = self.client / ".claude" / "settings.json"
        bad.parent.mkdir()
        bad.write_text("{not json", encoding="utf-8")
        code, doc, _ = run("--clients-root", str(self.root))
        self.assertEqual(code, 1)
        self.assertIs(doc["ok"], False)
        self.assertIn("how", doc)
        self.assertEqual(bad.read_text(encoding="utf-8"), "{not json")
        self.assertEqual(self.load(), {"permissions": {"allow": RULES}})      # the clients folder still got it
        self.assertEqual([f["ok"] for f in doc["files"]], [True, False])

    def test_i2_help_states_the_launch_folder_fact(self):
        from test_plugin import isolated_env
        h = subprocess.run([sys.executable, "-B", str(CLI), "settings", "--help"], capture_output=True, text=True,
                           encoding="utf-8", env=isolated_env(), timeout=120).stdout
        flat = " ".join(h.split())
        for word in ("launched in", "every client folder", "--client", "files"):
            self.assertIn(word, flat)

    def test_i1_two_processes_do_not_lose_an_edit(self):
        """A holder reads, waits, adds its own rule and writes (a stale doc if nobody locked); the CLI starts while it
        waits. Under the lock the CLI queues behind it: both edits are in the file."""
        self.write('{"model": "opus"}')
        ready = Path(self._t.name) / "ready"
        holder = Path(self._t.name) / "holder.py"
        holder.write_text(f"""
import sys, time, json
sys.path.insert(0, {str(SK / "engine" / "reel")!r})
from pathlib import Path
from lib.file_lock import locked
from lib.common import read_json, write_json
f = Path({str(self.file)!r})
with locked(f):
    doc = read_json(f)
    Path({str(ready)!r}).write_text("x")
    time.sleep(2.0)
    doc.setdefault("permissions", {{}}).setdefault("allow", []).append("Bash(npm test)")
    write_json(f, doc)
""", encoding="utf-8")
        from test_plugin import isolated_env
        p = subprocess.Popen([sys.executable, "-B", str(holder)], env=isolated_env(), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        try:
            t0 = time.time()
            while not ready.exists() and time.time() - t0 < 30 and p.poll() is None:
                time.sleep(0.05)
            if not ready.exists():
                self.fail(p.communicate())
            res = claude_perms.apply_file(self.file)         # in this process: no start-up time, it runs inside the holder's wait
            self.assertTrue(res["changed"], res)
        finally:
            p.communicate(timeout=60)
        allow = self.load()["permissions"]["allow"]
        self.assertIn("Bash(npm test)", allow)
        for r in RULES:
            self.assertIn(r, allow)
        self.assertEqual(self.load()["model"], "opus")
        self.assertEqual(len(allow), len(set(allow)))

    def test_read_only_file_is_refused_with_the_right_hint_and_no_backup_pile_up(self):
        self.write('{"model": "opus"}')
        raw = self.file.read_bytes()
        os.chmod(self.file, stat.S_IREAD)
        self.addCleanup(lambda: os.chmod(self.file, stat.S_IREAD | stat.S_IWRITE))
        for _ in range(2):
            code, doc, err = run("--clients-root", str(self.root))
            self.assertEqual(code, 1)
            self.assertIn("read-only", doc["error"])
            self.assertIn("read-only", doc["files"][0]["error"])
            self.assertNotIn("folder is not read-only", doc["how"])
            self.assertNotIn("Traceback", err)
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.file.read_bytes(), raw)
        self.assertEqual(self.load()["model"], "opus")
        # the client folder was still done
        self.assertEqual(json.loads((self.client / ".claude" / "settings.json").read_text(encoding="utf-8")),
                         {"permissions": {"allow": RULES}})

    def test_a_failed_write_removes_the_fresh_backup(self):
        self.write('{"model": "opus"}')
        raw = self.file.read_bytes()
        import lib.common as C
        with mock.patch.object(C, "write_json", side_effect=PermissionError(13, "Access is denied")):
            with self.assertRaises(claude_perms.Guidance) as cm:
                claude_perms.apply_file(self.file)
        self.assertIn("cannot write", cm.exception.error)
        self.assertEqual(self.backups(), [])
        self.assertEqual(self.file.read_bytes(), raw)

    def test_a_failed_backup_is_guidance_not_a_raw_oserror(self):
        self.write('{"model": "opus"}')
        raw = self.file.read_bytes()
        with mock.patch.object(claude_perms.shutil, "copyfile", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(claude_perms.Guidance) as cm:
                claude_perms.apply_file(self.file)
        self.assertIn("backup", cm.exception.error)
        self.assertIn("nothing was changed", cm.exception.error)
        self.assertEqual(self.file.read_bytes(), raw)
        self.assertEqual(self.backups(), [])

    def test_arabic_paths(self):
        root = Path(self._t.name) / "عملاء"
        client = root / "د أحمد"
        (client / "assets").mkdir(parents=True)
        (client / "data").mkdir()
        code, doc, err = run("--clients-root", str(root), "--json")
        self.assertEqual(code, 0, (doc, err))
        f = client / ".claude" / "settings.json"
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")), {"permissions": {"allow": RULES}})
        self.assertIn(str(f), [x["file"] for x in doc["files"]])
        code, doc, err = run("--client", str(client))
        self.assertEqual(code, 0, (doc, err))
        self.assertFalse(doc["changed"])

    def test_dot_entries_rule(self):
        """Hidden entries of the OS / the editor's .claude do not make a folder 'not empty'; .git / .ssh do."""
        ok = Path(self._t.name) / "NewOk"
        (ok / ".claude").mkdir(parents=True)
        (ok / ".DS_Store").write_text("x")
        code, doc, _ = run("--clients-root", str(ok))
        self.assertEqual(code, 0, doc)
        for name in (".git", ".ssh"):
            with self.subTest(name=name):
                bad = Path(self._t.name) / ("Dot" + name)
                (bad / name).mkdir(parents=True)
                code, doc, _ = run("--clients-root", str(bad))
                self.assertEqual(code, 1)
                self.assertIn("not a WhyNot Cut clients folder", doc["error"])
                self.assertFalse((bad / ".claude").exists())

    def test_new_clients_inherit_the_rule_only_when_the_clients_folder_has_it(self):
        from lib import onboard
        fresh = self.root / "New One"
        r = onboard.scaffold(fresh)                                           # nothing opted in yet
        self.assertEqual(r["status"], "CREATED")
        self.assertNotIn("allow_reel", r)
        self.assertFalse((fresh / ".claude" / "settings.json").exists())
        code, doc, _ = run("--clients-root", str(self.root))
        self.assertEqual(code, 0, doc)
        again = self.root / "New Two"
        r = onboard.scaffold(again)                                           # the editor accepted: new client inherits
        self.assertTrue(r["allow_reel"]["ok"])
        self.assertEqual(r["allow_reel"]["added"], RULES)
        self.assertEqual(json.loads((again / ".claude" / "settings.json").read_text(encoding="utf-8")),
                         {"permissions": {"allow": RULES}})
        # client-init on an existing folder: idempotent and never a second backup
        from test_plugin import isolated_env
        for _ in range(2):
            r = subprocess.run([sys.executable, "-B", str(CLI), "client-init", "--root", str(self.client), "--id", "dr-a",
                                "--force"], capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL,
                               env=isolated_env(), timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.backups(self.client / ".claude" / "settings.json"), [])


if __name__ == "__main__":
    unittest.main()
