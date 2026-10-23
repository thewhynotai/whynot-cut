# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.4 — `reel episode-sheet --init <EP>`: a filled episode-sheet template in output/, never in data/.

The template goes to output/episodes/<EP>/, named like the episode file (EP12.mp4 -> EP12.md), so the editor moves it
next to the episode in data/Episodes/ without renaming. Its frontmatter is what `episode.parse_sheet` reads; every
value is empty until the editor fills it (guidance only in `#` comments), so an untouched template never puts
placeholder text into the publish copy. The client's people[] are listed (name, role, gender, honorifics) for the
editor to copy; nobody is put into host or guest by guessing. Case list: the wnc-queue track's task notes.
Run:  bash tools/test.sh -p test_t44_episode_sheet.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib import client_move_paths as CMP  # noqa: E402
from lib import common  # noqa: E402
from lib import episode_sheet as ES  # noqa: E402
from lib.common import write_json  # noqa: E402
from lib.episode import parse_sheet  # noqa: E402
from lib.errors import Guidance  # noqa: E402

CLI = SK / "engine/reel/cli.py"
KARIM = {"name": "Dr. Karim Test / د. كريم تجربة", "role": "client: the doctor on camera", "gender": "male",
         "honorific_ar": "الدكتور", "honorific_en": "Dr.", "pronouns": "he/him"}
NOUR = {"name": "Nour Placeholder / نور بليسهولدر", "role": "off-camera interviewer", "gender": "unknown",
        "honorific_ar": "", "honorific_en": "", "pronouns": ""}
PERSON_FIELDS = ("host", "guest")
EMPTY_KEYS = ("show", "host", "host_honorific_ar", "host_honorific_en", "guest", "guest_honorific_ar",
              "guest_honorific_en", "topics", "sponsor", "publish_date")


def env():
    from test_plugin import isolated_env
    return isolated_env()


def make_client(tmp: Path, name: str = "Dr Test د. تجربة") -> Path:
    root = tmp / name                                    # spaces + Arabic in the client folder
    for d in ("assets/Brand", "data/Raw", "data/Episodes"):
        (root / d).mkdir(parents=True)
    (root / ".whynot-client").write_text("{}", encoding="utf-8")
    return root


def tree(folder: Path) -> dict:
    """Names, sizes and mtimes of everything under a folder (links not followed): proves nothing was written."""
    out = {}
    for dp, dns, fns in os.walk(folder):
        for n in dns + fns:
            p = Path(dp) / n
            st = p.lstat()
            out[str(p.relative_to(folder))] = (st.st_size, st.st_mtime_ns)
    return out


