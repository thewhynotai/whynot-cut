"""Tests for guide-ar/site.py (the Markdown export of the guide for the docs site).

Run:  ~/.whynot-cut/venv/Scripts/python.exe -m unittest discover -s guide-ar/tests -v

Standard library only. The committed pages in guide-ar/site/ar must equal a fresh export.
"""
import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path

GUIDE = Path(__file__).resolve().parent.parent
CHAPTERS = GUIDE / "chapters"
COMMITTED_AR = GUIDE / "site" / "ar"

# loaded under another name: «site» is also a standard-library module
_spec = importlib.util.spec_from_file_location("guide_site", GUIDE / "site.py")
site = importlib.util.module_from_spec(_spec)
sys.modules["guide_site"] = site
_spec.loader.exec_module(site)

TODO_LABEL = "في الإصدار 3.0"


def _sources():
    """(path, html without team comments) for every chapter file."""
    return [(p, re.sub(r"<!--.*?-->", "", p.read_text(encoding="utf-8"), flags=re.S))
            for p in sorted(CHAPTERS.glob("*.html"))]


def _count(pattern):
    return sum(len(re.findall(pattern, html)) for _, html in _sources())


def _anchors(text):
    return set(re.findall(r"\{#([^}\s]+)\}", text))


class ExportSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name) / "ar"
        cls.paths = site.export_site(CHAPTERS, cls.out, "ar")
        cls.pages = {p.name: p.read_text(encoding="utf-8") for p in cls.paths}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_export_site_ar(self):
        self.assertEqual(len(self.paths), 20)
        self.assertEqual([p.name for p in self.paths], sorted(p.name for p in self.paths))
        for n, path in enumerate(self.paths):
            text = self.pages[path.name]
            self.assertTrue(path.name.endswith(".md"))
            front = re.match(r"---\n(.*?)\n---\n", text, re.S)
            self.assertIsNotNone(front, path.name)
            meta = dict(line.split(": ", 1) for line in front.group(1).split("\n"))
            self.assertEqual(int(meta["order"]), n, path.name)
            self.assertEqual(meta["slug"], path.stem)
            self.assertEqual(meta["lang"], "ar")
            self.assertEqual(meta["dir"], "rtl")
            self.assertTrue(meta["title"].strip().strip('"'))
            self.assertNotRegex(meta["title"], r"^\"?\d+ ·")
            self.assertNotIn("<!--", text, path.name)
        # every link with an anchor resolves to an existing page and anchor
        anchors = {name: _anchors(text) for name, text in self.pages.items()}
        checked = 0
        for name, text in self.pages.items():
            for target in re.findall(r"\]\(([^)\s]+)\)", text):
                if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or "#" not in target:
                    continue
                page, anchor = target.split("#", 1)
                page = page or name
                self.assertIn(page, self.pages, f"{name}: {target}")
                self.assertIn(anchor, anchors[page], f"{name}: {target}")
                checked += 1
        self.assertGreater(checked, 100)
        # the 3.0 lines
        # a box inside a list item is indented under it
        todo_lines = sum(len(re.findall(r"^\s*> \*\*" + TODO_LABEL, t, re.M)) for t in self.pages.values())
        self.assertEqual(todo_lines, _count(r'<aside\b[^>]*\bclass="todo"'))
        self.assertGreater(todo_lines, 0)

    def test_export_site_shots(self):
        # a screenshot inside a list item is indented under it
        images = [line.lstrip() for text in self.pages.values() for line in text.split("\n")
                  if line.lstrip().startswith("![")]
        self.assertEqual(len(images), _count(r'<figure\b[^>]*\bclass="shot"'))
        ids = [re.search(r"\]\(shots/([^)\s]+)\.png\)", line).group(1) for line in images]
        self.assertEqual(len(ids), len(set(ids)))
        for text in self.pages.values():
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if line.lstrip().startswith("!["):
                    alt = re.match(r"!\[(.*)\]\(", line.lstrip()).group(1)
                    self.assertTrue(alt)
                    self.assertEqual(lines[i + 2].strip(), f"*{alt}*")

    def test_export_site_no_html_leak(self):
        for name, text in self.pages.items():
            for needle in ("<div", "<span", "<figure", "<table", "<aside", "<bdi", "<strong", "<li", "class="):
                self.assertNotIn(needle, text, f"{name}: {needle}")

    def test_fix_blocks_keep_three_labels(self):
        text = self.pages["17-troubleshooting.md"]
        fixes = _count(r'<div\b[^>]*\bclass="fix"')
        for label in ("اللي حصل", "ليه", "اعمل كده"):
            self.assertGreaterEqual(len(re.findall(r"^\*\*" + label + r":\*\*", text, re.M)), 1)
        total = sum(len(re.findall(r"^\*\*اللي حصل:\*\*", t, re.M)) for t in self.pages.values())
        self.assertEqual(total, fixes)

    def test_steps_are_ordered_lists_and_tables_are_pipe_tables(self):
        text = self.pages["02-install.md"]
        self.assertRegex(text, r"(?m)^1\. ")
        self.assertRegex(text, r"(?m)^2\. ")
        glossary = self.pages["19-glossary.md"]
        self.assertRegex(glossary, r"(?m)^\| English \| .* \|$")
        self.assertRegex(glossary, r"(?m)^\| --- \| --- \| --- \|$")

    def test_site_ar_is_fresh(self):
        committed = sorted(COMMITTED_AR.glob("*.md"))
        self.assertEqual([p.name for p in committed], [p.name for p in self.paths],
                         "guide-ar/site/ar is missing or has extra pages: run python guide-ar/site.py")
        for path in committed:
            self.assertEqual(path.read_text(encoding="utf-8"), self.pages[path.name],
                             f"{path.name} is stale: run python guide-ar/site.py")


