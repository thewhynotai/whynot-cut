"""Tests for guide-ar/build.py.

Run:  ~/.whynot-cut/venv/Scripts/python.exe -m unittest discover -s guide-ar/tests -v

The helper tests need only the standard library. The PDF tests run only after a
build has written guide-ar/.build/test.pdf (and .build/toc.json); they need pypdf.
"""
import contextlib
import importlib.util
import io
import json
import os
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
<p>مقدمة الفصل</p>
<h2 id="ch02-run">تشغيل <bdi dir="ltr"><code>reel setup</code></bdi></h2>
<p>افتح <bdi dir="ltr">Window&nbsp;›&nbsp;Extensions</bdi> ثم كمّل.</p>
<h2 id="ch02-check">التأكد</h2></section>"""


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

        # the TOC page lists the chapters only (one page); the number is its own span,
        # the « · » stays in the text so the plain text is still «N · العنوان»
        toc = html[html.index('<nav id="toc">'):html.index("</nav>")]
        ids = re.findall(r'<a href="#([^"]+)">', toc)
        self.assertEqual(ids, ["ch01-title", "ch02-title"])
        self.assertIn('<span class="pg" data-for="ch01-title"></span>', toc)
        self.assertIn('<span><span class="num">1</span><span class="ch-sep"> · </span>مقدمة</span>', toc)
        self.assertEqual(build.plain_text(re.search(r"<li[^>]*>(.*?)</li>", toc).group(1)), "1 · مقدمة")

        # each chapter with 2+ sections gets a map after its first paragraph; ch01 has one
        # h2 with an id (an h2 without an id is never listed), so no map
        ch1 = html[html.index('id="ch01"'):html.index('id="ch02"')]
        self.assertNotIn("ch-map", ch1)
        self.assertNotIn("عنوان من غير id", toc)
        ch2 = html[html.index('id="ch02"'):]
        self.assertLess(ch2.index("مقدمة الفصل"), ch2.index('<ol class="ch-map">'))
        self.assertLess(ch2.index('<ol class="ch-map">'), ch2.index('<h2 id="ch02-run"'))
        cmap = ch2[ch2.index('<ol class="ch-map">'):ch2.index("</ol>")]
        self.assertEqual(re.findall(r'<a href="#([^"]+)">', cmap), ["ch02-run", "ch02-check"])
        self.assertIn('<span class="map-pg" data-for="ch02-run"></span>', cmap)
        # inline isolation is kept inside the map entry
        self.assertIn('<bdi dir="ltr"><code>reel setup</code></bdi>', cmap)

        # the h1 number is wrapped for print, its plain text (bookmark title) is unchanged
        self.assertIn('<h1 class="ch-title" id="ch02-title"><span class="ch-num">2'
                      '<span class="ch-sep"> · </span></span>التثبيت</h1>', html)
        self.assertEqual([build.plain_text(i) for lv, _, i in build.toc_headings(html) if lv == "h1"],
                         ["1 · مقدمة", "2 · التثبيت"])
        # a menu path becomes a chip
        self.assertIn('<bdi dir="ltr" class="path">Window&nbsp;›&nbsp;Extensions</bdi>', html)
        # the chapter sources are not touched
        self.assertNotIn("ch-num", CH2)
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

    def test_fill_toc_also_fills_chapter_maps(self):
        html = _wrap(
            '<nav id="toc"><ol><li><a href="#a1"><span>1 · مقدمة</span><span class="pg" data-for="a1"></span></a></li>'
            "</ol></nav>"
            '<h1 class="ch-title" id="a1">1 · مقدمة</h1><p>نص</p>'
            '<ol class="ch-map"><li><a href="#a2"><span>تشغيل</span><span class="map-pg" data-for="a2"></span></a></li>'
            "</ol><h2 id=\"a2\">تشغيل</h2>"
        )
        out = build.fill_toc(html, {"1 · مقدمة": 3, "تشغيل": 5})
        self.assertIn('<span class="map-pg" data-for="a2">5</span>', out)
        # the TOC page numbers and the chapter-map numbers are tracked apart
        self.assertEqual(build.toc_numbers(out), {"a1": 3})
        self.assertEqual(build.map_numbers(out), {"a2": 5})
        self.assertEqual(build.expected_numbers(out, {"تشغيل": 6}, build.map_numbers(out)), {"a2": 6})

    def test_shot_followed_by_todo_is_kept_together(self):
        shot = '<figure class="shot"><div class="shot-frame">لقطة</div><figcaption>تعليق</figcaption></figure>'
        todo = '<aside class="todo" data-phase="6"><p>جملة.</p><!-- فريق: x --></aside>'
        src = f"<p>نص</p>{shot}\n\n{todo}<p>بعد</p>{shot}<p>بلا مربع</p>"
        out = build.keep_shot_with_todo(src)
        self.assertEqual(out.count('<div class="keep">'), 1)
        self.assertIn(f'<div class="keep">{shot}\n\n{todo}</div>', out)
        self.assertEqual(build.keep_shot_with_todo(out), out, "idempotent")
        self.assertEqual(build.lint(_wrap(out)), [])

    def test_chapter_number_markup_is_idempotent_and_keeps_text(self):
        h1 = '<h1 class="ch-title" id="ch12-title">12 · حذف السكتات: <bdi dir="ltr">WhyNot Hush</bdi></h1>'
        once = build.mark_chapter_numbers(h1)
        self.assertIn('<span class="ch-num">12<span class="ch-sep"> · </span></span>حذف', once)
        self.assertEqual(build.mark_chapter_numbers(once), once)
        self.assertEqual(build.plain_text(once), "12 · حذف السكتات: WhyNot Hush")
        # other headings are untouched
        self.assertEqual(build.mark_chapter_numbers("<h2>3 · خطوات</h2>"), "<h2>3 · خطوات</h2>")


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

    def test_lint_technical_token_classes(self):
        """Every technical token class is flagged bare and accepted inside <bdi dir="ltr">."""
        cases = {
            "file name": ["edit-decisions.json", "reels-plan.md", "C0239.prproj", "clean.wav", "out.srt",
                          "motion.aep", "C0239.mov", "notes.txt", "cover.jpg", "frame.png", ".prproj"],
            "version": ["v2.2.1", "3.0.0", "26.5", "3.0"],
            "CLI flag": ["--fix", "--by editor", "-v"],
            "hyphen/underscore/id": ["whynot-cut.local.md", "C0239", "EP12_R03", "approval_required",
                                     "example-clinic", "large-v3"],
            "standalone command": ["reel", "/whynot-cut", "/whynot-cut:edit"],
            "path/time/url/email": [r"D:\WhyNot Clients", "~/WhyNot", "00:12:04.000", "https://thewhynot.ai",
                                    "thewhynot.ai", "info@thewhynot.ai"],
        }
        for cls, tokens in cases.items():
            for token in tokens:
                with self.subTest(cls=cls, token=token):
                    bare = build.lint(_wrap(f"<p>اكتب {token} وبعدين كمّل.</p>"))
                    self.assertEqual(len(bare), 1, f"{token!r} ({cls}) not flagged: {bare}")
                    ok = build.lint(_wrap(f'<p>اكتب <bdi dir="ltr"><code>{token}</code></bdi> وبعدين كمّل.</p>'))
                    self.assertEqual(ok, [], f"{token!r} ({cls}) flagged inside bdi")
                    # any LTR ancestor isolates too (e.g. the .cmd block or a dir="ltr" cell)
                    self.assertEqual(build.lint(_wrap(f'<div class="cmd" dir="ltr">{token}</div>')), [])

    def test_lint_allows_plain_words(self):
        words = ("Premiere Pro, After Effects, Claude, WhyNot Cut, Magnific, YouTube, Instagram, TikTok, "
                 "Whisper, NVIDIA, Windows 11, macOS, Photoshop, Lucide, MP4, XML, PDF, H.264, 4K, B-roll.")
        self.assertEqual(build.lint(_wrap(f"<p>بيشتغل مع {words}</p>")), [])
        self.assertEqual(build.lint(_wrap("<p>عندك 3 خطوات بس، وكل خطوة 10 دقايق.</p>")), [])

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
            build.lint(_wrap('<section id="ch19"><p>في السجلات: Gate 1 = الموافقة</p></section>')), [])
        # logo-dark.svg does not exist either: 2 problems (dark logo + missing file)
        dark = build.lint(_wrap('<img src="img/logo-dark.svg" alt="">'))
        self.assertTrue(any("logo-dark" in p for p in dark), dark)

    def test_lint_todo_needs_data_phase(self):
        self.assertEqual(len(build.lint(_wrap('<aside class="todo"><p>نص</p></aside>'))), 1)
        self.assertEqual(len(build.lint(_wrap('<aside class="todo" data-phase=""><p>نص</p></aside>'))), 1)
        self.assertEqual(build.lint(_wrap('<aside class="todo" data-phase="7"><p>نص</p></aside>')), [])


SHOT_IMG = ('<figure class="shot"><div class="shot-frame"><img src="{src}" alt="لقطة"></div>'
            "<figcaption>تعليق</figcaption></figure>")


class ImageTests(unittest.TestCase):
    def test_missing_image_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            problems = build.lint(_wrap(SHOT_IMG.format(src="img/ch99-missing.png")), root=Path(tmp))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("file not found", problems[0])

    def test_existing_image_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "img").mkdir()
            (Path(tmp) / "img" / "ch99-ok.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            html = _wrap(SHOT_IMG.format(src="img/ch99-ok.png"))
            self.assertEqual(build.lint(html, root=Path(tmp)), [])
            # a filled slot also passes the release checks
            self.assertEqual(build.lint(html, release=True, root=Path(tmp)), [])

    def test_image_src_must_be_double_quoted_local_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "img").mkdir()
            (Path(tmp) / "img" / "a.png").write_bytes(b"x")
            root = Path(tmp)
            self.assertEqual(len(build.lint(_wrap("<img src='img/a.png' alt=''>"), root=root)), 1)
            self.assertEqual(len(build.lint(_wrap("<img src=img/a.png alt=''>"), root=root)), 1)
            self.assertEqual(len(build.lint(_wrap('<img alt="">'), root=root)), 1)
            self.assertEqual(len(build.lint(_wrap('<img src="https://example.com/a.png" alt="">'), root=root)), 1)

    def test_shell_logo_resolves(self):
        """The real index.html images exist relative to guide-ar/ (default root)."""
        shell = (GUIDE / "index.html").read_text(encoding="utf-8")
        self.assertEqual([p for p in build.lint(shell) if "img" in p], [])

    def test_relocate_prefixes_image_src(self):
        html = ('<link rel="stylesheet" href="styles.css"><img src="img/ch06-plan.png" alt="">'
                "<img src='img/x.png'><a href=\"#ch06-title\">6</a><a href=\"https://thewhynot.ai\">x</a>")
        out = build.relocate(html)
        self.assertIn('href="../styles.css"', out)
        self.assertIn('src="../img/ch06-plan.png"', out)
        self.assertIn("src='../img/x.png'", out)
        self.assertIn('href="#ch06-title"', out)
        self.assertIn('href="https://thewhynot.ai"', out)


DRAFT_DOC = _wrap(
    '<section id="ch02"><h2 id="a">التحديث</h2>'
    '<aside class="todo" data-phase="7"><p>المخطَّط: قيد البناء.</p></aside>'
    '<p>حتى ذلك الحين يعمل كل شيء من المحادثة.</p>'
    '<figure class="shot"><div class="shot-frame"><span>لقطة شاشة: فولدر العميل</span></div>'
    "<figcaption>تعليق</figcaption></figure></section>")


class ReleaseTests(unittest.TestCase):
    def test_draft_fixture_fails_only_under_release(self):
        self.assertEqual(build.lint(DRAFT_DOC), [], "the default (draft) build accepts placeholders")
        problems = build.lint(DRAFT_DOC, release=True)
        text = "\n".join(problems)
        self.assertIn("placeholder left", text)                # the .todo / data-phase
        self.assertIn("screenshot slot without an <img>", text)
        self.assertIn("حتى ذلك الحين", text)                   # draft phrase outside the .todo
        self.assertNotIn("قيد البناء", text, "phrases inside a .todo are covered by the .todo problem")
        self.assertEqual(len(problems), 3, problems)

    def test_draft_phrases_ignore_diacritics_and_need_a_digit_for_phase(self):
        self.assertEqual(len(build.lint(_wrap("<p>الأقسام المخططة</p>"), release=True)), 1)
        self.assertEqual(build.lint(_wrap("<p>فيديو للمونتاج المخطَّط، والمونتاج المخطط</p>"), release=True), [],
                         "«المونتاج المخطَّط» = the planned edit, not a draft phrase")
        self.assertEqual(len(build.lint(_wrap("<p>يكتمل في مرحلة 7</p>"), release=True)), 1)
        self.assertEqual(build.lint(_wrap("<p>كل مرحلة لها ملف</p>"), release=True), [])

    def test_release_flag_and_env(self):
        old = os.environ.pop("WNC_RELEASE", None)
        try:
            self.assertFalse(build.is_release())
            self.assertTrue(build.is_release(True))
            os.environ["WNC_RELEASE"] = "1"
            self.assertTrue(build.is_release())
            os.environ["WNC_RELEASE"] = "0"
            self.assertFalse(build.is_release())
        finally:
            os.environ.pop("WNC_RELEASE", None)
            if old is not None:
                os.environ["WNC_RELEASE"] = old

    def test_main_release_exits_1_on_draft_lint(self):
        """--release stops at the lint (no browser needed) when a placeholder is left."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "chapters").mkdir()
            (root / "index.html").write_text(SHELL, encoding="utf-8")
            (root / "chapters" / "01-intro.html").write_text(
                CH1.replace("<p>نص</p>", '<aside class="todo" data-phase="7"><p>نص</p></aside>'),
                encoding="utf-8")
            old_root = build.ROOT
            build.ROOT = root
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    self.assertEqual(build.main(["--release", "--out", str(root / "x.pdf")]), 1)
            finally:
                build.ROOT = old_root
            self.assertIn("LINT (release)", out.getvalue())
            self.assertFalse((root / "x.pdf").exists())