def dir_link(link: Path, target: Path):
    """A directory link (a junction on Windows, which needs no privilege; a symlink elsewhere)."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = make_client(self.tmp)
        self.ep_dir = self.root / "data/Episodes"

    def tearDown(self):
        common.set_context(None)
        for dp, dns, _fns in os.walk(self.tmp):          # unlink our links first: never delete through one
            for n in dns:
                p = Path(dp) / n
                if p.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(p)):
                    os.rmdir(p) if os.name == "nt" else p.unlink()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def episode(self, rel: str = "EP12.mp4") -> Path:
        f = self.ep_dir / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\0" * 64)                          # discovery classifies by name; nothing probes it here
        return f

    def people(self, *people):
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"id": "cl-test", "people": list(people)})

    def init(self, eid: str = "EP12", force: bool = False) -> dict:
        return ES.init(self.root, eid, force=force)


class TestTemplate(Base):
    def test_writes_the_template_into_output_and_says_where_to_move_it(self):
        self.episode()
        before = tree(self.root / "data")
        r = self.init()
        self.assertTrue(r["ok"], r)
        sheet = self.root / "output/episodes/EP12/EP12.md"
        self.assertEqual(Path(r["sheet"]), sheet)
        self.assertTrue(sheet.is_file())
        self.assertEqual(r["sheet_rel"], "output/episodes/EP12/EP12.md")
        self.assertEqual(r["move_to"], "data/Episodes/EP12.md")
        self.assertEqual(r["episode_file"], "data/Episodes/EP12.mp4")
        self.assertIn("data/Episodes/EP12.md", r["next"])
        self.assertEqual(tree(self.root / "data"), before, "nothing under data/ changed")

    def test_fields_parse_with_the_shipped_reader(self):
        self.episode()
        s = parse_sheet((self.root / self.init()["sheet_rel"]).read_text(encoding="utf-8"))
        self.assertEqual(s["episode"], "EP12")
        for k in ("show", "host", "host_gender", "host_honorific_ar", "host_honorific_en", "guest", "guest_gender",
                  "guest_honorific_ar", "guest_honorific_en", "topics", "sponsor", "links", "publish_date", "avoid"):
            self.assertIn(k, s, k)
        self.assertEqual((s["host_gender"], s["guest_gender"]), ("unknown", "unknown"))   # never guessed
        self.assertEqual((s["links"], s["avoid"]), ([], []))

    def test_an_untouched_template_puts_no_placeholder_text_anywhere(self):
        """Moved into data/ unfilled, it must not give the publish copy a fake guest, show name or link. episode-prep
        keeps the WHOLE text (comments too) as sheet_text: the publish writer takes names from it and publish-check
        builds its allowed links from it, so the comments must carry none either (T4.4 review P1-1)."""
        self.episode()
        self.people(KARIM, NOUR)
        text = (self.root / self.init()["sheet_rel"]).read_text(encoding="utf-8")
        s = parse_sheet(text)
        for k in EMPTY_KEYS:
            self.assertEqual(s[k], "", f"{k} = {s[k]!r}")
        self.assertEqual(s["_notes"], "")
        from lib.motion_script import fill_placeholders
        self.assertEqual(fill_placeholders("{guest}", s)[1], ["guest"])          # still missing: nothing invented
        from lib.publish import urls_in
        self.assertEqual(urls_in(text), [])
        for p in (KARIM, NOUR):                                                  # the client's people: not in the
            for part in p["name"].split(" / "):                                  # sheet text
                self.assertNotIn(part, text)
        self.assertNotIn("منى", text)

    def test_profile_people_come_back_in_the_result_never_assigned(self):
        self.episode()
        self.people(KARIM, NOUR)
        r = self.init()
        s = parse_sheet((self.root / r["sheet_rel"]).read_text(encoding="utf-8"))
        for k in PERSON_FIELDS:
            self.assertEqual(s[k], "")
        self.assertEqual(r["people"], [{k: p[k] for k in ES.PERSON_KEYS} for p in (KARIM, NOUR)])
        self.assertIn("people", r["next"])

    def test_the_profile_override_is_honoured(self):
        """--profile (the CLI's context) is where the people come from, like everywhere else in the engine."""
        self.episode()
        common.set_context(self.root, "example-clinic")
        names = [p["name"] for p in self.init()["people"]]
        self.assertTrue(any("Sample Example" in n for n in names), names)

    def test_sheet_people_turns_a_filled_sheet_into_people_entries(self):
        sheet = parse_sheet("---\nhost: Nour Placeholder\nguest: د. منى سالم — استشاري جلدية\nguest_gender: female\n"
                            "guest_honorific_ar: الدكتورة\nguest_honorific_en: Dr.\nguest_2: Karim Test — مهندس\n"
                            "guest_2_gender: f\n---\n")
        people, issues = ES.sheet_people(sheet)
        self.assertEqual([(p["role"], p["name"], p["gender"]) for p in people],
                         [("host", "Nour Placeholder", "unknown"), ("guest", "د. منى سالم", "female"),
                          ("guest_2", "Karim Test", "unknown")])
        self.assertTrue(any("the sheet's guest_2" in i and "'f'" in i for i in issues), issues)
        bad, issues = ES.sheet_people(parse_sheet("---\nguest: د. منى سالم\nguest_gender: female\n"
                                                  "guest_honorific_ar: الدكتور\n---\n"))
        self.assertTrue(any("the sheet's guest" in i and "does not match" in i for i in issues), issues)
        self.assertEqual(ES.sheet_people(parse_sheet(self.template_text()))[0], [])   # untouched: nobody
        people, issues = ES.sheet_people(parse_sheet("---\nguest: [Karim Test, Nour Placeholder]\n---\n"))
        self.assertEqual(people, [])                                   # never "['Karim Test', 'Nour Placeholder']"
        self.assertTrue(any("guest in the episode sheet is a list" in i for i in issues), issues)
        # review c963132 P2-1 (executor ruling): a name is one value written as text; a one-item list is a list too
        one, issues = ES.sheet_people(parse_sheet("---\nguest:\n- Karim Test\n---\n"))
        self.assertEqual(one, [])
        self.assertTrue(any("guest in the episode sheet is a list" in i for i in issues), issues)

    def test_name_problems_accepts_only_text(self):
        """Review c963132 P2-1: host, guest, guest_2 … guest_9 and show must each be one name written as text; an
        empty or absent value is "not given". Every other value gets one plain line (English and Arabic) that never
        shows the value's Python form."""
        ok = {"host": "Nour Placeholder", "guest": "", "guest_9": "Karim Test — مهندس", "show": "My Show",
              "topics": ["a", "b"], "episode": 12, "guest_10": ["not a sheet person"]}
        self.assertEqual(ES.name_problems(ok), [])
        self.assertEqual(ES.name_problems({}), [])
        for key, val in (("host", ["Nour"]), ("guest", ["A", "B"]), ("guest_2", {"name": "X"}), ("guest_9", 123),
                         ("show", True), ("host", None), ("show", 1.5)):
            bad = ES.name_problems({key: val})
            self.assertEqual(len(bad), 1, (key, val))
            self.assertTrue(bad[0].startswith(f"{key} in the episode sheet "), bad)
            self.assertIn(f"`{key}: ", bad[0])
            self.assertIn("في شيت الحلقة", bad[0])
            for part in ("['", "{'", "123", "True", "None", "1.5"):
                self.assertNotIn(part, bad[0], (key, val))
            self.assertEqual(ES.sheet_text(val), "")
        self.assertEqual(ES.sheet_text("  Nour  "), "Nour")

    def template_text(self) -> str:
        return ES.render("EP12", "data/Episodes/EP12.mp4", "data/Episodes/EP12.md")

    def test_no_profile_or_no_people_is_fine(self):
        self.episode()
        r = self.init()
        self.assertTrue(r["ok"], r)
        self.people()
        self.assertTrue(self.init(force=True)["ok"])

    def test_utf8_without_bom_and_lf(self):
        self.episode()
        self.people(KARIM)
        raw = (self.root / self.init()["sheet_rel"]).read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", raw)
        raw.decode("utf-8")


class TestNames(Base):
    def test_an_arabic_episode_file_names_the_sheet_after_it(self):
        self.episode("الحلقة ١٢.mp4")
        from lib.episode import episode_id_for
        eid = episode_id_for(Path("الحلقة ١٢.mp4"))
        r = self.init(eid)
        self.assertEqual(r["move_to"], "data/Episodes/الحلقة ١٢.md")
        self.assertEqual(Path(r["sheet"]).name, "الحلقة ١٢.md")
        self.assertEqual(Path(r["sheet"]).parent, self.root / "output/episodes" / eid)
        self.assertEqual(parse_sheet(Path(r["sheet"]).read_text(encoding="utf-8"))["episode"], eid)

    def test_an_episode_in_a_subfolder(self):
        self.episode("Season 2/EP12.mp4")
        r = self.init()
        self.assertEqual(r["move_to"], "data/Episodes/Season 2/EP12.md")
        self.assertEqual(r["episode_file"], "data/Episodes/Season 2/EP12.mp4")

    def test_an_audio_only_episode(self):
        self.episode("EP12.m4a")
        r = self.init()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["move_to"], "data/Episodes/EP12.md")

    def test_the_episode_file_is_not_there_yet(self):
        r = self.init()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["sheet_rel"], "output/episodes/EP12/EP12.md")
        self.assertIsNone(r["episode_file"])
        self.assertTrue(any("name it like the episode file" in w for w in r["warnings"]), r["warnings"])
        self.assertEqual(r["move_to"], "data/Episodes/EP12.md")

    def test_duplicate_ids_use_the_file_the_episode_id_means(self):
        self.episode("EP12.mp4")
        self.episode("EP12.mov")
        r = self.init()
        self.assertEqual(r["episode_file"], "data/Episodes/EP12.mov")   # sorted by rel: what --episode EP12 means
        self.assertTrue(any("duplicate episode id" in w for w in r["warnings"]), r["warnings"])

    def test_bad_ids_are_refused_before_anything_is_written(self):
        self.episode()
        before = tree(self.root / "data")
        for bad in ("../data", "EP/1", "EP\\1", "C:x", ".", "..", "", " EP12", "EP 12"):
            with self.subTest(bad=bad):
                with self.assertRaises(Guidance):
                    self.init(bad)
        self.assertFalse((self.root / "output").exists(), "not even discovery ran")
        self.assertEqual(tree(self.root / "data"), before)


