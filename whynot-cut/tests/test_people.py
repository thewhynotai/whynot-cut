"""People, gender and honorifics (3.0 T1.7): the profile's people[] (name, role, gender, honorific_ar/en, pronouns) and
the engine check that flags an Arabic honorific (or verb) whose gender disagrees with the profile, in `reel
publish-check` and in `reel plan`. Real incident: «الدكتورة» written for a male client from his name alone.
Run:
    ~/.whynot-cut/venv/bin/python -m unittest discover -s <plugin>/tests -p test_people.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import common  # noqa: E402
from lib.common import write_json  # noqa: E402

KARIM = {"name": "Dr. Karim Sample / د. كريم سامبل", "role": "client", "gender": "male",
         "honorific_ar": "الدكتور", "honorific_en": "Dr.", "pronouns": "he/him"}
MONA = {"name": "منى إكزامبل", "role": "guest", "gender": "female", "honorific_ar": "الدكتورة",
        "honorific_en": "Dr.", "pronouns": "she/her"}
NOUR = {"name": "Nour Test / نور تست", "role": "host", "gender": "unknown", "honorific_ar": "", "honorific_en": "",
        "pronouns": ""}


def run(text, people=(KARIM, MONA, NOUR)):
    from lib.people import check_text, load_people
    ppl, _issues = load_people({"people": list(people)})
    return check_text("T", text, ppl)


class TestHonorificGender(unittest.TestCase):
    def test_male_written_feminine_is_an_error(self):
        errs, _w = run("لقاء مع الدكتورة كريم عن الليزر")
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("كريم", errs[0])
        self.assertIn("male", errs[0])
        self.assertIn("الدكتور", errs[0])

    def test_male_correct_forms_pass(self):
        for t in ("لقاء مع الدكتور كريم", "د. كريم سامبل بيشرح", "د/ كريم", "دكتور كريم", "مع Dr. Karim",
                  "للدكتور كريم سامبل"):
            self.assertEqual(run(t), ([], []), t)

    def test_spelling_variants_still_caught(self):
        for t in ("الدُّكْتُورَة كريم", "الدكتـــورة كريم", "الدكتوره كريم", "للدكتورة كريم", "والدكتورة كريم سامبل",
                  "بالدكتورة كريم", "دكتورة كريم", "الدكتورة Karim", "الدكتورة  كريم", "ودكتورة كريم"):
            errs, _w = run(t)
            self.assertEqual(len(errs), 1, (t, errs))

    def test_every_honorific_pair(self):
        for fem in ("الأستاذة", "الاستاذة", "الإستاذة", "الشيخة", "المهندسة"):
            errs, _w = run(f"{fem} كريم")
            self.assertEqual(len(errs), 1, (fem, errs))
        for masc in ("الأستاذ", "الشيخ", "المهندس"):
            self.assertEqual(run(f"{masc} كريم"), ([], []), masc)
            errs, _w = run(f"{masc} منى")
            self.assertEqual(len(errs), 1, (masc, errs))

    def test_female_correct_and_wrong(self):
        self.assertEqual(run("الدكتورة منى إكزامبل"), ([], []))
        self.assertEqual(run("د. منى"), ([], []))
        errs, _w = run("الدكتور منى")
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("female", errs[0])
        self.assertIn("الدكتورة", errs[0])

    def test_alef_and_ya_forms_in_names(self):
        p = {"name": "إسلام مصطفى", "gender": "male"}
        errs, _w = run("الدكتورة اسلام", [p])
        self.assertEqual(len(errs), 1, errs)
        errs, _w = run("الدكتورة مصطفي", [p])
        self.assertEqual(len(errs), 1, errs)

    def test_unknown_gender_with_gendered_honorific_warns(self):
        errs, warns = run("الدكتورة نور")
        self.assertEqual(errs, [])
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("unknown", warns[0])
        errs, warns = run("الدكتور نور تست")
        self.assertEqual((errs, len(warns)), ([], 1))
        self.assertEqual(run("د. نور"), ([], []))                 # the abbreviation is not gendered

    def test_no_name_or_another_name_is_not_flagged(self):
        self.assertEqual(run("الدكتورة قالت إن الليزر آمن"), ([], []))
        self.assertEqual(run("الدكتورة سارة"), ([], []))           # not a person in the profile
        self.assertEqual(run("الدكتورة"), ([], []))
        self.assertEqual(run("كريم سامبل"), ([], []))              # a name with no honorific
        self.assertEqual(run("الدكتورة كريم", []), ([], []))       # no people[] at all

    def test_compound_names_with_particles(self):
        p = {"name": "عبد الرحمن", "gender": "male"}
        errs, _w = run("الشيخة عبد الرحمن", [p])
        self.assertEqual(len(errs), 1, errs)
        q = {"name": "عبد الله", "gender": "female"}            # «عبد» alone never identifies anyone
        self.assertEqual(run("الشيخ عبد الرحمن", [q]), ([], []))

    def test_verb_agreement_is_a_warning(self):
        errs, warns = run("قالت الدكتور كريم إن الليزر آمن")
        self.assertEqual(errs, [])
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("قالت", warns[0])
        self.assertEqual(run("قال الدكتور كريم إن الليزر آمن"), ([], []))
        self.assertEqual(run("قالت الدكتورة منى"), ([], []))
        errs, warns = run("أكد د. منى إن")
        self.assertEqual((errs, len(warns)), ([], 1))
        errs, warns = run("الدكتور كريم قالت إن الليزر آمن")      # clause start: the verb's subject is the doctor
        self.assertEqual((errs, len(warns)), ([], 1))
        self.assertEqual(run("مريضة الدكتور كريم قالت إن الليزر آمن"), ([], []))   # the patient said it
        self.assertEqual(run("قالت للدكتور كريم"), ([], []))     # she told the doctor
        self.assertEqual(run("شرح الدكتورة منى للحالة"), ([], []))   # «شرح» here is the noun "explanation"

    def test_hashtags(self):
        errs, _w = run("#الدكتورة_كريم #ليزر")
        self.assertEqual(len(errs), 1, errs)
        self.assertEqual(run("#الدكتور_كريم"), ([], []))

    def test_load_people_validates_gender(self):
        from lib.people import load_people
        ppl, issues = load_people({"people": [{"name": "كريم", "gender": "M"}, {"gender": "male"}, "x"]})
        self.assertEqual([p["gender"] for p in ppl], ["unknown"])
        self.assertEqual(len(issues), 3, issues)
        ppl, issues = load_people({"people": [{"name": "كريم", "gender": "Male"}]})
        self.assertEqual((ppl[0]["gender"], issues), ("male", []))
        self.assertEqual(load_people({}), ([], []))


class TestPeopleInPublishCheck(unittest.TestCase):
    def setUp(self):
        import test_podcast as tp
        from lib.episode import EpisodePaths, parse_sheet
        self.tp = tp
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "C"
        (self.root / "assets").mkdir(parents=True)
        (self.root / "data").mkdir()
        common.set_context(self.root)
        self.ep = EpisodePaths(self.root, "EP12")
        tp.synthetic_episode_transcript(self.ep)
        write_json(self.ep.p("00_inputs/episode.json"), {"episode_id": "EP12", "duration_ms": 121000,
                   "sheet_text": tp.PUB_SHEET,
                   "sheet": {k: v for k, v in parse_sheet(tp.PUB_SHEET).items() if k != "_text"}})
        write_json(self.ep.p("01_analysis/topics.json"), {"topics": [
            {"id": "T01", "start": "00:00:00.000", "end": "00:00:40.000", "title": "البداية"},
            {"id": "T02", "start": "00:00:40.000", "end": "00:01:20.000", "title": "مع الدكتورة كريم"},
            {"id": "T03", "start": "00:01:20.000", "end": "00:02:01.000", "title": "البداية من جديد"}]})

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self, people, title):
        from lib.publish import check
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"people": people})
        pub = self.tp.good_pub()
        pub["youtube"]["titles"][0] = title
        reel = self.tp.good_reel()
        reel["shorts"]["title"] = title
        write_json(self.ep.p("publish/publish.json"), pub)
        write_json(self.ep.p("publish/reels/EP12_R01.json"), reel)
        return check(self.ep)

    def test_male_written_feminine_is_an_error(self):
        r = self.check([KARIM], "لقاء مع الدكتورة كريم")
        self.assertFalse(r["ok"])
        bad = [e for e in r["errors"] if "كريم" in e and "male" in e]
        self.assertTrue(any(e.startswith("title 1") for e in bad), r["errors"])
        self.assertTrue(any(e.startswith("EP12_R01 shorts") for e in bad), r["errors"])
        self.assertTrue(any(e.startswith("chapter") for e in bad), r["errors"])      # topic titles are copy too

    def test_female_correct_passes(self):
        r = self.check([dict(KARIM, gender="female")], "لقاء مع الدكتورة كريم")
        self.assertTrue(r["ok"], r["errors"])
        self.assertFalse([w for w in r["warnings"] if "كريم" in w], r["warnings"])

    def test_unknown_gender_warns(self):
        r = self.check([dict(KARIM, gender="unknown")], "لقاء مع الدكتورة كريم")
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any("كريم" in w and "unknown" in w for w in r["warnings"]), r["warnings"])


class TestPeopleInPlan(unittest.TestCase):
    def setUp(self):
        import test_podcast as tp
        self.tp = tp
        self.tmp = Path(tempfile.mkdtemp())
        self.root, self.reel, _src = tp.reel_fixture(self.tmp, "success_story", music=False)

    def tearDown(self):
        common.set_context(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def plan(self, people, text):
        from lib.plan import compile_plan
        write_json(self.root / common.CLIENT_PROFILE_REL / "profile.json", {"people": people})
        write_json(self.reel.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": [
            self.tp.decision("EDIT_001", "00:00:00.000", "00:00:06.000", "كلمه0 كلمه1", graphics=[
                {"id": "GFX_001", "template": "context_card", "start": "00:00:01.000", "end": "00:00:04.000",
                 "text": text}])]})
        return compile_plan(self.reel)

    def test_male_written_feminine_is_an_error(self):
        r = self.plan([KARIM], "الدكتورة كريم سامبل بتحكي عن أول عيادة")
        self.assertFalse(r["ok"])
        self.assertTrue(any(e.startswith("GFX_001") and "كريم" in e and "male" in e for e in r["errors"]), r["errors"])

    def test_female_correct_passes(self):
        r = self.plan([dict(KARIM, gender="female")], "الدكتورة كريم سامبل بتحكي عن أول عيادة")
        self.assertTrue(r["ok"], r["errors"])

    def test_unknown_gender_warns(self):
        r = self.plan([dict(KARIM, gender="unknown")], "الدكتورة كريم سامبل بتحكي عن أول عيادة")
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any(w.startswith("GFX_001") and "unknown" in w for w in r["warnings"]), r["warnings"])


class TestPeopleInProfilesAndAgents(unittest.TestCase):
    KEYS = {"name", "role", "gender", "honorific_ar", "honorific_en", "pronouns"}

    def test_template_has_empty_people_and_a_note(self):
        prof = json.loads((SK / "profiles/_template/profile.json").read_text(encoding="utf-8"))
        self.assertEqual(prof["people"], [])
        notes = (SK / "profiles/_template/notes.md").read_text(encoding="utf-8")
        self.assertIn("people", notes)
        self.assertIn("unknown", notes)
        self.assertEqual(json.loads((common.CONFIG_DIR / "profile.json").read_text(encoding="utf-8"))["people"], [])

    def test_example_clinic_people_follow_the_schema(self):
        from lib.people import load_people
        prof = json.loads((SK / "profiles/example-clinic/profile.json").read_text(encoding="utf-8"))
        self.assertTrue(prof["people"])
        for p in prof["people"]:
            self.assertEqual(set(p), self.KEYS, p)
            self.assertIn(p["gender"], ("male", "female", "unknown"))
        self.assertEqual(load_people(prof)[1], [])
        common.set_context(None, "example-clinic")                     # load_config() layers the shipped profile
        self.addCleanup(common.set_context, None)
        from lib.people import check_text
        ppl, _ = load_people()
        self.assertEqual(len(check_text("T", "الدكتورة سامبل إكزامبل", ppl)[0]), 1)
        self.assertEqual(check_text("T", "د. سامبل إكزامبل", ppl), ([], []))
        self.assertEqual(len(check_text("T", "الأستاذة نور", ppl)[1]), 1)

    def test_agents_and_craft_skills_use_people(self):
        for f in ("agents/client-researcher.md", "skills/client-craft/SKILL.md"):
            body = (SK / f).read_text(encoding="utf-8")
            self.assertIn("people[]", body, f)
            self.assertIn("never infer gender from a name", body.lower(), f)
            self.assertIn("unknown", body, f)
        for f in ("agents/publish-writer.md", "skills/publish-craft/SKILL.md", "agents/story-editor.md",
                  "skills/story-craft/SKILL.md"):
            body = (SK / f).read_text(encoding="utf-8")
            self.assertIn("people[]", body, f)
            self.assertIn("gender", body, f)


if __name__ == "__main__":
    unittest.main()
