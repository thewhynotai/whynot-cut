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
            errs, _w = run(f"{masc} منى إكزامبل")          # «منى» alone folds to «مني» ("from me"): see round 1
            self.assertEqual(len(errs), 1, (masc, errs))

    def test_female_correct_and_wrong(self):
        self.assertEqual(run("الدكتورة منى إكزامبل"), ([], []))
        self.assertEqual(run("د. منى"), ([], []))
        errs, _w = run("الدكتور منى إكزامبل")
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
        errs, warns = run("أكد د. منى إكزامبل إن")
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
        r = self.check([dict(KARIM, gender="female", honorific_ar="الدكتورة")], "لقاء مع الدكتورة كريم")
        self.assertTrue(r["ok"], r["errors"])
        self.assertFalse([w for w in r["warnings"] if "كريم" in w], r["warnings"])

    def test_unknown_gender_warns(self):
        r = self.check([dict(KARIM, gender="unknown", honorific_ar="")], "لقاء مع الدكتورة كريم")
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
        r = self.plan([dict(KARIM, gender="female", honorific_ar="الدكتورة")], "الدكتورة كريم سامبل بتحكي عن أول عيادة")
        self.assertTrue(r["ok"], r["errors"])

    def test_unknown_gender_warns(self):
        r = self.plan([dict(KARIM, gender="unknown", honorific_ar="")], "الدكتورة كريم سامبل بتحكي عن أول عيادة")
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


ALI = {"name": "Dr. Ali Hassan / د. علي حسن", "gender": "male"}