class TestRefusals(Base):
    def test_a_sheet_already_in_data_is_refused(self):
        self.episode()
        (self.ep_dir / "EP12.md").write_text("---\nguest: X\n---\n", encoding="utf-8")
        before = tree(self.root / "data")
        r = self.init()
        self.assertIn("refused", r)
        self.assertIn("data/Episodes/EP12.md", r["refused"])
        self.assertFalse((self.root / "output/episodes/EP12/EP12.md").exists())
        r = self.init(force=True)                                       # the template anyway, still only in output/
        self.assertTrue(r["ok"], r)
        self.assertTrue((self.root / "output/episodes/EP12/EP12.md").is_file())
        self.assertEqual(tree(self.root / "data"), before)

    def test_a_rerun_changes_nothing(self):
        self.episode()
        f = self.root / self.init()["sheet_rel"]
        t0 = f.stat().st_mtime_ns
        r = self.init()
        self.assertTrue(r["ok"] and r["unchanged"], r)
        self.assertEqual(f.stat().st_mtime_ns, t0)

    def test_an_edited_template_is_kept_unless_forced(self):
        self.episode()
        f = self.root / self.init()["sheet_rel"]
        edited = f.read_text(encoding="utf-8").replace("\nguest:\n", "\nguest: د. منى — استشاري\n", 1)
        self.assertEqual(parse_sheet(edited)["guest"], "د. منى — استشاري")
        f.write_text(edited, encoding="utf-8", newline="\n")
        r = self.init()
        self.assertIn("refused", r)
        self.assertEqual(f.read_text(encoding="utf-8"), edited)
        r = self.init(force=True)                         # a fresh template, the editor's values kept aside
        self.assertTrue(r["ok"], r)
        self.assertEqual(parse_sheet(f.read_text(encoding="utf-8"))["guest"], "")
        self.assertRegex(r["backup"], r"^output/episodes/EP12/EP12\.before-\d{8}-\d{6}\.md$")
        self.assertEqual((self.root / r["backup"]).read_text(encoding="utf-8"), edited)

    def test_a_template_with_only_its_notes_changed_is_refreshed(self):
        """A newer template (other notes) or a note the editor touched: no value changed, so nothing is lost."""
        self.episode()
        f = self.root / self.init()["sheet_rel"]
        f.write_text(f.read_text(encoding="utf-8").replace("# show:", "# my own note\n# show:"), encoding="utf-8",
                     newline="\n")
        r = self.init()
        self.assertTrue(r["ok"] and r["refreshed"] and not r["unchanged"], r)
        self.assertNotIn("my own note", f.read_text(encoding="utf-8"))
        self.assertIn("my own note", (self.root / r["backup"]).read_text(encoding="utf-8"))   # kept (review 2 P2-2)

    def test_two_backups_in_one_second_never_overwrite_each_other(self):
        self.episode()
        f = self.root / self.init()["sheet_rel"]
        backups = []
        for guest in ("أ", "ب"):
            f.write_text(f.read_text(encoding="utf-8").replace("\nguest:\n", f"\nguest: {guest}\n"), encoding="utf-8",
                         newline="\n")
            backups.append(self.init(force=True)["backup"])
        self.assertEqual(len(set(backups)), 2, backups)
        self.assertEqual([parse_sheet((self.root / b).read_text(encoding="utf-8"))["guest"] for b in backups],
                         ["أ", "ب"])

    def test_a_sheet_first_already_moved_into_data_is_refused(self):
        """No episode file yet, but EP12.md already sits in data/Episodes: a fresh template moved there would
        replace the editor's filled sheet (T4.4 review P1-3)."""
        (self.ep_dir / "Season 2").mkdir()
        (self.ep_dir / "Season 2/ep12.md").write_text("---\nguest: X\n---\n", encoding="utf-8")
        r = self.init()
        self.assertIn("refused", r)
        self.assertIn("data/Episodes/Season 2/ep12.md", r["refused"])
        self.assertFalse((self.root / "output/episodes/EP12").exists())
        self.assertTrue(self.init(force=True)["ok"])

    def test_the_id_matches_ignoring_case(self):
        self.episode()
        r = self.init("ep12")
        self.assertEqual((r["episode_id"], r["sheet_rel"]), ("EP12", "output/episodes/EP12/EP12.md"))
        self.assertTrue(any("using EP12" in w for w in r["warnings"]), r["warnings"])

    def test_an_unknown_id_lists_the_known_ones(self):
        self.episode()
        r = self.init("EP13")
        self.assertTrue(any("known: EP12" in w for w in r["warnings"]), r["warnings"])

    def test_a_sheet_in_another_folder_or_format_is_named(self):
        self.episode("Season 2/EP12.mp4")
        (self.ep_dir / "EP12.md").write_text("---\n---\n", encoding="utf-8")       # not next to the episode
        (self.ep_dir / "Season 2/EP12.docx").write_bytes(b"PK")                     # not a format prep reads
        r = self.init()
        self.assertTrue(r["ok"], r)
        self.assertTrue(any("data/Episodes/EP12.md is in another folder" in w for w in r["warnings"]), r["warnings"])
        self.assertTrue(any("EP12.docx is not read as the sheet" in w for w in r["warnings"]), r["warnings"])

    def test_a_file_where_the_folder_goes_and_a_folder_where_the_file_goes(self):
        self.episode()
        (self.root / "output/episodes").mkdir(parents=True)
        (self.root / "output/episodes/EP12").write_text("x", encoding="utf-8")
        self.assertIn("refused", self.init())
        (self.root / "output/episodes/EP12").unlink()
        (self.root / "output/episodes/EP12/EP12.md").mkdir(parents=True)
        self.assertIn("refused", self.init(force=True))


