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
ITEM_KEYS = {"id", "kind", "state", "status", "next", "next_step", "step", "stale", "updated", "file", "partial",
             "error"}
CLIENT_KEYS = {"name", "path", "prefix", "profile", "counts", "truncated", "error", "skipped", "items"}
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
                                         "blocked": 1, "done": 0, "not_scanned": 0})
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
        code, text, err = reel("board", "--clients-root", str(self.base), "--lang", "en")
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
        doc = self.board("--budget", "0")           # past the deadline: every client listed, none scanned
        self.assertTrue(doc["truncated"])
        self.assertEqual(doc["totals"]["not_scanned"], 2)
        for c in doc["clients"]:
            self.assertEqual((c["skipped"], c["items"], c["prefix"]), ("time budget", [], None), c)
        code, text, _ = reel("board", "--clients-root", str(self.base), "--budget", "0", "--lang", "en")
        self.assertTrue(any(ARABIC in ln and "not scanned (time budget)" in ln for ln in text.splitlines()), text)
        code, text, _ = reel("board", "--clients-root", str(self.base), "--budget", "0", "--lang", "ar")
        self.assertTrue(any(ARABIC in ln and "متفحصش" in ln for ln in text.splitlines()), text)

    def test_budget_running_out_inside_a_client(self):
        import time as _time

        def slow(p):
            _time.sleep(0.3)
            return {"next": "transcribe", "stale": []}
        for i in (1, 2):
            common.write_json(self.b / f"output/projects/C010{i}/08_quality_control/project-status.json",
                              {"video_id": f"C010{i}", "status": "TRANSCRIBED"})
        card, over = B.client_card(self.b, slow, _time.monotonic() + 0.15)
        self.assertTrue(over and card["truncated"])
        items = {it["id"]: it for it in card["items"]}
        self.assertFalse(items["C0100"]["partial"])                 # read before the deadline
        self.assertEqual(items["C0100"]["next"], "transcribe")
        self.assertTrue(items["C0101"]["partial"] and items["C0102"]["partial"])
        self.assertEqual(items["C0101"]["status"], "TRANSCRIBED")  # the recorded status still shows
        self.assertNotIn("new", {it["state"] for it in card["items"]}, "the data/ scan is skipped after the deadline")

    def test_one_failing_project_keeps_the_card(self):
        common.write_json(self.b / "output/projects/C0101/08_quality_control/project-status.json",
                          {"video_id": "C0101", "status": "TRANSCRIBED"})

        def flaky(p):
            if p.video_id == "C0101":
                raise ValueError("broken plan file")
            return {"next": "transcribe", "stale": []}
        card, _ = B.client_card(self.b, flaky, None)
        self.assertIsNone(card["error"])
        items = {it["id"]: it for it in card["items"]}
        self.assertEqual((items["C0101"]["state"], items["C0101"]["status"]), ("blocked", "TRANSCRIBED"))
        self.assertIn("broken plan file", items["C0101"]["error"])
        self.assertEqual(items["C0100"]["next"], "transcribe")
        self.assertIn("episode", {it["kind"] for it in card["items"]})
        text = B.table({"clients": [card], "totals": {}}, lang="en")
        self.assertTrue(any("C0101" in ln and "could not be read" in ln for ln in text.splitlines()), text)

    def test_prefix_is_scanned_once_per_card(self):              # fix-1 review m2: next_doc reuses the card's prefix
        from unittest import mock
        touch(self.b / "output/projects/C0100/07_premiere/project/C0100_RE_EDIT.prproj")

        def nxt(p):                                                 # like cli.next_doc: names the project file
            return {"next": f"ppro-build {p.video_id}_{common.project_prefix()}_EDIT", "stale": []}
        with mock.patch.object(common, "existing_prefix", wraps=common.existing_prefix) as spy:
            card, _ = B.client_card(self.b, nxt, None)
        self.assertEqual(card["prefix"], "RE")
        self.assertEqual(spy.call_count, 1)
        self.assertIn("C0100_RE_EDIT", {it["id"]: it for it in card["items"]}["C0100"]["next"])

    def test_table_in_arabic_by_default_done_folded(self):
        for i in range(3):
            common.write_json(self.b / f"output/projects/D000{i}/08_quality_control/project-status.json",
                              {"video_id": f"D000{i}", "status": "VERIFIED"})
        doc = B.board(self.base, next_fn=lambda p: {"next": "done" if p.video_id.startswith("D") else "transcribe"})
        self.assertEqual(self.card(doc, ARABIC)["counts"]["done"], 3)
        ar = B.table(doc)                                           # the editor's language: ar unless set
        self.assertIn("واقف", ar)
        self.assertIn("اختار الريلز", ar)
        self.assertNotIn("D0001", ar)
        self.assertTrue(any(ARABIC in ln and "+3" in ln for ln in ar.splitlines()), ar)
        self.assertIn("D0001", B.table(doc, show_all=True))
        en = B.table(doc, lang="en")
        self.assertIn("pick the reels", en)
        self.assertTrue(any("+3 done" in ln for ln in en.splitlines()), en)
        st = {it["id"]: it["state"] for c in doc["clients"] for it in c["items"]}
        self.assertEqual(st["C0100"], "blocked")                    # JSON keeps machine values
        code, text, err = reel("board", "--clients-root", str(self.base))
        self.assertEqual(code, 0, err)
        self.assertIn("اختار الريلز", text)
        code, text, err = reel("board", "--clients-root", str(self.base), "--lang", "en", "--all")
        self.assertEqual(code, 0, err)
        self.assertIn("pick the reels", text)


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