class TestReviewRound1(unittest.TestCase):
    """T1.7 review fixes: function-word names, nameless honorifics in plan, punctuation, chained honorifics,
    honorific_ar vs gender, the `reel next` hint, description link labels."""

    def test_function_word_names_are_only_a_warning(self):
        for t in ("ردت الدكتورة على سؤال المتابعين", "الدكتورة على حق"):    # «على» folds to the name «علي»
            errs, warns = run(t, [ALI])
            self.assertEqual(errs, [], t)
            self.assertEqual(len(warns), 1, (t, warns))
            self.assertIn("common word", warns[0])
        errs, warns = run("الدكتور مني بيقول", [MONA])                    # «مني» = "from me" and the name منى
        self.assertEqual((errs, len(warns)), ([], 1))
        errs, _w = run("الدكتورة علي حسن", [ALI])                       # two name words: no doubt left
        self.assertEqual(len(errs), 1, errs)
        errs, _w = run("الدكتورة على", [dict(ALI, name="علي")])         # a one-word name that is a function word
        self.assertEqual(errs, [])
        self.assertEqual(run("الدكتورة على حق", [dict(ALI, gender="unknown")]), ([], []))
        self.assertEqual(run("الدكتور علي حسن قال", [ALI]), ([], []))

    def test_verb_after_the_name_with_a_new_subject_is_not_flagged(self):
        self.assertEqual(run("الدكتور علي حسن قالت الدكتورة سارة", [ALI]), ([], []))
        self.assertEqual(run("الدكتور علي حسن قالت د. سارة", [ALI]), ([], []))

    def test_punctuation_and_direction_marks_after_the_honorific(self):
        for t in ("دكتورة/ كريم", "الدكتورة/كريم", "الدكتورة: كريم", "الدكتورة - كريم سامبل", "الدكتورة «كريم سامبل»",
                  "الدكتورة “كريم”", "الدكتورة‏ كريم", "‫الدكتورة‬ كريم", "الدكتورة‌ كريم",
                  "⁧الدكتورة كريم⁩", "الدكتو‍رة كريم"):
            errs, _w = run(t, [KARIM])
            self.assertEqual(len(errs), 1, (t, errs))
        for t in ("الدكتور: كريم", "الدكتور/ كريم", "الدكتور - كريم"):
            self.assertEqual(run(t, [KARIM]), ([], []), t)
        self.assertEqual(run("الدكتورة سارة: كريم شاطر", [KARIM]), ([], []))   # the colon after a name still ends it

    def test_chained_honorifics(self):
        errs, _w = run("الأستاذة الدكتور كريم سامبل", [KARIM])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("الأستاذة", errs[0])
        errs, _w = run("الأستاذة الدكتورة كريم", [KARIM])
        self.assertEqual(len(errs), 2, errs)
        self.assertEqual(run("الأستاذ الدكتور كريم", [KARIM]), ([], []))
        self.assertEqual(run("الأستاذ د. كريم", [KARIM]), ([], []))

    def test_honorific_ar_must_agree_with_gender(self):
        from lib.people import load_people
        for p, n in ((dict(KARIM, honorific_ar="الدكتورة"), 1), (dict(MONA, honorific_ar="الدكتور"), 1),
                     (dict(NOUR, honorific_ar="الشيخة"), 1), (KARIM, 0), (MONA, 0), (dict(KARIM, honorific_ar="د."), 0),
                     (dict(KARIM, honorific_ar="الأستاذ الدكتور"), 0)):
            issues = load_people({"people": [p]})[1]
            self.assertEqual(len(issues), n, (p, issues))
        self.assertIn("honorific_ar", load_people({"people": [dict(KARIM, honorific_ar="الدكتورة")]})[1][0])

    def test_nameless_honorific_when_everyone_has_the_other_gender(self):
        from lib.people import check_nameless, load_people

        def nameless(text, people):
            return check_nameless("G", text, load_people({"people": people})[0])
        self.assertEqual(len(nameless("صور الدكتورة المعتمدة", [KARIM, ALI])), 1)
        self.assertIn("male", nameless("صور الدكتورة المعتمدة", [KARIM])[0])
        self.assertEqual(len(nameless("الدكتورة سارة", [KARIM])), 1)            # not a known name
        self.assertEqual(nameless("صور الدكتور المعتمدة", [KARIM]), [])
        self.assertEqual(nameless("الدكتورة كريم", [KARIM]), [])                # named: check_text's error covers it
        self.assertEqual(nameless("الدكتورة على حق", [ALI]), [])                # ambiguous: check_text warns once
        self.assertEqual(nameless("صور الدكتورة", [KARIM, MONA]), [])           # mixed genders: can't tell
        self.assertEqual(nameless("صور الدكتورة", [KARIM, NOUR]), [])           # someone unknown: can't tell
        self.assertEqual(nameless("صور الدكتورة", []), [])
        self.assertEqual(nameless("د. المعتمدة", [KARIM]), [])
        self.assertEqual(len(nameless("نصيحة الشيخ اليوم", [MONA])), 1)         # the mirror case

    def test_profile_notice_when_people_is_empty(self):
        import subprocess
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / "CL"
        for d in ("assets", "data"):
            (root / d).mkdir(parents=True)
        cli = [sys.executable, str(SK / "engine/reel/cli.py"), "--root", str(root)]
        r = subprocess.run(cli + ["client-init", "--id", "cl-test"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

        def notices():
            r = subprocess.run(cli + ["--video-id", "C0001", "next"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)["notices"]
        self.assertTrue(any("people[]" in n and "off" in n for n in notices()), notices())
        pj = root / common.CLIENT_PROFILE_REL / "profile.json"
        prof = json.loads(pj.read_text(encoding="utf-8"))
        prof["people"] = [KARIM]
        pj.write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        self.assertFalse(any("people[]" in n for n in notices()))
        from lib.people import profile_notice
        common.set_context(tmp / "nowhere")                   # no profile at all: `Profile: NONE` says it already
        self.addCleanup(common.set_context, None)
        self.assertIsNone(profile_notice())

    def test_episode_next_carries_the_people_notice(self):
        from lib.episode import EpisodePaths, episode_next
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / "CL"
        (root / "data").mkdir(parents=True)
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"id": "cl-test", "people": []})
        common.set_context(root)
        self.addCleanup(common.set_context, None)
        self.assertTrue(any("people[]" in n for n in episode_next(EpisodePaths(root, "EP01"))["notices"]))
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"id": "cl-test", "people": [KARIM]})
        self.assertEqual(episode_next(EpisodePaths(root, "EP01"))["notices"], [])

    def test_t11_more_invisible_marks_and_a_line_break_after_the_honorific(self):
        for t in ("الدكتورة؜ كريم", "الدكتو­رة كريم", "﻿الدكتورة كريم", "الدكتورة⁠ كريم",
                  "الدكتورة\nكريم", "الدكتورة \n كريم سامبل"):
            errs, _w = run(t, [KARIM])
            self.assertEqual(len(errs), 1, (t, errs))
        self.assertEqual(run("الدكتورة\n\nكريم", [KARIM]), ([], []))     # a blank line ends the clause
        self.assertEqual(run("الدكتور\nكريم", [KARIM]), ([], []))

    def test_t11_chained_nameless_honorifics_warn_once(self):
        from lib.people import check_nameless, load_people
        ppl = load_people({"people": [KARIM]})[0]
        self.assertEqual(len(check_nameless("G", "صور الأستاذة الدكتورة المعتمدة", ppl)), 1)
        self.assertEqual(len(check_nameless("G", "صور الأستاذة الدكتور المعتمدة", ppl)), 1)
        self.assertEqual(len(check_nameless("G", "الأستاذة المعتمدة والدكتورة الجديدة", ppl)), 2)   # two mentions

    def test_t11_motion_next_carries_the_people_notice(self):
        import subprocess
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / "CL"
        for d in ("assets", "data"):
            (root / d).mkdir(parents=True)
        cli = [sys.executable, str(SK / "engine/reel/cli.py"), "--root", str(root)]
        self.assertEqual(subprocess.run(cli + ["client-init", "--id", "cl-test"], capture_output=True).returncode, 0)
        write_json(root / "output/projects/EP01_R01_MO/00_inputs/source.json",
                   {"kind": "motion_reel", "footage": "data/Episodes/EP01.mp4", "in_ms": 0, "out_ms": 30000})

        def motion_next():
            r = subprocess.run(cli + ["--video-id", "EP01_R01_MO", "next"], capture_output=True, text=True,
                               encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            self.assertEqual(out.get("kind"), "motion")
            return out["notices"]
        self.assertTrue(any("people[]" in n for n in motion_next()))
        pj = root / common.CLIENT_PROFILE_REL / "profile.json"
        prof = json.loads(pj.read_text(encoding="utf-8"))
        prof["people"] = [KARIM]
        pj.write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(motion_next(), [])

    def test_lead_skills_carry_the_gender_rule(self):
        for s in ("new-client", "start", "edit", "podcast", "revise", "autopilot", "handoff", "status"):
            body = (SK / "skills" / s / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]
            self.assertIn("people[]", body, s)
            self.assertIn("«د.»", body, s)
            self.assertIn("own messages, tables and file names", body, s)


class TestReviewRound1Engine(unittest.TestCase):
    """Nameless honorific warning in `reel plan`; description link labels in publish-check."""
    def test_plan_warns_on_a_nameless_feminine_honorific_for_an_all_male_profile(self):
        import test_podcast as tp
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.addCleanup(common.set_context, None)
        root, reel, _src = tp.reel_fixture(tmp, "success_story", music=False)
        from lib.plan import compile_plan
        write_json(root / common.CLIENT_PROFILE_REL / "profile.json", {"people": [KARIM]})
        write_json(reel.p("01_analysis/edit-decisions.json"), {"global": {}, "decisions": [
            tp.decision("EDIT_001", "00:00:00.000", "00:00:06.000", "كلمه0 كلمه1", graphics=[
                {"id": "GFX_001", "template": "context_card", "start": "00:00:01.000", "end": "00:00:04.000",
                 "text": "صور الدكتورة المعتمدة"}])]})
        r = compile_plan(reel)
        self.assertTrue(r["ok"], r["errors"])
        self.assertTrue(any(w.startswith("GFX_001") and "male" in w for w in r["warnings"]), r["warnings"])

    def test_description_link_labels_are_checked(self):
        t = TestPeopleInPublishCheck("test_female_correct_passes")
        t.setUp()
        self.addCleanup(t.tearDown)
        from lib.publish import check
        write_json(t.root / common.CLIENT_PROFILE_REL / "profile.json", {"people": [KARIM]})
        pub = t.tp.good_pub()
        pub["youtube"]["description"]["links"][0]["label"] = "انستجرام الدكتورة كريم"
        write_json(t.ep.p("publish/publish.json"), pub)
        write_json(t.ep.p("publish/reels/EP12_R01.json"), t.tp.good_reel())
        r = check(t.ep)
        self.assertTrue(any(e.startswith("description link") and "كريم" in e for e in r["errors"]), r["errors"])
        self.assertFalse([w for w in r["warnings"] if "male" in w and "chapter" not in w], r["warnings"])


if __name__ == "__main__":
    unittest.main()