class TestNeverIntoData(Base):
    """A link inside output/ that leads into data/ (or assets/) must never carry the write there."""

    def refused_and_untouched(self):
        before = (tree(self.root / "data"), tree(self.root / "assets"))
        r = self.init()
        self.assertIn("refused", r)
        self.assertIn("data/", r["refused"] + r.get("how", ""))
        self.assertEqual((tree(self.root / "data"), tree(self.root / "assets")), before)
        return r

    def test_output_episodes_is_a_link_into_data(self):
        self.episode()
        (self.root / "output").mkdir()
        dir_link(self.root / "output/episodes", self.ep_dir)
        self.refused_and_untouched()

    def test_the_episode_folder_is_a_link_into_data(self):
        self.episode()
        (self.root / "output/episodes").mkdir(parents=True)
        dir_link(self.root / "output/episodes/EP12", self.ep_dir)
        self.refused_and_untouched()

    def test_output_itself_is_a_link_into_data(self):
        self.episode()
        (self.root / "data/out").mkdir()
        dir_link(self.root / "output", self.root / "data/out")
        before = tree(self.root / "data")
        r = ES.init(self.root, "EP12")
        self.assertIn("refused", r)
        self.assertEqual(tree(self.root / "data"), before)

    def test_a_link_into_assets(self):
        self.episode()
        (self.root / "output/episodes").mkdir(parents=True)
        dir_link(self.root / "output/episodes/EP12", self.root / "assets/Brand")
        before = tree(self.root / "assets")
        r = self.init()
        self.assertIn("refused", r)
        self.assertEqual(tree(self.root / "assets"), before)

    def test_the_target_file_is_a_symlink_into_data(self):
        self.episode()
        (self.ep_dir / "EP12.md.keep").write_text("mine", encoding="utf-8")
        d = self.root / "output/episodes/EP12"
        d.mkdir(parents=True)
        try:
            os.symlink(self.ep_dir / "EP12.md.keep", d / "EP12.md")
        except (OSError, NotImplementedError) as e:          # Windows without the symlink privilege
            self.skipTest(f"no file symlinks here: {e}")
        r = self.init(force=True)
        self.assertIn("refused", r)
        self.assertEqual((self.ep_dir / "EP12.md.keep").read_text(encoding="utf-8"), "mine")

    def test_discovery_never_writes_through_a_link_into_data(self):
        """list_episodes(refresh) runs discovery, which writes output/discovery/*: checked before it (review P0-2)."""
        self.episode()
        (self.root / "output").mkdir()
        dir_link(self.root / "output/discovery", self.ep_dir)
        self.refused_and_untouched()

    def test_output_moved_to_another_disk_still_works(self):
        """output/ as a link to a plain folder elsewhere (a bigger disk) is a legitimate setup (review 2 P1-A)."""
        self.episode()
        big = self.tmp / "BigDisk" / "ClientOut"
        big.mkdir(parents=True)
        dir_link(self.root / "output", big)
        r = self.init()
        self.assertTrue(r["ok"], r)
        self.assertTrue((big / "episodes/EP12/EP12.md").is_file())

    def test_a_link_into_another_clients_folder_is_refused(self):
        self.episode()
        other = make_client(self.tmp / "o", "Other Client")
        (other / "output").mkdir()
        (self.root / "output").mkdir()
        dir_link(self.root / "output/episodes", other / "output")
        before = tree(other)
        r = self.init()
        self.assertIn("refused", r)
        self.assertIn("another client", r["refused"])
        self.assertEqual(tree(other), before)

    def test_the_late_check_catches_a_link_swapped_in_after_the_first(self):
        """Between the first check and the write, the episode folder is replaced by a link into data/."""
        self.episode()
        project = self.root / "output/episodes/EP12"
        real_mkdir = Path.mkdir

        def mkdir(p, *a, **k):
            real_mkdir(p, *a, **k)
            if Path(p) == project and not os.path.lexists(project / ".swapped"):
                os.rmdir(p)
                dir_link(project, self.ep_dir)
        from unittest import mock
        before = tree(self.root / "data")
        with mock.patch.object(Path, "mkdir", autospec=True, side_effect=mkdir):
            r = self.init()
        self.assertIn("refused", r)
        self.assertEqual(tree(self.root / "data"), before)

    def test_the_target_check_runs_right_before_the_write(self):
        """Where file symlinks need a privilege (this PC) the symlink test skips: the same check, with the target
        resolving into data/ the way a symlink makes it."""
        self.episode()
        real = os.path.realpath
        target = str(self.root / "output/episodes/EP12/EP12.md")
        fake = str(self.ep_dir / "EP12.md")

        def realpath(p, *a, **k):
            return fake if os.path.normpath(str(p)) == os.path.normpath(target) else real(p, *a, **k)
        from unittest import mock
        before = tree(self.root / "data")
        with mock.patch.object(CMP.os.path, "realpath", side_effect=realpath):
            r = self.init()
        self.assertIn("refused", r)
        self.assertFalse(Path(target).exists())
        self.assertEqual(tree(self.root / "data"), before)

    def test_containment_folds_case_where_the_file_system_does(self):
        data = self.root / "data"
        self.assertTrue(CMP.inside(self.root / "DATA" / "Episodes" / "x.md", data, fold=True))
        self.assertFalse(CMP.inside(self.root / "DATA" / "Episodes" / "x.md", data, fold=False))
        self.assertFalse(CMP.inside(self.root / "database" / "x.md", data, fold=True))
        self.assertTrue(CMP.inside(data, data, fold=False))


