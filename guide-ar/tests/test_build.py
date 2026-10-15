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


class DevWordTests(unittest.TestCase):
    """Addendum G2: no developer words anywhere a reader sees, unless STYLE.md's «explained once» table lists the term
    and its first use in reading order carries data-term-first="<term>"."""

    TERMS = {"Python": ("Python",), "مسار": ("مسار",)}

    def test_visible_prose_drops_code_commands_comments_and_menu_paths(self):
        html = _wrap('<p>افتح <bdi dir="ltr"><code>prefs.json</code></bdi> من '
                     '<bdi dir="ltr">Window&nbsp;›&nbsp;UXP&nbsp;Plugins</bdi>.</p>'
                     '<div class="cmd" dir="ltr"><code>reel doctor --json</code></div>'
                     '<aside class="todo" data-phase="7"><p>جملة للقارئ.</p><!-- فريق: JSON token CLI --></aside>'
                     '<p>رسالة <bdi dir="ltr">engine not installed</bdi>.</p>'
                     '<style>p::before{content:"API"}</style>')
        prose = build.visible_prose(html)
        for gone in ("prefs.json", "UXP", "reel doctor", "JSON", "token", "API"):
            self.assertNotIn(gone, prose)
        for kept in ("افتح", "جملة للقارئ.", "engine not installed"):
            self.assertIn(kept, prose)

    def test_no_dev_words_in_prose(self):
        # a developer word in a paragraph fails
        bad = build.dev_word_problems(_wrap("<p>ملف JSON</p>"), terms={})
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("JSON", bad[0])
        # the same word inside code, a command box or a team comment passes
        self.assertEqual(build.dev_word_problems(_wrap("<p>افتح <code>prefs.json</code></p>"), terms={}), [])
        self.assertEqual(build.dev_word_problems(
            _wrap('<div class="cmd"><code>reel doctor --json</code></div><!-- فريق: JSON -->'), terms={}), [])
        # Arabic forms match with prefixes and without diacritics; «hook» (the editing term) is not a developer word
        self.assertEqual(len(build.dev_word_problems(_wrap("<p>والمسارات كلها</p>"), terms={})), 1)
        self.assertEqual(len(build.dev_word_problems(_wrap("<p>تقرير للمطوّر</p>"), terms={})), 1)
        self.assertEqual(build.dev_word_problems(_wrap("<p>البداية الجاذبة (hook) بالتايم كود</p>"), terms={}), [])
        # round-3 review I2: a word that starts a block right after another block still counts (blocks are separated
        # by a space, not glued to the previous letter; a glued fix-label is fix_problems' business, I1)
        for glued in ("<p>x</p><p>JSON</p>", "<p>نص</p><p>مسار</p>",
                      "<table><tr><td>الملف</td><td>جذر</td></tr></table>"):
            self.assertEqual(len(build.dev_word_problems(_wrap(glued), terms={})), 1, glued)
        self.assertEqual(build.visible_prose("<p>نص</p><p>آخر</p><h2>عنوان</h2>x<br>y"), "نص آخر عنوان x y")
        self.assertEqual(build.visible_prose("<p>كلمة<b>ملتصقة</b> و<bdi>Gate</bdi></p>"), "كلمةملتصقة وGate")
        # round-3 review M4: acronyms in any case, and the common extra words
        for word in ("json", "Json", "api", "xml", "cli", "script", "server", "config", "debug", "sha256",
                     "Script", "ترمينال", "التيرمينال", "السيرفر", "جيسون", "الاسكريبت"):
            self.assertEqual(len(build.dev_word_problems(_wrap(f"<p>ملف {word} هنا</p>"), terms={})), 1, word)
        # PATH stays case-sensitive («Copy as path» is a Windows menu label); «لوجو» is not «لوج»
        self.assertEqual(build.dev_word_problems(_wrap("<p>اختر Copy as path ثم لوجو</p>"), terms={}), [])
        self.assertEqual(len(build.dev_word_problems(_wrap("<p>متغير PATH</p>"), terms={})), 1)
        # an «explained once» term passes when its FIRST use carries data-term-first, later uses are free
        ok = ('<p><span data-term-first="Python">Python (لغة برمجة يحتاجها المحرك)</span></p>'
              "<p>رسالة عن Python.</p>")
        self.assertEqual(build.dev_word_problems(_wrap(ok), terms=self.TERMS), [])
        late = '<p>Python أولًا.</p><p><span data-term-first="Python">Python (لغة برمجة)</span></p>'
        self.assertEqual(len(build.dev_word_problems(_wrap(late), terms=self.TERMS)), 1)
        unmarked = "<p>المسار عنوان الملف.</p>"
        self.assertEqual(len(build.dev_word_problems(_wrap(unmarked), terms=self.TERMS)), 1)
        # data-term-first naming a term the table does not list is an error
        self.assertEqual(len(build.dev_word_problems(_wrap('<p data-term-first="JSON">ملف JSON</p>'), terms={})), 2)
        # the real guide: clean against the real STYLE.md table
        terms = build.explained_once_terms()
        for key in ("Python", "مسار", "XML", "محرك", "نموذج"):
            self.assertIn(key, terms)
        self.assertEqual(build.dev_word_problems(build.prose_sources(GUIDE)), [])

    def test_shell_index_is_linted_too(self):
        """Round-3 review M7: the cover, back cover and any page placed in index.html are read like a chapter."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "chapters").mkdir()
            (root / "chapters" / "01.html").write_text("<p>نص عادي</p>", encoding="utf-8")
            (root / "index.html").write_text(SHELL.replace("<!--@toc-->", "<p>ملف JSON</p>"), encoding="utf-8")
            sources = build.prose_sources(root)
            self.assertIn("نص عادي", sources)
            self.assertEqual(len(build.dev_word_problems(sources, terms={})), 1)
            self.assertEqual(build.dev_word_problems(build.chapter_sources(root), terms={}), [])

    def test_hook_is_not_a_dev_word(self):
        self.assertNotIn("hook", build.DEV_WORDS)
        for word in ("token", "daemon", "JSON", "CLI", "API", "venv", "Python", "MCP"):
            self.assertIn(word, build.DEV_WORDS)


class WawLatinTests(unittest.TestCase):
    """Round-3 review M2: the font draws a «و» that touches Latin text like a Latin "g" («Premiere Pro وAfter Effects»
    reads "After Effectsg Premiere Pro"). Repeat the preposition or reword: «في Premiere وفي After Effects»."""

    def test_waw_before_latin_is_flagged(self):
        for bad in ("<p>Premiere وAfter Effects</p>",
                    "<p><strong>Premiere Pro</strong>، و<strong>After Effects</strong></p>",
                    '<p>مثل <bdi dir="ltr">Gate 0</bdi> و<bdi dir="ltr">Gate 1</bdi></p>',
                    "<h2>مسار وPremiere</h2>",
                    "<p>على macOS وWindows</p>",
                    "<p>ثم وClaude يرد</p>"):
            self.assertEqual(len(build.waw_latin_problems(_wrap(bad))), 1, bad)

    def test_waw_before_latin_allowed_cases(self):
        for fine in ("<p>في Premiere وفي After Effects</p>",
                     "<p>على macOS وعلى Windows</p>",
                     "<p>هو Premiere</p>",                      # «و» inside an Arabic word
                     "<p>Premiere و After</p>",                  # a spaced «و» is the reader's problem, not a glued one
                     '<p><bdi dir="ltr"><code>assets/</code></bdi> و<bdi dir="ltr"><code>data/</code></bdi></p>',
                     '<div class="cmd"><code>reel doctor وabc</code></div>',
                     "<p>نص</p><!-- فريق: وClaude -->",
                     '<p title="وabc">نص</p>',
                     "<style>p::after{content:'وabc'}</style>"):
            self.assertEqual(build.waw_latin_problems(_wrap(fine)), [], fine)

    def test_real_guide_has_no_waw_before_latin(self):
        self.assertEqual(build.waw_latin_problems(build.prose_sources(GUIDE)), [])


def _fix(what="Premiere لا يستجيب.", why="اللوحة مغلقة.", do="افتح اللوحة.", labels=("اللي حصل", "ليه", "اعمل كده")):
    parts = []
    for cls, label, text in zip(("fix-what", "fix-why", "fix-do"), labels, (what, why, do)):
        if text is not None:
            parts.append(f'<p class="{cls}"><span class="fix-label">{label}</span> {text}</p>')
    return '<div class="fix">' + "".join(parts) + "</div>"


class TroubleshootingTests(unittest.TestCase):
    """Addendum G2: every ch17 entry says what happened, why, and the ONE thing to do."""

    def test_troubleshooting_entries_have_three_parts(self):
        self.assertEqual(build.fix_problems(_fix()), [])
        # a cause but no action fails
        self.assertEqual(len(build.fix_problems(_fix(do=None))), 1)
        # an empty part fails
        self.assertEqual(len(build.fix_problems(_fix(why=""))), 1)
        # the visible labels are required
        self.assertEqual(len(build.fix_problems(_fix(labels=("العرَض", "ليه", "اعمل كده")))), 1)
        # round-3 review I1: a space after every label, or Chrome shapes the label's last letter into the next word
        glued = _fix().replace("</span> ", "</span>")
        self.assertEqual(len(build.fix_problems(glued)), 3, build.fix_problems(glued))
        self.assertIn("space", build.fix_problems(glued)[0])
        self.assertEqual(len(build.fix_problems(_fix().replace("</span> ", "</span>", 1))), 1)
        # the action is ONE sentence
        self.assertEqual(len(build.fix_problems(_fix(do="أغلق Premiere. ثم افتح الفحص."))), 1)
        self.assertEqual(build.fix_problems(_fix(do='اكتب <bdi dir="ltr"><code>reel.doctor --x</code></bdi> ثم انتظر.')), [])
        # two systems: macOS first (G11)
        self.assertEqual(len(build.fix_problems(_fix(do="على Windows اضغط Install، وعلى Mac اضغط Install Font."))), 1)
        self.assertEqual(build.fix_problems(_fix(do="على Mac اضغط Install Font، وعلى Windows اضغط Install.")), [])
        # no row of the old table layout is left
        self.assertEqual(len(build.fix_problems("<table><tr><td>العرَض</td></tr></table>")), 1)
        self.assertEqual(build.fix_problems("<!-- <table><tr><td>قديم</td></tr></table> -->"), [])
        # print-only: an entry and the 3.0 line after it are kept on one page (idempotent, shape unchanged)
        todo = '<aside class="todo" data-phase="9"><p>جملة.</p><!-- فريق: x --></aside>'
        src = _fix() + _fix() + "\n" + todo
        kept = build.keep_fix_with_todo(src)
        self.assertEqual(kept.count('<div class="keep">'), 1)
        self.assertIn('<div class="keep">' + _fix() + "\n" + todo + "</div>", kept)
        self.assertEqual(build.keep_fix_with_todo(kept), kept)
        # the real chapter: only .fix entries, every one in shape
        ch17 = (GUIDE / "chapters" / "17-troubleshooting.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(ch17.count('class="fix"'), 30)
        self.assertEqual(build.fix_problems(ch17), [])


class MacFirstTests(unittest.TestCase):
    """Addendum G11: macOS is the primary platform. Any element that names both systems names macOS first (body
    text, lead-in paragraphs, list items, table cells, captions and section headings), and a two-platform pair split
    over sibling elements (two list items, two lead-ins, two h3/h4 headings) puts the macOS one first."""

    def test_macos_listed_first(self):
        problems = build.platform_order_problems
        # one element naming both systems, Windows first, fails; macOS first passes
        self.assertEqual(len(problems(_wrap("<p>للّصق اضغط Ctrl+V على Windows، وCmd+V على Mac.</p>"))), 1)
        self.assertEqual(problems(_wrap("<p>للّصق اضغط Cmd+V على Mac، وCtrl+V على Windows.</p>")), [])
        # section headings and table cells are scanned too
        self.assertEqual(len(problems(_wrap("<h2>حدود «تايدي» على Windows وmacOS</h2>"))), 1)
        self.assertEqual(problems(_wrap("<h2>حدود «تايدي» على macOS وWindows</h2>")), [])
        self.assertEqual(len(problems(_wrap(
            '<table><tr><td>نظام التشغيل</td><td><bdi dir="ltr">Windows 10/11</bdi> أو <bdi dir="ltr">macOS 14</bdi>'
            "</td></tr></table>"))), 1)
        # app names count as their system (PowerShell / Notepad / File Explorer vs Terminal / TextEdit / Finder),
        # and a menu-path label is read too: «Open with › Notepad» before «Open With › TextEdit» fails
        self.assertEqual(len(problems(_wrap("<p>الصق السطر في PowerShell أو Terminal.</p>"))), 1)
        self.assertEqual(len(problems(_wrap(
            '<li>افتحه بـ <bdi dir="ltr">Open&nbsp;with&nbsp;›&nbsp;Notepad</bdi> '
            '(على Mac: <bdi dir="ltr">Open&nbsp;With&nbsp;›&nbsp;TextEdit</bdi>)</li>'))), 1)
        # a pair split over siblings: two lead-ins inside one step, two list items, two h3 headings
        self.assertGreaterEqual(len(problems(_wrap(
            '<ol><li>الصق السطر.<p class="lead-in">على Windows، في PowerShell:</p>'
            '<div class="cmd"><bdi dir="ltr"><code>irm https://x | iex</code></bdi></div>'
            '<p class="lead-in">على Mac، في Terminal:</p>'
            '<div class="cmd"><bdi dir="ltr"><code>curl -fsSL https://x | bash</code></bdi></div></li></ol>'))), 1)
        self.assertEqual(len(problems(_wrap(
            '<ul><li>Windows: <bdi dir="ltr"><code>%APPDATA%\\Adobe</code></bdi></li>'
            '<li>macOS: <bdi dir="ltr"><code>~/Library/Adobe</code></bdi></li></ul>'))), 1)
        self.assertEqual(problems(_wrap(
            '<ul><li>macOS: <bdi dir="ltr"><code>~/Library/Adobe</code></bdi></li>'
            '<li>Windows: <bdi dir="ltr"><code>%APPDATA%\\Adobe</code></bdi></li></ul>')), [])
        self.assertEqual(len(problems(_wrap("<h3>على Windows</h3><p>خطوات.</p><h3>على macOS</h3><p>خطوات.</p>"))), 1)
        # single-platform text passes, also a Windows-only item next to an item that names both (macOS first)
        self.assertEqual(problems(_wrap("<p>على Windows تُثبَّت أداة Git for Windows.</p>")), [])
        self.assertEqual(problems(_wrap("<ol><li>على Windows: أداة صغيرة.</li>"
                                        "<li>على Mac داخل Documents، وعلى Windows في D.</li></ol>")), [])
        # a heading starts a new part: a Windows-only note and a later Mac-only section are not a pair
        self.assertEqual(problems(_wrap("<p>لم تُجرَّب بعد على Windows.</p><h2>موافقات macOS</h2>"
                                        "<p>على Mac اضغط Allow.</p>")), [])
        # code, command boxes and team comments are not read
        self.assertEqual(problems(_wrap('<p>شغّل <bdi dir="ltr"><code>PowerShell -c x</code></bdi> على Mac.</p>'
                                        "<!-- فريق: Windows ثم macOS -->")), [])
        # the real guide: macOS first everywhere
        self.assertEqual(problems(build.chapter_sources(GUIDE)), [])


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

    def test_product_name_never_splits(self):
        """«WhyNot / Cut» must not split at a line end (7a item 20): body text gets a no-break space; headings
        (bookmark and TOC titles), comments, attributes and command blocks keep the plain space."""
        src = ('<h2 id="a">ما الذي يقدّمه WhyNot Cut</h2>\n<p>يعمل WhyNot Cut <bdi dir="ltr"><code>WhyNot Cut 3.0.0</code>'
               '</bdi> و WhyNot&nbsp;Cut</p><!-- فريق: WhyNot Cut --><img alt="WhyNot Cut">'
               '<div class="cmd"><bdi dir="ltr"><code>echo WhyNot Cut</code></bdi></div><li>WhyNot Cut</li>')
        out = build.keep_product_name(src)
        self.assertIn('<h2 id="a">ما الذي يقدّمه WhyNot Cut</h2>', out)
        self.assertIn("<p>يعمل WhyNot&nbsp;Cut <bdi", out)
        self.assertIn("<code>WhyNot&nbsp;Cut 3.0.0</code>", out)
        self.assertIn("<!-- فريق: WhyNot Cut -->", out)
        self.assertIn('alt="WhyNot Cut"', out)
        self.assertIn("<code>echo WhyNot Cut</code>", out)
        self.assertIn("<li>WhyNot&nbsp;Cut</li>", out)
        self.assertEqual(build.keep_product_name(out), out, "idempotent")
        self.assertEqual(out.replace("&nbsp;", " "), src.replace("&nbsp;", " "), "only the space changes")
        # the real guide: no plain space left inside the name in printed body text
        html = build.assemble(GUIDE)
        start, end = html.index('<section class="chapter" id="ch00"'), html.index('<section class="back-cover"')
        body = re.sub(r"<!--.*?-->|<(h[1-6])\b.*?</\1\s*>|<div\b[^>]*\bclass=\"cmd[^\"]*\"[^>]*>.*?</div>|<[^>]+>",
                      "", html[start:end], flags=re.S)
        self.assertGreater(len(body), 10000)
        self.assertNotIn("WhyNot Cut", body)

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

    def test_css_pagination_rules_wave_b(self):
        """Round 3 layout pass: the empty screenshot slot is short (a tall slot jumped to the next page and left a
        hole), a step may split from its shot, the owner box may split between bullets, a table never starts with
        only its header and one row, a code pill keeps air next to Arabic, and the example-clinic chip only shows on
        shots that are about the example client."""
        height = re.search(r"height:\s*(\d+)mm", self._rule(".shot-frame"))
        self.assertIsNotNone(height)
        self.assertLessEqual(int(height.group(1)), 22, "an empty screenshot slot must stay about 220 px tall")
        css = re.sub(r"/\*.*?\*/", "", (GUIDE / "styles.css").read_text(encoding="utf-8"), flags=re.S)
        self.assertRegex(self._rule("ol.steps > li"), r"break-inside:\s*auto")
        self.assertRegex(css, r"ol\.steps > li > figure\.shot \{[^}]*break-before:\s*avoid")
        self.assertRegex(css, r"ol\.steps > li > \.todo \{[^}]*break-before:\s*avoid")
        self.assertRegex(self._rule(".owner"), r"break-inside:\s*auto")
        self.assertRegex(self._rule(".owner"), r"box-decoration-break:\s*clone")
        self.assertRegex(self._rule(".owner > ul > li"), r"break-inside:\s*avoid")
        self.assertRegex(self._rule("thead"), r"break-after:\s*avoid")
        self.assertRegex(css, r"tbody tr:first-child:not\(:last-child\) \{[^}]*break-after:\s*avoid")
        self.assertRegex(self._rule("bdi > code"), r"margin-inline:\s*0\.18em")
        self.assertRegex(self._rule(".cmd code"), r"margin-inline:\s*0;", "the pill's air must not shrink a command block")
        self.assertRegex(self._rule('figure.shot[data-scope="app"] .shot-frame::before'), r"content:\s*none")
        self.assertRegex(self._rule(".shot-frame::before"), r'content:\s*"example-clinic"',
                         "the chip stays the default: only data-scope=app shots drop it")

    def test_chapters_have_no_plain_numbered_list(self):
        """A plain <ol> prints «.1» markers; every numbered list uses the violet ol.steps badges."""
        for path in sorted((GUIDE / "chapters").glob("*.html")):
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"<ol\b(?![^>]*\bclass=\"[^\"]*\bsteps\b)",
                                f"{path.name}: use <ol class=\"steps\"> (also with start= or another class)")

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
    def test_wait_for_file_waits_for_a_detached_browser(self):
        """Edge 155+: the launcher exits 0 before the detached browser writes the PDF; the build waits for it."""
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "late.pdf"
            threading.Timer(0.6, lambda: pdf.write_bytes(b"%PDF-1.7 x\n%%EOF\n")).start()
            self.assertTrue(build.wait_for_file(pdf, timeout=10, settle=0.3, poll=0.1))
            self.assertFalse(build.wait_for_file(Path(tmp) / "never.pdf", timeout=0.5, settle=0.1, poll=0.1))

    def test_wait_for_file_needs_the_pdf_end_marker_and_the_final_size(self):
        """Round-3 review M3: a size that stays put is not enough, the file must end with %%EOF."""
        import threading
        with tempfile.TemporaryDirectory() as tmp:
            # a partial file that never grows and never ends: timeout, not "done"
            partial = Path(tmp) / "partial.pdf"
            partial.write_bytes(b"%PDF-1.7 half a file")
            self.assertFalse(build.wait_for_file(partial, timeout=1.0, settle=0.2, poll=0.1))
            # written in two chunks with a pause shorter than `settle`: wait for the last chunk
            two = Path(tmp) / "two.pdf"
            two.write_bytes(b"%PDF-1.7 first chunk")

            def second():
                with open(two, "ab") as fh:
                    fh.write(b" second chunk\n%%EOF\n")

            threading.Timer(0.3, second).start()
            self.assertTrue(build.wait_for_file(two, timeout=10, settle=0.6, poll=0.1))
            self.assertTrue(two.read_bytes().endswith(b"%%EOF\n"))

    def _fake_browser(self, tmp, content):
        """A stand-in browser that exits 0 at once; it writes `content` to the --print-to-pdf path (none: nothing)."""
        script = tmp / "fake_browser.py"
        script.write_text(
            "import sys\n"
            f"content = {content!r}\n"
            "target = [a.split('=', 1)[1] for a in sys.argv if a.startswith('--print-to-pdf=')][0]\n"
            "if content is not None:\n"
            "    open(target, 'wb').write(content)\n", encoding="utf-8")
        if sys.platform == "win32":
            fake = tmp / "fake.cmd"
            fake.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="ascii")
        else:
            fake = tmp / "fake.sh"
            fake.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="ascii")
            fake.chmod(0o755)
        return fake

    def test_print_pdf_fails_on_a_file_the_browser_did_not_finish(self):
        """Round-3 review M3: after the wait times out the build raises, it does not carry on with a partial file."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "x.html").write_text("<p>x</p>", encoding="utf-8")
            profiles = tmp / "profiles"
            profiles.mkdir()
            old_timeout, old_settle = build.PRINT_TIMEOUT, build.PDF_SETTLE
            old_env = os.environ.get("WNC_BROWSER_TMP")
            build.PRINT_TIMEOUT, build.PDF_SETTLE, os.environ["WNC_BROWSER_TMP"] = 3, 0.3, str(profiles)
            try:
                with self.assertRaises(SystemExit) as cm:
                    build.print_pdf(tmp / "x.html", tmp / "x.pdf", self._fake_browser(tmp, b"%PDF-1.7 half a file"))
                self.assertIn("did not finish writing", str(cm.exception))
                # a finished file passes (generous timeout: starting the stand-in browser is slow on a busy machine)
                build.PRINT_TIMEOUT = 30
                build.print_pdf(tmp / "x.html", tmp / "ok.pdf", self._fake_browser(tmp, b"%PDF-1.7 x\n%%EOF\n"))
                self.assertTrue((tmp / "ok.pdf").read_bytes().endswith(b"%%EOF\n"))
            finally:
                build.PRINT_TIMEOUT, build.PDF_SETTLE = old_timeout, old_settle
                if old_env is None:
                    os.environ.pop("WNC_BROWSER_TMP", None)
                else:
                    os.environ["WNC_BROWSER_TMP"] = old_env

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
        # chapter 0 is the tester welcome page (round 3, G-T10); it is optional, chapter 1 always exists
        first = 0 if seen and seen[0] == 0 else 1
        self.assertEqual(seen, list(range(first, first + len(seen))),
                         "chapter file numbers must be consecutive from 00 (welcome page) or 01")
        self.assertEqual(problems, [])

    def test_welcome_page_is_chapter_zero(self):
        """The tester welcome page (G-T10) is chapter 0, first in the PDF: id ch00, h1 «0 · أهلًا بك في تجربة …», and it
        links the feedback route of chapter 17."""
        path = GUIDE / "chapters" / "00-welcome-testers.html"
        self.assertTrue(path.exists(), "guide-ar/chapters/00-welcome-testers.html is missing")
        text = path.read_text(encoding="utf-8")
        h1 = [inner for lv, hid, inner in build.toc_headings(text) if lv == "h1" and hid == "ch00-title"]
        self.assertEqual(len(h1), 1)
        self.assertTrue(build.plain_text(h1[0]).startswith("0 · أهلًا بك في تجربة WhyNot Cut"))
        self.assertIn('href="#ch17-feedback"', text)
        html = build.assemble(GUIDE)
        self.assertLess(html.index('id="ch00"'), html.index('id="ch01"'))
        toc = re.findall(r'data-for="([^"]+)"', build.build_toc(build.chapter_sources(GUIDE)))
        self.assertEqual(toc[:2], ["ch00-title", "ch01-title"])

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
