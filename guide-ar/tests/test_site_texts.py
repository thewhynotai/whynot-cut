"""Tests for the hand-written docs-site texts (Addendum G5, owner decisions R2 D-01/D-02/D-05/D-07, rule H24).

Run:  ~/.whynot-cut/venv/Scripts/python.exe -m unittest guide-ar/tests/test_site_texts.py -v

Files checked: release-notes/TEMPLATE.{ar,en}.md, whats-new/3.0.0.{ar,en}.md and
site/pages/{support,data}.{ar,en}.md; the no-WhatsApp-link rule (D-05 update) reads every guide-ar text file.
Standard library only.
"""
import ast
import os
import re
import unittest
from pathlib import Path

GUIDE = Path(os.environ.get("WNC_GUIDE_DIR") or Path(__file__).resolve().parent.parent)
REPO = GUIDE.parent

TEMPLATES = {lang: GUIDE / "release-notes" / f"TEMPLATE.{lang}.md" for lang in ("ar", "en")}
WHATS_NEW = {lang: GUIDE / "whats-new" / f"3.0.0.{lang}.md" for lang in ("ar", "en")}
PAGES = {(name, lang): GUIDE / "site" / "pages" / f"{name}.{lang}.md"
         for name in ("support", "data") for lang in ("ar", "en")}
ALL_FILES = list(TEMPLATES.values()) + list(WHATS_NEW.values()) + list(PAGES.values())

WHATS_NEW_MAX_ITEMS = 5
WHATS_NEW_MAX_CHARS = 90  # panel line length (plan Task 8 Step 4)

TEMPLATE_SECTIONS = {
    "ar": ["الجديد", "اتصلّح", "لازم تعرف", "إزاي تحدّث"],
    "en": ["What's new", "Fixed", "Good to know", "How to update"],
}

# Approved data-flow sentence (executor, G2-r1-agency-owner.md); the brief asks for the AR one verbatim.
DATA_FLOW = {
    "ar": "ملفات الفيديو والصوت لا تُرفع أبدًا؛ يقرأ Claude النصوص (التفريغ والخطة) وبعض الصور الثابتة: "
          "لقطات قليلة من التايملاين للتحقق وصور البراند",
    "en": "Video and audio files are never uploaded. Claude reads text (the transcript and the plan) and a few "
          "still images: some timeline frames for checking, and brand photos.",
}
# D-01 (R2-owner-decisions.md): the Claude plan cost line. It is the ONLY place a price may appear.
D01 = {
    "ar": "كل مونتير محتاج اشتراك Claude Pro أو Max باسمه، بيدفعه لـ Anthropic (Pro بيبدأ من 20 دولار في الشهر، "
          "والسعر بيختلف من بلد للتاني). WhyNot Cut مش بيزوّد عليه حاجة.",
    "en": "Each editor needs their own Claude Pro or Max plan, paid to Anthropic (Pro from $20 a month; prices vary "
          "by country). WhyNot Cut adds nothing on top.",
}
# D-02 wording, verbatim.
D02 = {
    "ar": "اللي Claude بيقراه بيتعامل معاه حسب شروط اشتراكك في Claude. لشغل العملاء، اقفل \"Help improve our AI "
          "models\" من إعدادات الخصوصية في Claude. للعملاء الطبيين: استخدم اشتراك Team أو Enterprise، لأن بياناته "
          "ما بتتستخدمش في التدريب.",
    "en": "What Claude reads is handled under your Claude plan's terms. For client work, turn off 'Help improve our "
          "AI models' in Claude's privacy settings. Medical clients: use a Team or Enterprise plan, where data isn't "
          "used for training.",
}
# D-05 support promise, exactly as decided.
D05 = {
    "ar": "بنرد خلال يوم عمل واحد (من الأحد للخميس، بتوقيت القاهرة).",
    "en": "We reply within one working day (Sun–Thu, Cairo time).",
}
SUPPORT_EMAIL = "info@thewhynot.ai"
# The panel's real support control today (adobe/panel-ui/i18n/{en,ar}.json, "actions.diagnostics").
DIAGNOSTICS_LABEL = {"ar": "«نسخ التشخيص»", "en": "“Copy diagnostics”"}