class TestCli(Base):
    def reel(self, *argv, root=None):
        cmd = [sys.executable, "-B", str(CLI), "--root", str(root or self.root), "episode-sheet", *argv]
        e = {k: v for k, v in env().items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        r = subprocess.run(cmd, capture_output=True, env=e)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")

    def test_classified_as_a_writer_and_listed(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("reel_cli_t44", CLI)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        self.assertIn("episode-sheet", m.command_table())
        self.assertIn("episode-sheet", m.registered_commands())
        self.assertIn("episode-sheet", m.CORE_WRITES)
        self.assertNotIn("episode-sheet", m.CORE_READS)
        self.assertIn("episode-sheet", m.NO_ID)

    def test_init_through_the_cli_with_an_arabic_file(self):
        self.episode("الحلقة ١٢.mp4")
        self.people(KARIM)
        from lib.episode import episode_id_for
        eid = episode_id_for(Path("الحلقة ١٢.mp4"))
        code, out, err = self.reel("--init", eid)
        self.assertEqual(code, 0, out + err)
        r = json.loads(out)
        self.assertEqual(r["move_to"], "data/Episodes/الحلقة ١٢.md")
        self.assertEqual(r["people"][0]["name"], KARIM["name"])
        self.assertTrue(Path(r["sheet"]).is_file())

    def test_output_a_link_into_data_writes_not_even_the_lock(self):
        """The writer lock is taken before the command runs (output/.whynot-lock): a link from output/ into data/
        must stop it there, for every writing command (T4.4 review P0-1)."""
        self.episode()
        (self.root / "data/out").mkdir()
        dir_link(self.root / "output", self.root / "data/out")
        before = tree(self.root / "data")
        code, out, err = self.reel("--init", "EP12")
        self.assertEqual(code, 2, out + err)
        self.assertIn("refused", json.loads(out))
        self.assertEqual(tree(self.root / "data"), before)
        # every writer, not just this one (the T4.7 review saw data/out/logs/pipeline.log from any writing command)
        e = {k: v for k, v in env().items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        r = subprocess.run([sys.executable, "-B", str(CLI), "--root", str(self.root), "discover"], capture_output=True,
                           env=e)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(tree(self.root / "data"), before, "nothing under data/, logs included")

    def test_refusal_exits_2_and_writes_nothing(self):
        self.episode()
        (self.ep_dir / "EP12.md").write_text("---\n---\n", encoding="utf-8")
        code, out, _err = self.reel("--init", "EP12")
        self.assertEqual(code, 2, out)
        self.assertIn("refused", json.loads(out))
        self.assertFalse((self.root / "output/episodes/EP12/EP12.md").exists())

    def test_output_logs_a_link_into_data_writes_no_log_line(self):
        """The log lines written before the command (a 2.x marker note, a stale-lock takeover) go to output/logs/
        (review 2 P1-B)."""
        self.episode()
        (self.root / "output").mkdir()
        (self.root / "data/logs-here").mkdir()
        dir_link(self.root / "output/logs", self.root / "data/logs-here")
        write_json(self.root / "output/.whynot-lock", {"session_id": "gone", "pid": 999999, "host": "elsewhere",
                                                        "started_at": "2020-01-01T00:00:00Z",
                                                        "updated_at": "2020-01-01T00:00:00Z"})
        (self.root / ".whynot-client").unlink()                        # a 2.x client: the marker note would be logged
        before = tree(self.root / "data")
        code, out, err = self.reel("--init", "EP12")
        self.assertEqual(code, 2, out + err)
        self.assertEqual(tree(self.root / "data"), before)

    def test_init_is_required(self):
        code, _out, err = self.reel()
        self.assertEqual(code, 2)
        self.assertIn("--init", err)

    def test_not_a_client_folder(self):
        other = self.tmp / "not-a-client"
        other.mkdir()
        code, out, _err = self.reel("--init", "EP12", root=other)
        self.assertEqual(code, 1, out)
        doc = json.loads(out)
        self.assertFalse(doc["ok"])
        self.assertIn("not a client folder", doc["error"])
        self.assertFalse((other / "output").exists())


if __name__ == "__main__":
    unittest.main()