class SiteConverterTests(unittest.TestCase):
    """The converter on small inputs (stdlib only, no chapter files)."""

    def convert(self, body, extra=""):
        html = (f'<section class="chapter" id="ch05"><h1 class="ch-title" id="ch05-title">5 · عنوان</h1>'
                f'{body}</section>')
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "chapters"
            src.mkdir()
            (src / "05-demo.html").write_text(html, encoding="utf-8")
            out = Path(tmp) / "out"
            (page,) = site.export_site(src, out, "ar")
            return page.read_text(encoding="utf-8")

    def test_front_matter_and_heading_anchor(self):
        text = self.convert('<p>نص</p><h2 id="ch05-a">قسم</h2>')
        self.assertTrue(text.startswith("---\ntitle: عنوان\nslug: 05-demo\norder: 5\nlang: ar\ndir: rtl\n---\n"))
        self.assertIn("# عنوان {#ch05-title}", text)
        self.assertIn("## قسم {#ch05-a}", text)

    def test_inline_bdi_code_and_links(self):
        text = self.convert('<h2 id="ch05-a">x</h2><p>افتح <bdi dir="ltr">File</bdi> و<bdi dir="ltr"><code>reel</code></bdi> '
                            '<a href="#ch05-a">هنا</a> <a href="https://example.com/a">خارج</a></p>')
        self.assertIn("افتح File و`reel` [هنا](#ch05-a) [خارج](https://example.com/a)", text)

    def test_comments_removed_and_entities(self):
        text = self.convert('<p>a<!-- فريق: سري -->&nbsp;b &lt;path&gt;</p>')
        self.assertNotIn("<!--", text)
        self.assertNotIn("سري", text)
        self.assertIn("\\<path>", text)

    def test_command_box_is_fenced(self):
        text = self.convert('<div class="cmd"><bdi dir="ltr"><code>a "&lt;x&gt;"\nb</code></bdi></div>')
        self.assertIn('```\na "<x>"\nb\n```', text)

    def test_boxes(self):
        text = self.convert('<aside class="tip"><p>حاجة</p></aside><aside class="warn"><p>خطر</p></aside>'
                            '<aside class="todo" data-phase="9"><p>سطر ثلاثة</p></aside>')
        self.assertRegex(text, r"(?m)^> \*\*[^*]+:\*\* حاجة$")
        self.assertRegex(text, r"(?m)^> \*\*[^*]+:\*\* خطر$")
        self.assertRegex(text, r"(?m)^> \*\*في الإصدار 3.0[^*]*:\*\* سطر ثلاثة$")

    def test_unknown_link_target_is_an_error(self):
        with self.assertRaises(ValueError):
            self.convert('<p><a href="#ch99-nowhere">x</a></p>')


if __name__ == "__main__":
    unittest.main()