class BoardScale(unittest.TestCase):
    """Review I1: 200 clients plus one with 2,000 raw clips stay within the time budget (no quadratic id lookups,
    the budget covers every per-client step)."""
    BUDGET = 1.0
    MARGIN = 1.0

    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        cls.base = Path(cls._t.name) / "Clients"
        cls.big = client(cls.base, "Aaa Big Client")               # sorted first: scanned before the deadline
        for i in range(2000):
            touch(cls.big / f"data/Raw/C{i:05d}.MP4")
        for c in range(200):
            root = client(cls.base, f"Client {c:03d}")
            for i in range(3):
                touch(root / f"data/Raw/C{i:04d}.MP4")
            for i in range(2):
                common.write_json(root / f"output/projects/P{i:04d}/08_quality_control/project-status.json",
                                  {"video_id": f"P{i:04d}", "status": "TRANSCRIBED"})

    @classmethod
    def tearDownClass(cls):
        cls._t.cleanup()

    @staticmethod
    def nxt(p):
        return {"next": "transcribe", "stale": []}

    def test_clip_ids_are_linear(self):
        import time as _time
        from lib import clip_ids
        rels = [f"data/Raw/C{i:05d}.MP4" for i in range(2000)]
        t = _time.monotonic()
        ids = clip_ids.assign(self.big, rels, {})
        index = clip_ids.index(ids)
        found = [index.get(clip_ids.key(r)) for r in rels]
        self.assertLess(_time.monotonic() - t, 1.0)
        self.assertEqual(found[:2], ["C00000", "C00001"])
        self.assertEqual(len(set(found)), 2000)

    def test_big_client_alone(self):
        import time as _time
        t = _time.monotonic()
        card, over = B.client_card(self.big, self.nxt, _time.monotonic() + 30)
        self.assertLess(_time.monotonic() - t, 2.5)
        self.assertFalse(over)
        self.assertEqual(len(card["items"]), B.MAX_ITEMS)

    def test_whole_board_within_budget(self):
        import time as _time
        t = _time.monotonic()
        doc = B.board(self.base, next_fn=self.nxt, budget=self.BUDGET)
        took = _time.monotonic() - t
        self.assertLess(took, self.BUDGET + self.MARGIN, took)
        self.assertEqual(doc["totals"]["clients"], B.MAX_CLIENTS)          # 201 folders: the cap still applies
        self.assertTrue(doc["truncated"])
        for c in doc["clients"]:
            if c["skipped"]:
                self.assertEqual((c["items"], c["prefix"]), ([], None))

    def test_budget_zero_does_no_work(self):
        import time as _time
        t = _time.monotonic()
        doc = B.board(self.base, next_fn=self.nxt, budget=0)
        self.assertLess(_time.monotonic() - t, 0.5)
        self.assertEqual(doc["totals"]["not_scanned"], B.MAX_CLIENTS)

