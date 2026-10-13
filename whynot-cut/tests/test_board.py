"""3.0 T3.10 — UX for any editor: `reel board`, the file-name prefix without "RE", and the start/help/status texts.

- `reel board` (the table `/whynot-cut:status` shows with no arguments, and the JSON the Premiere panel shows): every
  client under the clients folder with its items, state and next step; Arabic client names; read-only; bounded by a
  time budget; a stable, documented JSON shape; exit codes per lib/errors.py (1 + guidance without a clients folder).
- The prefix: a stored one wins; else RE for a 2.x client that already has RE-named projects; else the client folder's
  ASCII initials; else WN. `client-init` stores it.
- start / help / status speak the three verbs, mention the WhyNot Cut panel in Premiere, and start's permission step
  uses `reel settings --allow-reel` with the workspace-trust dialog.
Run:  bash tools/test.sh -p test_board.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import re
import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import board as B, common  # noqa: E402

CLI = SK / "engine/reel/cli.py"
SKILLS = SK / "skills"
ARABIC = unicodedata.normalize("NFC", "عميل تجربة")
ITEM_KEYS = {"id", "kind", "state", "status", "next", "next_step", "stale", "updated", "file", "partial"}
CLIENT_KEYS = {"name", "path", "prefix", "profile", "counts", "truncated", "error", "items"}
TOP_KEYS = {"ok", "board", "clients_root", "generated", "elapsed_ms", "truncated", "totals", "clients"}


def reel(*argv, env=None):
    from test_plugin import isolated_env
    r = subprocess.run([sys.executable, "-B", str(CLI), *argv], capture_output=True, text=True, encoding="utf-8",
                       stdin=subprocess.DEVNULL, env=isolated_env(env), timeout=180)
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        doc = r.stdout
    return r.returncode, doc, r.stderr


def touch(f: Path, data: bytes = b"x"):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return f


def client(base: Path, name: str) -> Path:
    root = base / name
    (root / "assets").mkdir(parents=True)
    (root / "data" / "Raw").mkdir(parents=True)
    (root / ".whynot-client").write_text('{"whynot_client": 1}', encoding="utf-8")
    return root


def snapshot(base: Path) -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in base.rglob("*")}


class BoardFixture(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.base = Path(self._t.name) / "WhyNot Clients"
        # client 1 (ASCII): a new raw clip, and an episode waiting for the editor's pick
        self.a = client(self.base, "Dr Mona Adel")
        touch(self.a / "data/Raw/C0239.MP4")
        touch(self.a / "data/Episodes/EP01.mp4")
        ep = self.a / "output/episodes/EP01"
        for rel in ("00_inputs/episode.json", "02_transcription/transcript.json", "01_analysis/topics.json",
                    "01_analysis/speakers.json", "01_analysis/reels-plan.json", "01_analysis/reels-plan-validated.json",
                    "03_candidates/_sheet.jpg"):
            touch(ep / rel, b"{}")
        # client 2 (Arabic name): a blocked project, and a new Arabic-named episode
        self.b = client(self.base, ARABIC)
        common.write_json(self.b / "output/projects/C0100/08_quality_control/project-status.json",
                          {"video_id": "C0100", "status": "BLOCKED", "updated": "2026-10-13T10:00:00",
                           "history": [{"status": "BLOCKED", "at": "2026-10-13T10:00:00", "note": "x"}],
                           "stages": {}, "blockers": ["silent audio"]})
        touch(self.b / "data/Episodes/حلقة ١.mp4")

    def board(self, *extra):
        code, doc, err = reel("board", "--json", "--clients-root", str(self.base), *extra)
        self.assertEqual(code, 0, (doc, err))
        return doc

    def card(self, doc, name):
        return next(c for c in doc["clients"] if c["name"] == unicodedata.normalize("NFC", name))

    def test_two_clients_one_arabic(self):
        doc = self.board()
        self.assertEqual(set(doc), TOP_KEYS)
        self.assertEqual((doc["ok"], doc["board"], doc["truncated"]), (True, 1, False))
        self.assertEqual(sorted(c["name"] for c in doc["clients"]), sorted(["Dr Mona Adel", ARABIC]))
        a, b = self.card(doc, "Dr Mona Adel"), self.card(doc, ARABIC)
        self.assertEqual((a["prefix"], b["prefix"]), ("MA", "WN"))
        items = {it["id"]: it for it in a["items"]}
        self.assertEqual(items["C0239"]["state"], "new")
        self.assertEqual(items["C0239"]["file"], "data/Raw/C0239.MP4")
        self.assertIn("edit the new videos", items["C0239"]["next_step"])
        self.assertEqual((items["EP01"]["kind"], items["EP01"]["state"], items["EP01"]["next_step"]),
                         ("episode", "waiting_for_you", "pick the reels"))
        self.assertEqual(a["items"][0]["id"], "EP01")            # what waits for the editor comes first
        bitems = {it["kind"]: it for it in b["items"]}
        self.assertEqual((bitems["clip"]["id"], bitems["clip"]["state"], bitems["clip"]["status"]),
                         ("C0100", "blocked", "BLOCKED"))
        self.assertEqual(bitems["episode"]["state"], "new")
        self.assertRegex(bitems["episode"]["id"], r"^EP_[0-9A-F]+$")
        self.assertEqual(bitems["episode"]["file"], "data/Episodes/حلقة ١.mp4")
        self.assertEqual(doc["totals"], {"clients": 2, "items": 4, "new": 2, "working": 0, "waiting_for_you": 1,
                                         "blocked": 1, "done": 0})
        for c in doc["clients"]:
            self.assertEqual(set(c), CLIENT_KEYS)
            self.assertEqual(sum(c["counts"].values()), len(c["items"]))
            for it in c["items"]:
                self.assertEqual(set(it), ITEM_KEYS, it)
                self.assertIn(it["state"], B.STATES)
                self.assertNotRegex(it["next_step"], r"`|\breel\s|--", "the panel shows next_step as it is")

    def test_read_only(self):
        before = snapshot(self.base)
        self.board()
        code, _, _ = reel("board", "--clients-root", str(self.base))
        self.assertEqual(code, 0)
        self.assertEqual(snapshot(self.base), before)

    def test_plain_table(self):
        code, text, err = reel("board", "--clients-root", str(self.base))
        self.assertEqual(code, 0, err)
        self.assertIsInstance(text, str)
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("| Client"))
        self.assertRegex(lines[0], "[؀-ۿ]")
        self.assertTrue(any(ARABIC in ln and "blocked" in ln for ln in lines), text)
        self.assertTrue(any("EP01" in ln and "pick the reels" in ln for ln in lines), text)
        self.assertIn("2 clients · 4 videos · 1 waiting for you", text)

    def test_one_client_with_root(self):
        code, doc, err = reel("board", "--json", "--root", str(self.b))
        self.assertEqual(code, 0, err)
        self.assertEqual([c["name"] for c in doc["clients"]], [ARABIC])

    def test_time_budget_keeps_it_bounded(self):
        doc = self.board("--budget", "0")
        self.assertTrue(doc["truncated"])
        known = [it for c in doc["clients"] for it in c["items"] if it["state"] != "new"]
        self.assertTrue(known and all(it["partial"] and it["next"] is None for it in known), known)
        blocked = next(it for it in known if it["id"] == "C0100")
        self.assertEqual(blocked["state"], "blocked")             # the recorded status still shows

    def test_configured_clients_folder_is_the_default(self):
        code, doc, err = reel("board", "--json", env={"WHYNOT_CLIENTS_ROOT": str(self.base)})
        self.assertEqual(code, 0, err)
        self.assertEqual(doc["totals"]["clients"], 2)

    def test_exit_codes(self):
        missing = str(Path(self._t.name) / "nowhere")
        code, doc, _ = reel("board", "--json", "--clients-root", missing)
        self.assertEqual((code, doc["ok"]), (1, False))
        self.assertIn("how", doc)
        code, doc, _ = reel("board", "--json", "--root", str(self.a / "data"))
        self.assertEqual((code, doc["ok"]), (1, False))
        self.assertIn("not a client folder", doc["error"])

    def test_plain_step_never_names_a_command(self):
        for nxt in ("PLAYBACK edit-plan.md to editor, then approve-plan", "ppro-build (needs Premiere + bridge)",
                    "ppro-frames, LOOK at every frame, verify --record", "qc", "handoff", "transcribe", "done",
                    "SELECT reels (the editor picks; reels-select --by editor)", "motion-build (needs After Effects)",
                    "publish-check", "AUTHOR 01_analysis/edit-decisions.json", None):
            st = B._state(None, nxt)
            s = B.plain_step(nxt, "C0239", "clip", st)
            self.assertNotRegex(s, r"`|\breel\s|--|AUTHOR|PLAYBACK", (nxt, s))
        self.assertEqual(B.plain_step("PLAYBACK x", "C1", "clip", "waiting_for_you"), "approve the plan")


class Prefix(unittest.TestCase):
    def test_initials(self):
        for name, want in (("Dr Mona Adel", "MA"), ("Nour Hospital", "NH"), ("Acme", "AC"), ("Dr Karim", "KA"),
                           ("example clinic", "EC"), ("Prof. Ali Hassan Omar Zaki", "AHO"), ("Dr", "DR"),
                           (ARABIC, "WN"), ("مركز Nour", "NO"), ("Café Luna", "CL"), ("", "WN"), ("2024 ١", "WN")):
            self.assertEqual(common.initials_prefix(name), want, name)

    def test_valid_prefix(self):
        self.assertTrue(common.valid_prefix("SH"))
        for bad in ("<2-3 letters>", "", None, "A B", "شي", "TOOLONGPREFIX"):
            self.assertFalse(common.valid_prefix(bad), bad)

    def _root(self, name):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        return client(Path(t.name), name)

    def prefix_of(self, root):
        with common.use_context(common.Context(root)):
            return common.project_prefix()

    def test_derived_stored_and_legacy(self):
        new = self._root("Nour Hospital")
        self.assertEqual(self.prefix_of(new), "NH")
        self.assertEqual(self.prefix_of(self._root(ARABIC)), "WN")
        with common.use_context(common.Context(None)):
            self.assertEqual(common.project_prefix(), "WN")
        legacy = self._root("Old Client")                        # 2.x: built as RE, no stored prefix -> keeps RE
        touch(legacy / "output/projects/C0001/07_premiere/project/C0001_RE_EDIT.prproj")
        self.assertEqual(self.prefix_of(legacy), "RE")
        stored = self._root("Some Client")                       # a stored prefix always wins
        common.write_json(stored / common.CLIENT_PROFILE_REL / "profile.json", {"id": "some", "prefix": "ZZ"})
        touch(stored / "output/projects/C0001/07_premiere/project/C0001_RE_EDIT.prproj")
        self.assertEqual(self.prefix_of(stored), "ZZ")
        placeholder = self._root("Hany Saad")                    # the template's placeholder is not a prefix
        common.write_json(placeholder / common.CLIENT_PROFILE_REL / "profile.json", {"prefix": "<2-3 letters>"})
        self.assertEqual(self.prefix_of(placeholder), "HS")

    def test_defaults_no_longer_say_re(self):
        self.assertIsNone(json.loads((SK / "config/defaults/profile.json").read_text(encoding="utf-8"))["prefix"])

    def test_client_init_stores_the_prefix(self):
        root = self._root("Hany Saad")
        code, doc, err = reel("client-init", "--root", str(root), "--id", "hany")
        self.assertEqual(code, 0, (doc, err))
        self.assertEqual(doc["prefix"], "HS")
        pj = json.loads((root / common.CLIENT_PROFILE_REL / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual(pj["prefix"], "HS")
        code, doc, _ = reel("profile", "--root", str(root))
        self.assertEqual(doc["prefix"], "HS")
        other = self._root(ARABIC)
        code, doc, err = reel("client-init", "--root", str(other), "--id", "ar", "--prefix", "DS")
        self.assertEqual((code, doc["prefix"]), (0, "DS"), err)


def skill(name: str) -> str:
    return " ".join((SKILLS / name / "SKILL.md").read_text(encoding="utf-8").split())


class SkillTexts(unittest.TestCase):
    VERBS = ("drop files", "say what you want", "approve the plan")

    def test_three_verbs_in_start_help_status(self):
        for n in ("start", "help", "status"):
            s = skill(n).lower()
            for v in self.VERBS:
                self.assertIn(v, s, f"{n}: {v}")

    def test_help_is_contextual(self):
        s = skill("help")
        self.assertIn("reel next", s)
        self.assertIn("reel board", s)

    def test_status_without_arguments_shows_the_board(self):
        s = skill("status")
        self.assertRegex(s, r"(?i)no (clip|arguments?|video)[^.]*reel board")
        self.assertIn("reel board --json", s)

    def test_panel_in_premiere_is_mentioned(self):
        for n in ("start", "help", "status"):
            self.assertRegex(skill(n), r"WhyNot Cut panel", n)
        self.assertRegex(skill("start"), r"(?i)never types? (a )?commands?")

    def test_start_permission_step(self):
        s = skill("start")
        self.assertIn("reel settings --allow-reel", s)
        self.assertRegex(s, r"(?i)workspace.trust")
        self.assertRegex(s, r"(?i)folder (Claude|it) is (started|launched|opened) in")
        self.assertIn(".claude/settings.json.lock", s)
        self.assertIn("guard_active: false", s)

    def test_start_links_the_installer_reference_when_present(self):
        s = skill("start")
        self.assertIn("${CLAUDE_SKILL_DIR}/references/install-from-claude.md", s)
        self.assertRegex(s, r"(?i)when [^.]*install-from-claude\.md[^.]*(present|exists)")

    def test_no_re_default_left_in_user_text(self):
        for p in [SK / "README.md"] + sorted(SKILLS.glob("*/SKILL.md")):
            self.assertNotRegex(p.read_text(encoding="utf-8"), r"_RE_EDIT|default RE\b", p)

    def test_readme_quick_start_is_arabic_first(self):
        s = (SK / "README.md").read_text(encoding="utf-8")
        ar = s.find("## ابدأ")
        self.assertGreater(ar, 0, "an Arabic quick-start heading")
        self.assertLess(ar, s.find("## Install"), "the Arabic quick start comes before the English install")
        self.assertIn("reel board", s)


class EngineWording(unittest.TestCase):
    """Engine text that reaches the editor says "approve the plan" / "pick the reels", not Gate 0/1 (status codes and
    internal comments keep their names)."""

    def test_motion_messages(self):
        for rel in ("engine/reel/lib/motion_build.py", "engine/reel/lib/motion_cli.py", "engine/reel/lib/motion_qc.py",
                    "engine/reel/lib/podcast_cli.py", "engine/reel/lib/episode.py", "engine/reel/lib/reels.py"):
            src = (SK / rel).read_text(encoding="utf-8")
            strings = re.findall(r'(?<![#\w])f?"(?:[^"\\\n]|\\.)*"', src)
            bad = [s_ for s_ in strings if re.search(r"\bGate\s*[012]\b", s_)]
            self.assertEqual(bad, [], rel)


if __name__ == "__main__":
    unittest.main()