class EnvTests(unittest.TestCase):
    def test_print_timeout_falls_back_on_bad_values(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(build._print_timeout("abc"), 300)
            self.assertEqual(build._print_timeout("-5"), 300)
        self.assertIn("WNC_PRINT_TIMEOUT", err.getvalue())
        self.assertEqual(build._print_timeout(None), 300)
        self.assertEqual(build._print_timeout(" 45 "), 45)

    def test_module_imports_with_non_numeric_timeout(self):
        old = os.environ.get("WNC_PRINT_TIMEOUT")
        os.environ["WNC_PRINT_TIMEOUT"] = "five minutes"
        try:
            spec = importlib.util.spec_from_file_location("guide_build_timeout", GUIDE / "build.py")
            mod = importlib.util.module_from_spec(spec)
            with contextlib.redirect_stderr(io.StringIO()):
                spec.loader.exec_module(mod)  # must not raise
            self.assertEqual(mod.PRINT_TIMEOUT, 300)
        finally:
            if old is None:
                os.environ.pop("WNC_PRINT_TIMEOUT", None)
            else:
                os.environ["WNC_PRINT_TIMEOUT"] = old

    def test_browser_candidates_include_per_user_mac_apps(self):
        found = [str(p) for p in build.browser_candidates()]
        home_apps = Path.home() / "Applications"
        self.assertIn(str(home_apps / "Google Chrome.app/Contents/MacOS/Google Chrome"), found)
        self.assertIn(str(home_apps / "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"), found)
        self.assertIn(str(Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")), found)


class HeadingTests(unittest.TestCase):
    def test_headings_ignore_comments_style_script_and_accept_single_quotes(self):
        html = _wrap(
            "<!-- <h2 id='old'>قديم</h2> -->"
            "<style>h2::before{content:'<h2 id=\"css\">x</h2>'}</style>"
            "<script>var s = '<h2 id=\"js\">y</h2>';</script>"
            "<h1 class='ch-title' id='c1'>1 · مقدمة</h1>"
            "<h2 id=c1-a>أول <bdi dir='ltr'><code>reel doctor</code></bdi></h2>"
            "<h2>من غير id</h2>"
        )
        got = build.toc_headings(html)
        self.assertEqual([(lv, hid) for lv, hid, _ in got], [("h1", "c1"), ("h2", "c1-a")])
        self.assertEqual(build.plain_text(got[1][2]), "أول reel doctor")
        toc = build.build_toc(html)
        self.assertNotIn("old", toc)
        # section labels (chapter maps) keep their inline code
        self.assertIn("<code>reel doctor</code>", build._toc_label(got[1][2]))
        self.assertEqual(len(build.all_headings(html)), 3)


class OutlineMatchTests(unittest.TestCase):
    HEADS = [(1, "1 · مقدمة"), (2, "أهم الخطوات"), (2, "إزاي تبدأ")]
    HEIGHTS = [842.0, 842.0, 842.0, 842.0]

    def _marks(self, *rows):
        return [{"title": t, "page": p, "top": top, "left": 0.0, "zoom": 0.0} for t, p, top in rows]

    def test_match_outline_tolerates_duplicated_title(self):
        marks = self._marks((" · مقدمة1", 0, 770.0),          # runs in layout order
                            ("أهم الخطواتأهم الخطوات", 1, 400.0),  # Edge wrote it twice
                            ("إزاي تبدأ", 2, 700.0))
        got = build.match_outline(marks, self.HEADS, self.HEIGHTS)
        self.assertEqual([(e["title"], e["page"]) for e in got],
                         [("1 · مقدمة", 0), ("أهم الخطوات", 1), ("إزاي تبدأ", 2)])
        self.assertTrue(got[1]["notes"])
        self.assertEqual(got[2]["notes"], [])

    def test_match_outline_moves_page_break_sliver_to_next_page(self):
        # the duplicated title's bookmark points at the bottom edge of the previous page
        marks = self._marks(("1 · مقدمة", 0, 770.0), ("أهم الخطواتأهم الخطوات ", 1, 62.7), ("إزاي تبدأ", 2, 500.0))
        got = build.match_outline(marks, self.HEADS, self.HEIGHTS)
        self.assertEqual((got[1]["page"], got[1]["top"]), (2, 842.0))

    def test_match_outline_fails_on_count_or_order(self):
        with self.assertRaises(ValueError):
            build.match_outline(self._marks(("أ", 0, 700.0)), self.HEADS, self.HEIGHTS)
        with self.assertRaises(ValueError):
            build.match_outline(self._marks(("1 · مقدمة", 2, 770.0), ("أهم الخطوات", 1, 400.0),
                                            ("إزاي تبدأ", 3, 700.0)), self.HEADS, self.HEIGHTS)

    def test_fix_outline_rewrites_a_garbled_pdf_outline(self):
        try:
            import pypdf
            from pypdf.generic import Fit
        except ImportError:
            self.skipTest("pypdf missing")
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "o.pdf"
            w = pypdf.PdfWriter()
            for _ in range(3):
                w.add_blank_page(width=595, height=842)
            top = w.add_outline_item(" · مقدمة1", 0, fit=Fit.xyz(0, 770, 0))
            w.add_outline_item("أهم الخطواتأهم الخطوات ", 0, parent=top, fit=Fit.xyz(0, 62.7, 0))
            w.add_outline_item("إزاي تبدأ", 2, parent=top, fit=Fit.xyz(0, 500, 0))
            with open(pdf, "wb") as fh:
                w.write(fh)
            html = _wrap("<h1 class='ch-title' id='a'>1 · مقدمة</h1><h2 id='b'>أهم الخطوات</h2><h2 id='c'>إزاي تبدأ</h2>")
            notes = io.StringIO()
            meta = build.pdf_metadata("ab" * 32, release=False)
            with contextlib.redirect_stdout(notes):
                self.assertEqual(build.fix_outline(pdf, html, meta), 3)
            self.assertIn("next page", notes.getvalue())
            self.assertEqual(build.outline_pages(pdf), {"1 · مقدمة": 1, "أهم الخطوات": 2, "إزاي تبدأ": 3})
            r = pypdf.PdfReader(str(pdf))
            self.assertEqual(r.trailer["/Root"]["/PageMode"], "/UseOutlines")
            self.assertEqual(r.metadata["/Author"], "The Why Not AI")
            self.assertEqual(r.metadata["/Title"], "WhyNot Cut — دليل الاستخدام")
            self.assertIn("مسودة", r.metadata["/Subject"])
            self.assertEqual(r.metadata[build.HASH_KEY], "ab" * 32)
        self.assertNotIn("مسودة", build.pdf_metadata(None, release=True)["/Subject"])

    def test_source_hash_tracks_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "chapters").mkdir()
            (root / "img").mkdir()
            (root / "index.html").write_text(SHELL, encoding="utf-8")
            (root / "styles.css").write_text("body{}", encoding="utf-8")
            (root / "chapters" / "01-intro.html").write_text(
                CH1.replace("<p>نص</p>", '<p><img src="img/a.png" alt=""></p>'), encoding="utf-8")
            (root / "img" / "a.png").write_bytes(b"one")
            first = build.source_hash(root)
            self.assertEqual(build.source_hash(root), first, "deterministic")
            (root / "img" / "a.png").write_bytes(b"two")
            second = build.source_hash(root)
            self.assertNotEqual(second, first, "a changed screenshot changes the hash")
            (root / "styles.css").write_text("body{color:red}", encoding="utf-8")
            self.assertNotEqual(build.source_hash(root), second, "a changed stylesheet changes the hash")


class CmdAndShotTests(unittest.TestCase):
    def test_nowrap_cmd_tokens(self):
        src = ('<div class="cmd"><bdi dir="ltr"><code>reel client-init --root "D:/WhyNot Clients/Example Clinic" '
               '--id example-clinic &amp;&amp; x</code></bdi></div><p>reel doctor --fix</p>')
        out = build.nowrap_cmd_tokens(src)
        self.assertIn('<span class="nw">--id</span> <span class="nw">example-clinic</span>', out)
        self.assertIn('<span class="nw">&amp;&amp;</span>', out)
        self.assertIn('<bdi dir="ltr"><code><span class="nw">reel</span>', out)
        self.assertTrue(out.endswith("<p>reel doctor --fix</p>"), "text outside .cmd untouched")
        self.assertEqual(build.nowrap_cmd_tokens(out), out, "idempotent")
        self.assertEqual(re.sub(r"</?span[^>]*>", "", out), src, "visible text unchanged")
        # multi-line blocks keep their line breaks
        self.assertIn("\n", build.nowrap_cmd_tokens('<div class="cmd"><code>a: 1\nb: 2</code></div>'))

    def test_lint_flags_cmd_token_too_long_to_wrap(self):
        long = "output/" + "x" * 80 + ".prproj"
        html = _wrap(f'<div class="cmd"><bdi dir="ltr"><code>{long}</code></bdi></div>')
        self.assertEqual(len(build.lint(html)), 1)
        ok = _wrap('<div class="cmd"><bdi dir="ltr"><code>output/projects/C0001/07_premiere/project/'
                   'C0001_EC_EDIT.prproj</code></bdi></div>')
        self.assertEqual(build.lint(ok), [])

    def _rule(self, selector):
        css = (GUIDE / "styles.css").read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
        self.assertIsNotNone(m, f"no CSS rule for {selector}")
        return m.group(1)

    def test_css_shot_frame_is_not_flex_and_lead_in_kept_with_next(self):
        frame = self._rule(".shot-frame")
        self.assertNotRegex(frame, r"display:\s*(inline-)?(flex|grid)",
                            "flex/grid would split the caption's <bdi> runs into separate items")
        self.assertRegex(frame, r"display:\s*table-cell")
        css = (GUIDE / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"h2, h3, h4, \.lead-in \{ break-after: avoid;")
        self.assertRegex(self._rule(".cmd code"), r"overflow-wrap:\s*normal")
        self.assertRegex(self._rule(".cmd .nw"), r"white-space:\s*nowrap")

    def test_css_filled_shot_and_tip_code(self):
        # a filled slot shrinks to its image on a light violet stage (round 3 design pass)
        filled = self._rule(".shot-frame:has(img)")
        self.assertRegex(filled, r"height:\s*auto")
        self.assertRegex(filled, r"padding:\s*6mm")
        self.assertRegex(filled, r"background:\s*var\(--stage\)")
        self.assertRegex(self._rule(".shot-frame:has(img)::before"), r"content:\s*none")
        img = self._rule(".shot-frame img")
        self.assertRegex(img, r"max-width:\s*100%")
        self.assertRegex(img, r"max-height:\s*140mm")
        self.assertRegex(self._rule(".tip code"), r"background:\s*#FFFFFF")

    def test_css_footer_and_running_header(self):
        """Owner rule: the body footer reads «Powered by thewhynot.ai» (plus the page number); the covers have no
        header or footer."""
        css = re.sub(r"/\*.*?\*/", "", (GUIDE / "styles.css").read_text(encoding="utf-8"), flags=re.S)
        page = re.search(r"@page\s*\{(.*?)\n\}", css, flags=re.S).group(1)
        self.assertRegex(page, r'@bottom-right\s*\{[^}]*content:\s*"Powered by thewhynot\.ai"')
        self.assertRegex(page, r"@bottom-left\s*\{[^}]*content:\s*counter\(page\)")
        self.assertRegex(page, r'@top-right\s*\{[^}]*content:\s*"\\2067WhyNot Cut — دليل الاستخدام\\2069"')
        cover = re.search(r"@page cover\s*\{(.*?)\n\}", css, flags=re.S).group(1)
        for box in ("@top-right", "@bottom-right", "@bottom-left"):
            self.assertRegex(cover, re.escape(box) + r"\s*\{[^}]*content:\s*none")

    def test_css_todo_is_a_quiet_line_with_a_pill(self):
        """Round 3 design pass: the 3.0 box is no longer a box — a hairline, muted small text and an inline pill."""
        todo = self._rule(".todo")
        self.assertRegex(todo, r"border:\s*0")
        self.assertRegex(todo, r"border-top:\s*0\.75pt solid")
        self.assertRegex(todo, r"background:\s*transparent")
        pill = self._rule(".todo::before")
        self.assertRegex(pill, r"display:\s*inline-block")
        self.assertRegex(pill, r"border-radius:\s*999pt")
        self.assertRegex(self._rule(".todo > p:first-of-type"), r"display:\s*inline")

    def test_css_claude_run_command_caption(self):
        """Ruling R2-4: a .cmd box Claude runs (data-who="claude") shows «يشغّله Claude — لا تكتبه أنت» on its own
        RTL line, drawn by CSS outside the <code> (the source text stays just the command)."""
        rule = self._rule('.cmd[data-who="claude"]::before')
        self.assertIn('content: "يشغّله Claude — لا تكتبه أنت"', rule)
        self.assertRegex(rule, r"display:\s*block")
        self.assertRegex(rule, r"direction:\s*rtl")
        boxes = []
        for path in sorted((GUIDE / "chapters").glob("*.html")):
            for m in re.finditer(r"<div\b([^>]*)\bclass=\"cmd\"([^>]*)>(.*?)</div>",
                                 path.read_text(encoding="utf-8"), flags=re.S):
                code = re.sub(r"<[^>]+>", "", m.group(3)).strip()
                if code.startswith("reel ") and 'data-who="claude"' not in m.group(1) + m.group(2):
                    boxes.append(f"{path.name}: {code[:40]}")
        self.assertEqual(boxes, [], 'every `reel …` .cmd box needs data-who="claude"')

    def test_css_todo_label_is_reader_facing(self):
        """Ruling R2-9: the .todo label tells the reader «في الإصدار 3.0 — لم يُتحقَّق منه بعد», with no phase number
        (data-phase stays an attribute for the lint and the release gate)."""
        rule = self._rule(".todo::before")
        self.assertIn('content: "في الإصدار 3.0 — لم يُتحقَّق منه بعد"', rule)
        self.assertNotIn("attr(data-phase)", rule)
        self.assertNotIn("المرحلة", rule)


class PrintTests(unittest.TestCase):
    def test_print_timeout_stops_browser_and_cleans_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            if sys.platform == "win32":
                fake = tmp / "hang.cmd"
                fake.write_text("@ping -n 30 127.0.0.1 >nul\r\n", encoding="ascii")
            else:
                fake = tmp / "hang.sh"
                fake.write_text("#!/bin/sh\nsleep 30\n", encoding="ascii")
                fake.chmod(0o755)
            profiles = tmp / "profiles"
            profiles.mkdir()
            (tmp / "x.html").write_text("<p>x</p>", encoding="utf-8")
            old_timeout, old_env = build.PRINT_TIMEOUT, os.environ.get("WNC_BROWSER_TMP")
            build.PRINT_TIMEOUT, os.environ["WNC_BROWSER_TMP"] = 2, str(profiles)
            try:
                with self.assertRaises(SystemExit) as cm:
                    build.print_pdf(tmp / "x.html", tmp / "x.pdf", fake)
            finally:
                build.PRINT_TIMEOUT = old_timeout
                if old_env is None:
                    os.environ.pop("WNC_BROWSER_TMP", None)
                else:
                    os.environ["WNC_BROWSER_TMP"] = old_env
            self.assertIn("did not finish printing", str(cm.exception))
            self.assertEqual(list(profiles.iterdir()), [], "temporary browser profile left behind")


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


    def test_chapter_numbers_match_files(self):
        """chapters/NN-*.html: section id chNN, h1 id chNN-title, h1 text «N · …» (Western digits, no leading zero)."""
        paths = sorted((GUIDE / "chapters").glob("*.html"))
        self.assertTrue(paths, "no chapters")
        problems = []
        seen = []
        for path in paths:
            m = re.match(r"(\d\d)-", path.name)
            if not m:
                problems.append(f"{path.name}: file name must start with NN-")
                continue
            nn = m.group(1)
            seen.append(int(nn))
            text = path.read_text(encoding="utf-8")
            if not re.search(rf'<section\b[^>]*\bid="ch{nn}"', text):
                problems.append(f'{path.name}: no <section id="ch{nn}">')
            h1 = re.search(rf'<h1\b[^>]*\bid="ch{nn}-title"[^>]*>(.*?)</h1>', text, flags=re.S)
            if not h1:
                problems.append(f'{path.name}: no <h1 id="ch{nn}-title">')
            elif not re.match(rf"{int(nn)} · \S", build.plain_text(h1.group(1))):
                problems.append(f"{path.name}: h1 «{build.plain_text(h1.group(1))}» must start with «{int(nn)} · »")
            for other in re.findall(r'\bid="ch(\d\d)(?:-[^"]*)?"', text):
                if other != nn:
                    problems.append(f"{path.name}: id for chapter {other} inside chapter {nn}")
        self.assertEqual(seen, list(range(1, len(seen) + 1)), "chapter file numbers must be consecutive from 01")
        self.assertEqual(problems, [])

    def test_chapter_link_text_matches_target(self):
        """A link that names a chapter number points at that chapter: <a href="#chNN-…">الفصل N</a> (also with
        &nbsp;) and the listed form <a href="#chNN-…">N</a> («الفصلان 2 و3») need N == NN."""
        paths = sorted((GUIDE / "chapters").glob("*.html"))
        self.assertTrue(paths, "no chapters")
        wrong = []
        checked = 0
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r'<a\b[^>]*\bhref="#ch(\d\d)(?:-[^"]*)?"[^>]*>(.*?)</a>', text, flags=re.S):
                label = build.plain_text(m.group(2)).replace(" ", " ").strip()
                n = re.fullmatch(r"(?:الفصل\s+)?(\d+)", label)
                if not n:
                    continue
                checked += 1
                if int(n.group(1)) != int(m.group(1)):
                    wrong.append(f"{path.name}: «{label}» links to #ch{m.group(1)}")
        self.assertGreater(checked, 0, "no chapter links found")
        self.assertEqual(wrong, [])

    TEAM_NOTE = re.compile(r"المرحلة\s*\d|\b6B\b|\bH\d{1,2}\b|حسب الإضافة|الإضافة [A-F]\b|factcheck|reader2")

    def test_todo_visible_text_has_no_team_notes(self):
        """Ruling R2-9: the visible text of a .todo box is for the reader. Team notes (phase numbers, 6B, H-items,
        «حسب الإضافة A», review file names) live only in an HTML comment inside the box that starts «فريق:»."""
        paths = sorted((GUIDE / "chapters").glob("*.html"))
        self.assertTrue(paths, "no chapters")
        problems = []
        boxes = 0
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r'<aside\b[^>]*\bclass="todo"[^>]*>(.*?)</aside>', text, flags=re.S):
                boxes += 1
                inner = m.group(1)
                for comment in re.findall(r"<!--(.*?)-->", inner, flags=re.S):
                    if not comment.strip().startswith("فريق:"):
                        problems.append(f"{path.name}: comment in a .todo box does not start «فريق:»: {comment.strip()[:40]}")
                visible = build.plain_text(re.sub(r"<!--.*?-->", "", inner, flags=re.S))
                hit = self.TEAM_NOTE.search(visible)
                if hit:
                    problems.append(f"{path.name}: team note «{hit.group(0)}» in visible .todo text: {visible.strip()[:60]}")
        self.assertGreater(boxes, 0, "no .todo boxes found")
        self.assertEqual(problems, [])