class Prefix(unittest.TestCase):
    def test_initials(self):
        for name, want in (("Dr Mona Adel", "MA"), ("Nour Hospital", "NH"), ("Acme", "AC"), ("Dr Karim", "KA"),
                           ("example clinic", "EC"), ("Prof. Ali Hassan Omar Zaki", "AHO"), ("Dr", "DR"),
                           (ARABIC, "WN"), ("مركز Nour", "NO"), ("Café Luna", "CL"), ("", "WN"), ("2024 ١", "WN")):
            self.assertEqual(common.initials_prefix(name), want, name)

    def test_valid_prefix(self):
        for ok in ("SH", "N-H", "Dr_M", "TOOLONGPREFIX", "RE2"):    # any file-name-safe 2.x value is honoured
            self.assertTrue(common.valid_prefix(ok), ok)
        for bad in ("<2-3 letters>", "", None, "A B", "N/H", "a:b", "x\\y", "..", "-", "a" * 40, "Q?", "A\tB", "a."):
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

    def test_stored_2x_prefix_is_kept(self):                  # review I2 (c)
        for value in ("N-H", "Dr_M", "LONGERTHAN8"):
            root = self._root("Nour Hospital")
            common.write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"prefix": value})
            self.assertEqual(self.prefix_of(root), value)

    def test_xml_only_2x_client_keeps_its_tag(self):             # review I2 (a)
        root = self._root("Old Client")
        touch(root / "output/projects/C0001/07_premiere/interchange/C0001_RE_EDIT.xml")
        self.assertEqual(self.prefix_of(root), "RE")
        other = self._root("Nour Hospital")                      # any tag, not only RE: XML, prproj, AE projects
        touch(other / "output/projects/DR_X_1/07_premiere/interchange/DR_X_1_N-H_EDIT_base.xml")
        self.assertEqual(self.prefix_of(other), "N-H")
        ae = self._root("Mona Adel")
        touch(ae / "output/projects/EP01_R03_MO/04_after_effects/project/EP01_R03_MO_ZQ_MOTION.aep")
        self.assertEqual(self.prefix_of(ae), "ZQ")
        unsafe = self._root("Hany Saad")                         # a tag that is not file-name-safe is not adopted
        touch(unsafe / "output/projects/C0001/07_premiere/project/C0001_a b_EDIT.prproj")
        self.assertEqual(self.prefix_of(unsafe), "HS")

    def test_scaffold_stores_the_prefix_and_a_renamed_folder_keeps_it(self):    # review I2 (b)
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name) / "Mona Adel"
        code, doc, err = reel("scaffold", "--root", str(root))
        self.assertEqual(code, 0, (doc, err))
        self.assertEqual(json.loads((root / ".whynot-client").read_text(encoding="utf-8"))["prefix"], "MA")
        renamed = root.rename(Path(t.name) / "Dr Mona Adel Clinic")
        self.assertEqual(self.prefix_of(renamed), "MA")
        code, doc, err = reel("client-init", "--root", str(renamed), "--id", "mona")
        self.assertEqual((code, doc["prefix"]), (0, "MA"), err)

    def test_client_init_validates_and_force_keeps_the_prefix(self):           # review M2
        root = self._root("Hany Saad")
        code, doc, _ = reel("client-init", "--root", str(root), "--id", "hany", "--prefix", "N H")
        self.assertEqual((code, doc["ok"]), (1, False), doc)
        self.assertIn("how", doc)
        self.assertFalse((root / common.CLIENT_PROFILE_REL / "profile.json").exists())
        code, doc, err = reel("client-init", "--root", str(root), "--id", "hany", "--prefix", "N-H")
        self.assertEqual((code, doc["prefix"]), (0, "N-H"), err)
        code, doc, err = reel("client-init", "--root", str(root), "--id", "hany", "--force")
        self.assertEqual((code, doc["prefix"]), (0, "N-H"), err)
        code, doc, err = reel("client-init", "--root", str(root), "--id", "hany", "--force", "--prefix", "HS")
        self.assertEqual((code, doc["prefix"]), (0, "HS"), err)
        code, doc, _ = reel("client-init", "--root", str(root), "--id", "hany", "--prefix", "a b")
        self.assertRegex(doc["how"], r"(?i)arabic")                # the message says what is accepted
        self.assertIn("'.'", doc["how"])

    def test_force_twice_never_loses_the_original_profile(self):  # fix-1 review N1
        root = self._root("Hany Saad")
        code, _, err = reel("client-init", "--root", str(root), "--id", "hany")
        self.assertEqual(code, 0, err)
        prof = root / common.CLIENT_PROFILE_REL
        (prof / "brand.json").write_text('{"ORIGINAL": "the editor\'s brand"}', encoding="utf-8")
        backups = []
        for _ in range(2):
            code, doc, err = reel("client-init", "--root", str(root), "--id", "hany", "--force")
            self.assertEqual(code, 0, err)
            backups += doc["backups"]
        originals = [f for f in prof.iterdir() if f.name.startswith("brand.json.bak")
                     and "ORIGINAL" in f.read_text(encoding="utf-8")]
        self.assertEqual(len(originals), 1, sorted(f.name for f in prof.iterdir()))
        self.assertEqual(sorted(f.name for f in prof.glob("brand.json.bak*")), ["brand.json.bak", "brand.json.bak.1"])
        self.assertIn("brand.json.bak.1", {Path(b).name for b in backups})

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

    def test_no_one_click_panel_approval_yet(self):             # review M1: the panel says "not available yet" (T6.2b)
        for p in [SK / "README.md"] + [SKILLS / n / "SKILL.md" for n in ("start", "help", "status")]:
            s = " ".join(p.read_text(encoding="utf-8").split())
            for bad in (r"(?i)one click|with a click|in chat,? or [^.]{0,30}(in )?the WhyNot Cut panel|approved? (it )?in the WhyNot Cut panel",
                        r"(?i)the plan to approve|بتعرض[^.]{0,60}الخطة اللي مستنية موافقتك"):
                m = re.search(bad, s)
                self.assertIsNone(m, f"{p.parent.name}/{p.name}: {m and m.group(0)}")
        for n in ("start", "help"):
            self.assertRegex(skill(n), r"(?i)panel[^.]*(coming|next update|not yet)", n)
        self.assertIn("وافق هنا في الشات", (SK / "README.md").read_text(encoding="utf-8"))

    def test_readme_has_no_gate_words_for_the_editor(self):     # review M4
        from test_skill_text import gate_word_issues
        self.assertEqual(gate_word_issues((SK / "README.md").read_text(encoding="utf-8")), [])

    def test_arabic_quick_start_names_the_launch_folder(self):  # review M5
        s = (SK / "README.md").read_text(encoding="utf-8")
        quick = s[s.find("## ابدأ"):s.find("## Install")]
        self.assertTrue(re.search(r"افتح Claude (جوه|في) مجلد العملاء", quick), "the launch folder in the Arabic quick start")

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