# No prices, licence or legal words (D-07, Addendum G H17). Checked case-insensitively.
FORBIDDEN = ["$", "دولار", "ترخيص", "رخصة", "licen", "eula", "refund", "terms of service"]
# H24: these pages are not live yet, so nothing links (or even points) to them.
NOT_LIVE = re.compile(r"thewhynot\.ai/(support|data)\b", re.IGNORECASE)
# D-05 update (2026-10-16): no WhatsApp number or chat link anywhere in the guide; the guide points at the panel
# button and the support page's own button. The only exception is the support pages' front-matter instruction to Yunus
# («whatsapp: Yunus inserts the wa.me support link at publish»), which is not reader text.
WHATSAPP_LINK = re.compile(r"wa\.(me|link)\b", re.IGNORECASE)
WHATSAPP_FRONT_MATTER = re.compile(r"^whatsapp: .*$", re.M)
TEXT_SUFFIXES = {".html", ".md", ".css", ".txt"}


def read(path):
    return path.read_text(encoding="utf-8")


def split_front_matter(text):
    m = re.match(r"---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not m:
        raise AssertionError("missing front matter")
    meta = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, m.group(2)


def bullet_items(body):
    return [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]


def real_client_tokens():
    """The engine suite's own list of real-client words, read from its source (this file must not spell them out)."""
    tree = ast.parse(read(REPO / "whynot-cut" / "tests" / "test_plugin.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "REAL_CLIENT_TOKENS"
                                                for t in node.targets):
            return [t.lower() for t in ast.literal_eval(node.value)]
    raise AssertionError("REAL_CLIENT_TOKENS not found in whynot-cut/tests/test_plugin.py")


class WhatsNewTests(unittest.TestCase):
    def test_whats_new_line_length(self):
        counts = {}
        for lang, path in WHATS_NEW.items():
            meta, body = split_front_matter(read(path))
            self.assertEqual(meta.get("version"), "3.0.0", path.name)
            self.assertEqual(meta.get("lang"), lang, path.name)
            self.assertTrue(meta.get("status", "").startswith("draft"), f"{path.name}: must stay a draft")
            self.assertEqual(len([l for l in body.splitlines() if l.startswith("# ")]), 1, f"{path.name}: one title")
            items = bullet_items(body)
            self.assertTrue(items, f"{path.name}: no items")
            self.assertLessEqual(len(items), WHATS_NEW_MAX_ITEMS, path.name)
            for item in items:
                self.assertLessEqual(len(item), WHATS_NEW_MAX_CHARS, f"{path.name}: {len(item)} chars: {item}")
            counts[lang] = len(items)
        self.assertEqual(counts["ar"], counts["en"], "AR and EN must have the same items")


class ReleaseTemplateTests(unittest.TestCase):
    def test_release_template_sections(self):
        for lang, path in TEMPLATES.items():
            meta, body = split_front_matter(read(path))
            self.assertEqual(meta.get("lang"), lang, path.name)
            headings = [l[3:].strip() for l in body.splitlines() if l.startswith("## ")]
            self.assertEqual(headings, TEMPLATE_SECTIONS[lang], f"{path.name}: sections and their order")
            # Each section: one instruction comment and at least one bullet.
            parts = re.split(r"^## .*$", body, flags=re.M)[1:]
            for heading, part in zip(headings, parts):
                self.assertEqual(part.count("<!--"), 1, f"{path.name} / {heading}: one instruction comment")
                self.assertTrue(bullet_items(part), f"{path.name} / {heading}: an example bullet")
            # "How to update" points to the guide's chapter 18, never to raw commands.
            self.assertIn("18-update-uninstall.md#ch18-update", parts[-1], path.name)
            self.assertNotIn("```", body, f"{path.name}: no command boxes")


class SitePagesTests(unittest.TestCase):
    def test_site_pages_rules(self):
        data_ar, data_en = read(PAGES[("data", "ar")]), read(PAGES[("data", "en")])
        self.assertIn(DATA_FLOW["ar"], data_ar)
        self.assertIn(DATA_FLOW["en"], data_en)
        # One English version on the whole site: the guide's chapter 1 uses the same approved sentence.
        intro_en = read(GUIDE / "site" / "en" / "01-intro.md")
        self.assertIn(DATA_FLOW["en"], intro_en, "site/en/01-intro.md: approved EN data-flow sentence")
        self.assertNotIn("brand images", intro_en, "site/en/01-intro.md: the old, unapproved wording")
        for lang, text in (("ar", data_ar), ("en", data_en)):
            self.assertIn(D01[lang], text, f"data.{lang}: D-01 wording")
            self.assertIn(D02[lang], text, f"data.{lang}: D-02 wording")
            self.assertIn("Magnific", text, f"data.{lang}: what Magnific receives")
        for lang in ("ar", "en"):
            support = read(PAGES[("support", lang)])
            self.assertIn(D05[lang], support, f"support.{lang}: D-05 promise")
            self.assertIn(SUPPORT_EMAIL, support, f"support.{lang}")
            self.assertNotIn("mailto:", support, f"support.{lang}: the address is plain text")
            self.assertIn("17-troubleshooting.md#", support, f"support.{lang}: link to troubleshooting")
            # I1: the steps name the control the shipping panel has (actions.diagnostics in panel-ui/i18n).
            self.assertIn(DIAGNOSTICS_LABEL[lang], support, f"support.{lang}: the real 'Copy diagnostics' label")
            for mockup_label in ("Details for support", "تفاصيل للدعم"):
                self.assertNotIn(mockup_label, support, f"support.{lang}: a P-22 mockup label, not in the panel")
            for name in ("support", "data"):
                meta, _ = split_front_matter(read(PAGES[(name, lang)]))
                self.assertTrue(meta.get("status", "").startswith("draft"), f"{name}.{lang}: must stay a draft")

        tokens = real_client_tokens()
        for path in ALL_FILES:
            text = read(path)
            # The only allowed price is the D-01 Claude plan line, and only on the data pages.
            if path in (PAGES[("data", "ar")], PAGES[("data", "en")]):
                text = text.replace(D01["ar"], "").replace(D01["en"], "")
            low = text.lower()
            for word in FORBIDDEN:
                self.assertNotIn(word, low, f"{path.name}: {word!r}")
            self.assertIsNone(NOT_LIVE.search(text), f"{path.name}: links to a page that isn't live (H24)")
            for token in tokens:
                self.assertNotIn(token, low, f"{path.name}: a real client name")
            self.assertIsNone(re.search("[٠-٩۰-۹]", text), f"{path.name}: Western digits only")

        # D-05 update: no wa.me / wa.link in any guide text file (chapters, shell, site pages, hand-written texts).
        for path in sorted(GUIDE.rglob("*")):
            if (path.suffix not in TEXT_SUFFIXES or not path.is_file()
                    or {".build", "__pycache__", "fonts", "img"} & set(path.relative_to(GUIDE).parts)):
                continue
            text = read(path)
            front = re.match(r"---\n.*?\n---\n", text, re.S)
            if path.parent == GUIDE / "site" / "pages" and front:  # the front-matter instruction only, never the body
                text = WHATSAPP_FRONT_MATTER.sub("", front.group(0)) + text[front.end():]
            self.assertIsNone(WHATSAPP_LINK.search(text),
                              f"{path.relative_to(GUIDE)}: a WhatsApp number or link (D-05 update: point at the button)")


if __name__ == "__main__":
    unittest.main()