@unittest.skipUnless(_pdf_ready(), "no guide-ar/.build/test.pdf yet (run build.py) or pypdf missing")
class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pypdf
        cls.reader = pypdf.PdfReader(str(TEST_PDF))

    def _fonts(self):
        """{(font name without subset prefix, PDF font subtype)} over all pages."""
        found = set()
        for page in self.reader.pages:
            res = page.get("/Resources")
            fonts = res.get_object().get("/Font") if res is not None else None
            if fonts is None:
                continue
            for ref in fonts.get_object().values():
                font = ref.get_object()
                subtype = str(font.get("/Subtype", ""))
                names = []
                if "/BaseFont" in font:
                    names.append(font["/BaseFont"])
                desc = font.get("/FontDescriptor")  # Type3 fonts are named only here
                if desc is not None and "/FontName" in desc.get_object():
                    names.append(desc.get_object()["/FontName"])
                for name in names:
                    clean = str(name).lstrip("/").split("+", 1)[-1]
                    if clean:
                        found.add((clean, subtype))
        return found

    def test_fonts_embedded(self):
        fonts = self._fonts()
        names = " ".join(sorted(n for n, _ in fonts))
        families = ("Alexandria", "IBMPlexSansArabic", "Inter", "IBMPlexMono", "Syne")
        for family in families:
            self.assertIn(family, names, f"{family} not embedded; fonts found: {names}")
        # no system fallback (Segoe UI, Arial, Times, Tahoma …) anywhere
        strays = sorted(n for n, _ in fonts if not n.startswith(families))
        self.assertEqual(strays, [], f"fonts outside the five families: {strays}")
        # static TTFs only: Chrome turns variable fonts into Type3 glyph procedures
        type3 = sorted(n for n, sub in fonts if sub == "/Type3")
        self.assertEqual(type3, [], f"Type3 (variable-font) embeddings: {type3}")
        # every committed font file is printed somewhere (no unused weights shipped);
        # the files are named after their PostScript names
        embedded = {n for n, _ in fonts}
        for ttf in sorted((GUIDE / "fonts").rglob("*.ttf")):
            self.assertIn(ttf.stem, embedded, f"{ttf.name} is never used in the PDF")

    def _toc_rows(self, toc_page_numbers):
        """[(printed page number, link destination page)] for each TOC link, top to bottom."""
        named = self.reader.named_destinations
        rows = []
        for pno in toc_page_numbers:
            page = self.reader.pages[pno - 1]
            frags = []

            def visit(text, cm, tm, font, size, frags=frags):
                if text and text.strip():
                    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
                    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                    frags.append((x, y, text.strip()))

            page.extract_text(visitor_text=visit)
            links = []
            for annot in page.get("/Annots") or []:
                a = annot.get_object()
                dest = a.get("/Dest")
                if dest is None and a.get("/A") is not None:
                    dest = a["/A"].get_object().get("/D")
                if dest is None:
                    continue  # external link
                if not isinstance(dest, list):
                    dest = named[str(dest)]
                    target = self.reader.get_destination_page_number(dest) + 1
                else:
                    target = self.reader.get_page_number(dest[0].get_object()) + 1
                x0, y0, x1, y1 = [float(v) for v in a["/Rect"]]
                links.append((min(y0, y1), max(y0, y1), min(x0, x1), max(x0, x1), target))
            for ylo, yhi, xlo, xhi, target in sorted(links, key=lambda r: -r[1]):
                inside = [(x, t) for x, y, t in frags if ylo - 2 <= y <= yhi + 2 and xlo - 2 <= x <= xhi + 2]
                numbers = [(x, t) for x, t in inside if re.fullmatch(r"\d+", t)]
                printed = int(min(numbers)[1]) if numbers else None  # leftmost = the .pg column
                rows.append((printed, target))
        return rows

    def test_toc_numbers_match_outline(self):
        self.assertTrue(TOC_JSON.exists(), "build.py writes .build/toc.json next to test.pdf")
        entries = json.loads(TOC_JSON.read_text(encoding="utf-8"))
        self.assertTrue(entries)
        outline = build.outline_pages(TEST_PDF)
        for e in entries:
            self.assertIn(e["title"], outline, f"{e['id']} missing from the PDF outline")
            self.assertEqual(e["page"], outline[e["title"]], f"TOC number wrong for {e['id']}")
        # what is PRINTED on each TOC line (digits inside that line's link box only)
        # must equal the outline page and the page the link jumps to
        self.assertIn("المحتويات", outline, "the TOC title is not a bookmark")
        first, last = outline["المحتويات"], min(e["page"] for e in entries) - 1
        rows = self._toc_rows(range(first, max(first, last) + 1))
        self.assertEqual(len(rows), len(entries), f"TOC links {rows} vs entries {len(entries)}")
        for e, (printed, target) in zip(entries, rows):
            self.assertEqual(printed, e["page"], f"#{e['id']}: printed {printed}, outline {e['page']}")
            self.assertEqual(target, e["page"], f"#{e['id']}: link goes to {target}, printed {printed}")

    def test_metadata_and_page_mode(self):
        self.assertEqual(self.reader.trailer["/Root"].get("/PageMode"), "/UseOutlines")
        meta = self.reader.metadata
        self.assertEqual(meta.get("/Author"), "The Why Not AI")
        self.assertEqual(meta.get("/Title"), "WhyNot Cut — دليل الاستخدام")
        self.assertRegex(str(meta.get(build.HASH_KEY, "")), r"^[0-9a-f]{64}$")

    def test_outline_has_all_chapters(self):
        outline = build.outline_pages(TEST_PDF)
        for path in sorted((GUIDE / "chapters").glob("*.html")):
            h1 = [inner for lv, _, inner in build.toc_headings(path.read_text(encoding="utf-8")) if lv == "h1"]
            self.assertEqual(len(h1), 1, f"{path.name} needs exactly one h1.ch-title with an id")
            title = build.plain_text(h1[0])
            self.assertIn(title, outline, f"{path.name}: «{title}» is not a PDF bookmark")


COMMITTED_PDF = GUIDE.parent / "whynot-cut" / "docs" / "WhyNot-Cut-Guide-AR.pdf"


class CommittedPdfTests(unittest.TestCase):
    def test_committed_pdf_matches_sources(self):
        """The published PDF must be rebuilt after any change to the chapters, shell, stylesheet or screenshots."""
        if not COMMITTED_PDF.exists():
            self.skipTest(f"{COMMITTED_PDF} is absent (nothing published yet)")
        try:
            import pypdf
        except ImportError:
            self.skipTest("pypdf missing: run with the WhyNot Cut engine venv python")
        meta = pypdf.PdfReader(str(COMMITTED_PDF)).metadata or {}
        stored = meta.get(build.HASH_KEY)
        self.assertIsNotNone(stored, f"{COMMITTED_PDF.name} has no {build.HASH_KEY}: rebuild it with guide-ar/build.py")
        self.assertEqual(str(stored), build.source_hash(GUIDE),
                         f"{COMMITTED_PDF.name} is stale: the guide sources changed since it was built. "
                         "Run guide-ar/build.py and commit the new PDF.")


if __name__ == "__main__":
    unittest.main()
