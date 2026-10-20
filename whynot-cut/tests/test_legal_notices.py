"""BL-03 (Task 22 R-T11): the GPL-compliance request and the trademark notice, each in Arabic and English
(docs/legal/notices/). Templates only. Checks:
  * all four files exist, and each starts with the "not legal advice; have a lawyer review it" banner in its language
  * the only `{{placeholders}}` are the allow-listed ones, and the Arabic and English twins use the same set
  * no e-mail, phone number, URL, personal name, DMCA / cease-and-desist wording, or law article number
  * each template tells the sender what to attach (commit history, release hashes, tag names)
  * the identity scan (Source-R naming rule: no audited project name) finds nothing; it is skipped without the key
Run:  ~/.whynot-cut/venv/Scripts/python.exe -B -m unittest discover -s whynot-cut/tests -p test_legal_notices.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NOTICES = REPO / "docs" / "legal" / "notices"
SCAN = REPO / "tools" / "identity_scan.py"

KINDS = ("gpl-compliance-request", "trademark-notice")
LANGS = ("en", "ar")
FILES = {(k, l): NOTICES / f"{k}.{l}.md" for k in KINDS for l in LANGS}

ALLOWED_PLACEHOLDERS = {
    "contact", "recipient", "date", "sender_org", "our_repo", "their_product", "their_location",
    "our_mark", "deadline_days", "evidence",
}
BANNER = {
    "en": (r"not legal advice", r"lawyer"),
    "ar": (r"ليس[تة]? (?:هذا )?استشارة قانونية|ليست استشارة قانونية", r"محامٍ|محامي"),
}
ATTACH = {
    "en": (r"commit history", r"release hash", r"tag name"),
    "ar": (r"سجل (?:ال)?(?:تعديلات|كوميت)|تاريخ (?:ال)?كوميت", r"بصمات? (?:ال)?(?:إصدار|اصدار)", r"أسماء (?:ال)?وسوم"),
}
DIGITS = "0-9٠-٩۰-۹"


def read(kind, lang):
    return FILES[(kind, lang)].read_text(encoding="utf-8")


class TestLegalNotices(unittest.TestCase):
    def test_four_files_exist_and_are_not_empty(self):
        for key, path in FILES.items():
            with self.subTest(file=path.name):
                self.assertTrue(path.is_file(), f"missing {path}")
                self.assertGreater(len(path.read_text(encoding="utf-8").strip()), 400)

    def test_files_are_in_their_language(self):
        for (kind, lang), path in FILES.items():
            text = path.read_text(encoding="utf-8")
            arabic = len(re.findall(r"[؀-ۿ]", text))
            latin = len(re.findall(r"[A-Za-z]", text))
            with self.subTest(file=path.name):
                if lang == "ar":
                    self.assertGreater(arabic, 300)
                else:
                    self.assertEqual(arabic, 0, "English template holds Arabic letters")
                    self.assertGreater(latin, 300)

    def test_banner_comes_first_in_both_languages(self):
        for (kind, lang), path in FILES.items():
            lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
            head = "\n".join(lines[:4])  # title + banner
            for pat in BANNER[lang]:
                with self.subTest(file=path.name, pattern=pat):
                    self.assertRegex(head, re.compile(pat, re.I))

    def test_only_allow_listed_placeholders_and_twins_match(self):
        for kind in KINDS:
            sets = {}
            for lang in LANGS:
                text = read(kind, lang)
                self.assertEqual(text.count("{{"), text.count("}}"), f"unbalanced braces in {kind}.{lang}")
                found = re.findall(r"\{\{\s*([^{}]*?)\s*\}\}", text)
                sets[lang] = set(found)
                with self.subTest(kind=kind, lang=lang):
                    self.assertTrue(found, "no placeholders at all")
                    self.assertFalse(set(found) - ALLOWED_PLACEHOLDERS, set(found) - ALLOWED_PLACEHOLDERS)
                    self.assertIn("contact", found)
            with self.subTest(kind=kind, twins=True):
                self.assertEqual(sets["en"], sets["ar"])

    def test_no_email_phone_url_or_name(self):
        for path in FILES.values():
            text = re.sub(r"\{\{[^{}]*\}\}", "", path.read_text(encoding="utf-8"))
            with self.subTest(file=path.name):
                self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text), "e-mail address")
                self.assertIsNone(re.search(rf"(?<![{DIGITS}])\+?[{DIGITS}][{DIGITS} ()\-]{{6,}}[{DIGITS}]", text), "phone number")
                self.assertIsNone(re.search(r"https?://|www\.", text, re.I), "URL (use a placeholder)")
                # a personal name is only ever a placeholder: no "Mr/Ms/Dr/Eng./م./د./الأستاذ" title followed by a word
                self.assertIsNone(re.search(r"\b(?:Mr|Mrs|Ms|Dr|Eng|Prof)\.?\s+[A-Z]", text), "titled name")
                self.assertIsNone(re.search(r"(?:^|\s)(?:السيد|السيدة|الدكتور|الدكتورة|المهندس|الأستاذ|الاستاذ)\s", text), "titled name")

    def test_no_dmca_or_cease_and_desist_kit(self):
        for path in FILES.values():
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertIsNone(re.search(r"dmca|cease[\s-]+and[\s-]+desist|takedown|إنذار|انذار|وقف وكف", text, re.I))

    def test_no_law_article_numbers(self):
        for path in FILES.values():
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertIsNone(re.search(rf"\b(?:art(?:icle)?s?|section|sec|clause)\.?\s*§?\s*[{DIGITS}]", text, re.I))
                self.assertIsNone(re.search(rf"§\s*[{DIGITS}]", text))
                self.assertIsNone(re.search(rf"(?:ال)?(?:مادة|المواد|بند|البند|فقرة)\s*(?:رقم\s*)?[{DIGITS}]", text))
                self.assertIsNone(re.search(rf"[{DIGITS}]+\s*/\s*[{DIGITS}]{{4}}|لسنة\s*[{DIGITS}]", text), "law number/year")

    def test_each_template_lists_what_to_attach(self):
        for (kind, lang), path in FILES.items():
            text = path.read_text(encoding="utf-8")
            for pat in ATTACH[lang]:
                with self.subTest(file=path.name, pattern=pat):
                    self.assertRegex(text, re.compile(pat, re.I))

    def test_templates_name_their_subject(self):
        for lang, gpl, tm in (("en", r"General Public License", r"trademark"), ("ar", r"الرخصة العمومية العامة|رخصة جنو|جنو", r"العلامة التجارية")):
            with self.subTest(lang=lang):
                self.assertRegex(read("gpl-compliance-request", lang), gpl)
                self.assertRegex(read("trademark-notice", lang), tm)

    def test_identity_scan_is_clean(self):
        run = subprocess.run([sys.executable, "-B", "-I", str(SCAN), "scan", "--root", str(NOTICES)],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
