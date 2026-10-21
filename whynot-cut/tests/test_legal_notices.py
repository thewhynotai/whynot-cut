"""BL-03 (Task 22 R-T11): the GPL-compliance request and the trademark notice, each in Arabic and English
(docs/legal/notices/). Templates only. Checks:
  * all four files exist, and each starts with the "not legal advice; have a lawyer review it" banner in its language
    ("in both languages" is read as one banner per language file: the English file holds no Arabic letters)
  * each template has a "Before sending" checklist (BL-02's LICENSE and SPDX headers in the cited release, every
    field filled, a lawyer has read it), and the GPL letter does not claim that *each* source file carries headers
  * the only `{{placeholders}}` are the allow-listed ones, and the Arabic and English twins use the same set
  * no e-mail, phone number, URL, personal name, DMCA / cease-and-desist wording, or law article number
  * each template tells the sender what to attach (commit history, release hashes, tag names)
  * the identity scan (Source-R naming rule: no audited project name) finds nothing; without the owner's key the test
    is SKIPPED (the repo-wide check is test_identity_scan.TestRealTree.test_real_tree_passes_with_the_owners_key)
Run:  tools/test.sh -p test_legal_notices.py -v
"""
import json
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
    "ar": (r"ليس[تة]? (?:هذا )?استشارة قانونية", r"محامٍ|محامي"),
}
CHECKLIST = {  # heading, then what the section itself must say
    "en": (r"^## Before sending\b.*$", (r"LICENSE", r"SPDX", r"BL-02", r"double-brace field", r"lawyer")),
    "ar": (r"^## قبل الإرسال.*$", (r"LICENSE", r"SPDX", r"BL-02", r"أقواس مزدوجة", r"محامٍ|محامي")),
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

    def test_before_sending_checklist(self):
        for (kind, lang), path in FILES.items():
            heading, musts = CHECKLIST[lang]
            text = path.read_text(encoding="utf-8")
            m = re.search(heading, text, re.M)
            with self.subTest(file=path.name):
                self.assertIsNotNone(m, "no checklist heading")
            if m is None:
                continue
            section = text[m.end():].split("\n\n")[0]  # the list right under the heading, not the letter body
            for pat in musts:
                with self.subTest(file=path.name, pattern=pat):
                    self.assertRegex(section, pat)

    def test_gpl_letter_does_not_claim_every_file_has_headers(self):
        # not true today, and BL-02 deliberately skips third-party, fixture, generated and pinned files
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertNotRegex(read("gpl-compliance-request", lang), re.compile(r"\beach source file|كل ملف مصدر", re.I))

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
        run = subprocess.run([sys.executable, "-B", "-I", str(SCAN), "scan", "--root", str(NOTICES), "--json"],
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        doc = json.loads(run.stdout)
        if "skipped" in doc:
            self.skipTest("the owner's identity key is not on this machine: nothing was scanned")
        self.assertEqual(doc["hits"], [])
        self.assertGreater(doc["files"], 0)


if __name__ == "__main__":
    unittest.main()
