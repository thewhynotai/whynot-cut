"""Tests for guide-ar/build.py.

Run:  ~/.whynot-cut/venv/Scripts/python.exe -m unittest discover -s guide-ar/tests -v

The helper tests need only the standard library. The PDF tests run only after a
build has written guide-ar/.build/test.pdf (and .build/toc.json); they need pypdf.
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

GUIDE = Path(__file__).resolve().parent.parent
BUILD_DIR = GUIDE / ".build"
TEST_PDF = BUILD_DIR / "test.pdf"
TOC_JSON = BUILD_DIR / "toc.json"

_spec = importlib.util.spec_from_file_location("guide_build", GUIDE / "build.py")
build = importlib.util.module_from_spec(_spec)
sys.modules["guide_build"] = build
_spec.loader.exec_module(build)

SHELL = """<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<link rel="stylesheet" href="styles.css"></head><body>
<nav id="toc"><h1 class="toc-title">المحتويات</h1><!--@toc--></nav>
<!--@chapters-->
</body></html>"""

CH1 = """<section class="chapter" id="ch01"><h1 class="ch-title" id="ch01-title">1 · مقدمة</h1>
<p>نص</p><h2 id="ch01-what">إيه الجديد</h2><h2>عنوان من غير id</h2></section>"""

CH2 = """<section class="chapter" id="ch02"><h1 class="ch-title" id="ch02-title">2 · التثبيت</h1>
<h2 id="ch02-run">تشغيل <bdi dir="ltr"><code>reel setup</code></bdi></h2></section>"""


def _wrap(body):
    return '<html dir="rtl"><body>' + body + "</body></html>"


def _pdf_ready():
    if not TEST_PDF.exists():
        return False
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


class AssembleTests(unittest.TestCase):
    def test_assemble_builds_toc_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "chapters").mkdir()
            (root / "index.html").write_text(SHELL, encoding="utf-8")
            # written out of order on purpose: assemble sorts by file name
            (root / "chapters" / "02-install.html").write_text(CH2, encoding="utf-8")
            (root / "chapters" / "01-intro.html").write_text(CH1, encoding="utf-8")
            html = build.assemble(root)

        self.assertNotIn("<!--@chapters-->", html)
        self.assertNotIn("<!--@toc-->", html)
        self.assertLess(html.index('id="ch01"'), html.index('id="ch02"'))

        toc = html[html.index('<nav id="toc">'):html.index("</nav>")]
        ids = re.findall(r'<a href="#([^"]+)">', toc)
        self.assertEqual(ids, ["ch01-title", "ch01-what", "ch02-title", "ch02-run"])
        self.assertIn('<span class="pg" data-for="ch01-title"></span>', toc)
        self.assertIn("<span>1 · مقدمة</span>", toc)
        # an h2 without an id is not a TOC entry
        self.assertNotIn("عنوان من غير id", toc)
        # inline isolation is kept inside the TOC entry
        self.assertIn('<bdi dir="ltr"><code>reel setup</code></bdi>', toc)
        # the assembled document itself lints clean
        self.assertEqual(build.lint(html), [])

    def test_fill_toc(self):
        html = _wrap(
            '<nav id="toc"><ol>'
            '<li><a href="#a1"><span>1 · مقدمة</span><span class="pg" data-for="a1"></span></a></li>'
            '<li><a href="#a2"><span>تشغيل</span><span class="pg" data-for="a2">99</span></a></li>'
            "</ol></nav>"
            '<h1 class="ch-title" id="a1">1 ·  مقدمة</h1>'
            '<h2 id="a2">تشغيل <bdi dir="ltr"><code>reel doctor</code></bdi></h2>'
        )
        pages = {"1 · مقدمة": 3, "تشغيل reel doctor": 4}
        out = build.fill_toc(html, pages)
        self.assertIn('<span class="pg" data-for="a1">3</span>', out)
        self.assertIn('<span class="pg" data-for="a2">4</span>', out)
        # unknown heading -> number left empty (first pass), never a stale value
        out2 = build.fill_toc(html, {})
        self.assertIn('<span class="pg" data-for="a2"></span>', out2)
        self.assertEqual(build.toc_numbers(out), {"a1": 3, "a2": 4})


class LintTests(unittest.TestCase):
    def test_lint_flags_unisolated_latin(self):
        self.assertEqual(len(build.lint(_wrap("<p>شغّل reel doctor</p>"))), 1)
        self.assertEqual(
            build.lint(_wrap('<p>شغّل <bdi dir="ltr"><code>reel doctor</code></bdi></p>')), [])
        # paths, timecodes, URLs and emails are caught too
        self.assertEqual(len(build.lint(_wrap(r"<p>افتح D:\WhyNot Clients</p>"))), 1)
        self.assertEqual(len(build.lint(_wrap("<p>عند 00:12:04.000 بالظبط</p>"))), 1)
        self.assertEqual(len(build.lint(_wrap("<p>ابعت على info@thewhynot.ai</p>"))), 1)
        self.assertEqual(len(build.lint(_wrap("<p>اكتب /whynot-cut:edit</p>"))), 1)
        # plain Latin product names are fine without isolation
        self.assertEqual(build.lint(_wrap("<p>افتح Premiere Pro و After Effects</p>")), [])

    def test_lint_flags_arabic_digits_in_bdi(self):
        self.assertEqual(len(build.lint(_wrap('<p>الإصدار <bdi dir="ltr">٣.٠</bdi></p>'))), 1)
        self.assertEqual(build.lint(_wrap('<p>الإصدار <bdi dir="ltr">3.0</bdi></p>')), [])
        # Arabic-Indic digits in prose are allowed
        self.assertEqual(build.lint(_wrap("<p>عندك ٣ خطوات</p>")), [])

    def test_lint_flags_broken_anchor(self):
        self.assertEqual(len(build.lint(_wrap('<p><a href="#nowhere">هنا</a></p>'))), 1)
        self.assertEqual(build.lint(_wrap('<h2 id="x">عنوان</h2><p><a href="#x">هنا</a></p>')), [])

    def test_lint_flags_duplicate_id_gate_and_dark_logo(self):
        self.assertEqual(len(build.lint(_wrap('<h2 id="x">أ</h2><h2 id="x">ب</h2>'))), 1)
        self.assertEqual(len(build.lint(_wrap("<p>بعد Gate 1 مباشرة</p>"))), 1)
        self.assertEqual(
            build.lint(_wrap('<section id="ch16"><p>في السجلات: Gate 1 = الموافقة</p></section>')), [])
        self.assertEqual(len(build.lint(_wrap('<img src="img/logo-dark.svg" alt="">'))), 1)


class ChapterTests(unittest.TestCase):
    def test_reel_commands_exist(self):
        chapters = sorted((GUIDE / "chapters").glob("*.html"))
        if not [p for p in chapters if p.name != "01-intro.html"]:
            self.skipTest("only the placeholder chapter exists")
        known = set((GUIDE / "tests" / "reel-commands.txt").read_text(encoding="utf-8").split())
        missing = []
        for path in chapters:
            text = path.read_text(encoding="utf-8")
            for code in re.findall(r"<code\b[^>]*>(.*?)</code>", text, flags=re.S):
                plain = re.sub(r"<[^>]+>", "", code)
                for word in re.findall(r"\breel\s+([a-z][a-z0-9-]*)", plain):
                    if word not in known:
                        missing.append(f"{path.name}: reel {word}")
        self.assertEqual(missing, [], "commands not in reel --help (tests/reel-commands.txt)")


@unittest.skipUnless(_pdf_ready(), "no guide-ar/.build/test.pdf yet (run build.py) or pypdf missing")
class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pypdf
        cls.reader = pypdf.PdfReader(str(TEST_PDF))

    def _font_names(self):
        names = set()
        for page in self.reader.pages:
            res = page.get("/Resources")
            if res is None:
                continue
            res = res.get_object()
            fonts = res.get("/Font")
            if fonts is None:
                continue
            for ref in fonts.get_object().values():
                # Type0 fonts carry /BaseFont; Chrome embeds variable fonts (Alexandria,
                # Inter, Syne) as Type3, whose name is only in /FontDescriptor /FontName.
                stack = [ref.get_object()]
                while stack:
                    font = stack.pop()
                    for key in ("/BaseFont",):
                        if key in font:
                            names.add(str(font[key]).split("+", 1)[-1].lstrip("/"))
                    desc = font.get("/FontDescriptor")
                    if desc is not None and "/FontName" in desc.get_object():
                        names.add(str(desc.get_object()["/FontName"]).split("+", 1)[-1].lstrip("/"))
                    stack.extend(d.get_object() for d in (font.get("/DescendantFonts") or []))
        names.discard("")
        return names

    def test_fonts_embedded(self):
        found = sorted(self._font_names())
        names = " ".join(found)
        for family in ("Alexandria", "IBMPlexSansArabic", "Inter", "IBMPlexMono", "Syne"):
            self.assertIn(family, names, f"{family} not embedded; fonts found: {names}")
        # no system fallback (Segoe UI, Arial, Times, Tahoma …) anywhere
        allowed = ("Alexandria", "IBMPlexSansArabic", "Inter", "IBMPlexMono", "Syne")
        strays = [n for n in found if not n.startswith(allowed)]
        self.assertEqual(strays, [], f"fonts outside the five families: {strays}")

    def test_toc_numbers_match_outline(self):
        self.assertTrue(TOC_JSON.exists(), "build.py writes .build/toc.json next to test.pdf")
        entries = json.loads(TOC_JSON.read_text(encoding="utf-8"))
        self.assertTrue(entries)
        outline = build.outline_pages(TEST_PDF)
        for e in entries:
            self.assertIn(e["title"], outline, f"{e['id']} missing from the PDF outline")
            self.assertEqual(e["page"], outline[e["title"]], f"TOC number wrong for {e['id']}")
        # the printed numbers are really on the TOC page(s): from the «المحتويات»
        # bookmark up to the page before the first chapter
        self.assertIn("المحتويات", outline, "the TOC title is not a bookmark")
        first, last = outline["المحتويات"], min(e["page"] for e in entries) - 1
        text = " ".join(self.reader.pages[p - 1].extract_text() or "" for p in range(first, max(first, last) + 1))
        digits = set(re.findall(r"\d+", text))
        for e in entries:
            self.assertIn(str(e["page"]), digits, f"page {e['page']} not printed in the TOC")

    def test_outline_has_all_chapters(self):
        outline = build.outline_pages(TEST_PDF)
        for path in sorted((GUIDE / "chapters").glob("*.html")):
            m = re.search(r'<h1 class="ch-title"[^>]*>(.*?)</h1>', path.read_text(encoding="utf-8"), re.S)
            self.assertIsNotNone(m, f"{path.name} has no h1.ch-title")
            title = build.plain_text(m.group(1))
            self.assertIn(title, outline, f"{path.name}: «{title}» is not a PDF bookmark")


if __name__ == "__main__":
    unittest.main()
