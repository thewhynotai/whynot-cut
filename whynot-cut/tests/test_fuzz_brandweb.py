# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 48 (L-T10, Addendum L §L4.4): property tests for the brand_web pure parsers.

Targets: html_parse.parse_page / parse_manifest / decode / http_url, css_parse.parse_css / urls_in, robots.parse and
Rules.allowed. Property: they return normally (none documents a typed error), inside a time cap, and the documented caps
hold on the output. Findings that are still open live in KNOWN_OPEN (id -> exception class): the property tests allow
that exception, and the strict test of the id is an expected failure while it is listed; when the owner fixes the bug that
test shows up as an UNEXPECTED SUCCESS: delete the entry. Profiles and the Hypothesis install: tests/security/fuzz/_hyp.py. Run:  tools/test.sh -p test_fuzz_brandweb.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE / "security" / "fuzz"))
_sys.path.insert(0, str(HERE.parent / "engine" / "reel"))

import _hyp  # noqa: E402
from _hyp import fuzz, given, requires_hypothesis, st  # noqa: E402

from lib.brand_web import css_parse, html_parse, robots  # noqa: E402

# id -> exception class of a finding that is still open (see the module docstring).
KNOWN_OPEN = {
    "robots_lone_surrogate": UnicodeEncodeError,
    "robots_redos": _hyp.Hang,       # no exception: regex backtracking holds the GIL, so it shows as a slow call
}
# Only the ROBOTS tests may tolerate an open robots finding, and only the exception it names: a UnicodeEncodeError or a hang in
# html_parse / css_parse / http_url is a NEW finding and must fail (review of L-T10). robots_redos has no exception (it is a
# slow call), so it never widens the allowed set; it only gates the MAX_SAFE_STARS filter below.
ROBOTS_OPEN = tuple(v for k, v in KNOWN_OPEN.items() if k != "robots_redos")
MAX_SAFE_STARS = 3                   # robots patterns with more '*' than this are the open ReDoS class (see OpenFindings)
MAX_OPEN_COST = 5 * 10 ** 7            # while robots_redos is open, a (pattern, path) pair is matched only when len(path) ** stars is below this
CAP = 10  # seconds per call
FM = html_parse.FIELD_MAX
LM = html_parse.LIST_MAX


def call(fn, *a, allowed=()):
    return _hyp.only_typed(fn, tuple(allowed) or (), *a, seconds=CAP) if allowed else _hyp.within(CAP, fn, *a)


def _typed(fn, *a):
    """Run fn under the time cap; ANY exception is a finding (html, css, manifest, url, decode tests)."""
    return _hyp.within(CAP, fn, *a)


def _typed_robots(fn, *a):
    """Like _typed, but the exception of a still-open ROBOTS finding is tolerated (returned as None)."""
    r = _hyp.only_typed(fn, ROBOTS_OPEN, *a, seconds=CAP)
    return None if isinstance(r, BaseException) else r


# ---- cap checks

def check_page(t, pg):
    t.assertIsInstance(pg, html_parse.Page)
    t.assertLessEqual(len(pg.title), FM)
    t.assertLessEqual(len(pg.lang), 20)
    t.assertLessEqual(len(pg.dir), 5)
    t.assertLessEqual(len(pg.meta), LM)
    for m in pg.meta:
        t.assertLessEqual(len(m["content"]), FM)
        t.assertLessEqual(len(m["key"]), 100)
        t.assertLessEqual(len(m["media"]), 200)
    t.assertLessEqual(len(pg.links), LM)
    for ln in pg.links:
        t.assertLessEqual(len(ln["text"]), FM)
        t.assertTrue(ln["url"].startswith(("http://", "https://")))
    t.assertLessEqual(len(pg.alternates), 50)
    t.assertLessEqual(len(pg.stylesheets), LM)
    t.assertLessEqual(len(pg.icons), 100)
    for ic in pg.icons:
        t.assertLessEqual(len(ic["sizes"]), 50)
        t.assertLessEqual(len(ic["type"]), 50)
        t.assertLessEqual(len(ic["color"]), 50)
    t.assertLessEqual(len(pg.images), LM)
    for im in pg.images:
        t.assertLessEqual(len(im["alt"]), FM)
        t.assertLessEqual(len(im["title"]), FM)
        t.assertLessEqual(len(im["figcaption"]), FM)
    t.assertLessEqual(len(pg.svgs), html_parse.SVG_MAX)
    for s in pg.svgs:
        t.assertLessEqual(len(s["markup"].encode("utf-8", "replace")), html_parse.SVG_MAX_BYTES)
    t.assertLessEqual(len(pg.style_blocks), LM)
    for b in pg.style_blocks:
        t.assertLessEqual(len(b), 2_000_000)
    t.assertLessEqual(len(pg.style_attrs), LM)
    for a in pg.style_attrs:
        t.assertLessEqual(len(a), 4000)
    t.assertLessEqual(len(pg.jsonld), html_parse.JSONLD_MAX)
    t.assertLessEqual(len(pg.headings), LM)
    for _lvl, h in pg.headings:
        t.assertLessEqual(len(h), FM)
    t.assertLessEqual(len(pg.text), LM * 5)
    for x in pg.text:
        t.assertLessEqual(len(x), FM)
    t.assertLessEqual(len(pg.extra_text), LM)
    for x in pg.extra_text:
        t.assertLessEqual(len(x), FM)
    t.assertLessEqual(len(pg.script_srcs), LM)
    t.assertIsInstance(pg.encoding, str)
    json.dumps(pg.as_dict(), default=str)        # as_dict is a plain, serialisable structure


def check_manifest(t, m):
    t.assertIsInstance(m, dict)
    t.assertLessEqual(len(m["icons"]), 50)
    for ic in m["icons"]:
        t.assertTrue(ic["url"].startswith(("http://", "https://")))
        t.assertLessEqual(len(ic["sizes"]), 50)
        t.assertLessEqual(len(ic["type"]), 50)
    for k in ("name", "short_name", "theme_color", "background_color"):
        if k in m:
            t.assertLessEqual(len(m[k]), FM)


def check_sheet(t, sh):
    t.assertIsInstance(sh, css_parse.Sheet)
    for r in sh.rules:
        t.assertLessEqual(len(r["at"]), css_parse.DEPTH_MAX)


# ---- strategies

BOMS = [b"", b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff", b"\xef\xbb"]
CTYPES = ["", "text/html", "text/html; charset=utf-8", "text/html; charset=utf-16", "text/html; charset=base64",
          "text/html; charset=rot13", "text/html; charset=idna", "text/html; charset=zlib", "charset=", "charset=\x00",
          "text/html; charset=latin1", "text/html; charset=cp65001", "text/html; charset='x'", "charset=" + "a" * 5000,
          "text/html; charset=windows-1256", "text/html; charset=utf-7", "text/html; charset=bogus"]
URLS = ["https://example.com/", "http://a.b/x/y?z=1#f", "https://xn--mgbh0fb.com/", "http://[::1]:80/", "", "x", "//x/y",
        "https://example.com:99999/", "file:///etc/passwd", "https://exa\0mple.com/"]
HOSTILE_ATTR = st.one_of(_hyp.hostile_text(), st.sampled_from(["x" * 100000, "javascript:alert(1)", "data:text/html,x",
                                                               "//evil.example/a", "http://[::1", "http://a:99999/",
                                                               "\\\\server\\share", "&quot;&#0;&#x110000;&amp"]))
ATTR_NAMES = ["href", "src", "srcset", "data-src", "style", "class", "id", "alt", "title", "content", "name", "property",
              "rel", "sizes", "type", "color", "hreflang", "media", "lang", "dir", "aria-label", "width", "height", "charset"]
TAGS = ["a", "img", "svg", "script", "style", "title", "meta", "link", "base", "html", "body", "head", "div", "span", "h1",
        "h2", "figure", "figcaption", "noscript", "template", "iframe", "xmp", "noembed", "header", "nav", "p", "b", "g",
        "path", "linearGradient", "my-app", "picture", "button", "!--", "![CDATA[", "?php", "/"]


@st.composite
def tag_piece(draw):
    tag = draw(st.sampled_from(TAGS))
    attrs = draw(st.lists(st.tuples(st.sampled_from(ATTR_NAMES) | _hyp.hostile_text(), HOSTILE_ATTR), max_size=5))
    quote = draw(st.sampled_from(['"', "'", "", "`"]))
    inner = " ".join("%s=%s%s%s" % (k, quote, v, quote) for k, v in attrs)
    kind = draw(st.sampled_from(["open", "close", "self", "unclosed", "open", "open"]))
    if kind == "close":
        return "</%s>" % tag
    if kind == "self":
        return "<%s %s/>" % (tag, inner)
    if kind == "unclosed":
        return "<%s %s" % (tag, inner)
    return "<%s %s>" % (tag, inner)


JSONLD_SNIPPETS = ["", "{", "[" * 3000, "{\"a\":" * 3000, "[]", "null", "42", "\"x\"", "{\"@type\":\"Organization\"}",
                   "&quot;a&quot;", "{&quot;@type&quot;:&quot;X&quot;}", "\x00", "{\"name\":\"\u202e\"}" * 3,
                   "{\"@graph\":[" + ",".join('{"@type":"T%d","name":"n"}' % i for i in range(400)) + "]}",
                   "[" * 100 + "{\"@type\":\"X\"}" + "]" * 100, "{\"@type\":\"A\"}{\"@type\":\"B\"}",
                   "NaN", "1e999999", "9" * 5000]


@st.composite
def html_doc(draw):
    parts = draw(st.lists(st.one_of(tag_piece(), _hyp.hostile_text(), st.sampled_from(_hyp.HOSTILE_PIECES),
                                    st.sampled_from(["<script type=application/ld+json>%s</script>" % s
                                                     for s in JSONLD_SNIPPETS]),
                                    st.sampled_from(["<svg viewBox='0 0 1 1'><path d='M0'/>",
                                                     "<svg><!ENTITY x SYSTEM 'file:///etc/passwd'>&x;</svg>",
                                                     "<!DOCTYPE svg [<!ENTITY a '&a;&a;'>]><svg>&a;</svg>",
                                                     "<svg/><svg/>", "<svg><svg><svg></svg>", "<svg><div>x</div>",
                                                     "<style>a{b:url(x)", "<!-- unclosed", "<![CDATA[ x", "<?xml",
                                                     "<a href=/><a href=/>", "&#xD800;&#0;&#x110000;&bogus;&amp",
                                                     "\u202e\u2066مرحبا\u2069"])),
                          max_size=40))
    return "".join(parts)


@st.composite
def page_bytes(draw):
    doc = draw(html_doc())
    enc = draw(st.sampled_from(["utf-8", "utf-16-le", "utf-16-be", "cp1256", "latin-1", "ascii"]))
    raw = doc.encode(enc, "replace") if enc != "utf-8" else doc.encode("utf-8", "replace")
    meta = draw(st.sampled_from(["", "<meta charset=utf-16>", "<meta charset=bogus>", "<meta charset=base64>",
                                 "<meta http-equiv=x content='text/html; charset=utf-7'>", "<meta charset=ascii>",
                                 "<meta charset=" + "x" * 5000 + ">", "<meta charset=\"cp1256\">"]))
    return draw(st.sampled_from(BOMS)) + meta.encode("ascii") + raw


def deep_html():
    return st.tuples(st.integers(min_value=100, max_value=5000),
                     st.sampled_from(["div", "span", "a", "svg", "b", "noscript", "figure", "h1", "p", "my-app", "g"]),
                     st.booleans()).map(lambda t: ("<%s>" % t[1]) * t[0] + "x" + (("</%s>" % t[1]) * t[0] if t[2] else ""))


# ---- html_parse

@requires_hypothesis
class FuzzHtml(unittest.TestCase):
    @fuzz()
    @given(st.binary(max_size=4000), st.sampled_from(CTYPES), st.sampled_from(URLS))
    def test_random_bytes(self, body, ctype, url):
        pg = _typed(html_parse.parse_page, body, url, ctype)
        if pg is not None:
            check_page(self, pg)

    @fuzz()
    @given(page_bytes(), st.sampled_from(CTYPES), st.sampled_from(URLS))
    def test_structured_hostile_html(self, body, ctype, url):
        pg = _typed(html_parse.parse_page, body, url, ctype)
        if pg is not None:
            check_page(self, pg)

    @fuzz(unit_examples=30)
    @given(deep_html())
    def test_deep_nesting(self, doc):
        pg = _typed(html_parse.parse_page, doc.encode("utf-8", "replace"), "https://example.com/")
        if pg is not None:
            check_page(self, pg)

    @fuzz(heavy=300_000, space=25)      # HEAVY waiver: every example is 300 KB or more (the shortest value is 300,000 bytes); 5 x 5 = 25 combinations
    @given(st.sampled_from(["<a href=%s>", "<img alt=%s>", "<meta name=a content=%s>", "<div style=%s>", "<svg id=%s>"]),
           st.sampled_from(["x" * 300000, "a b " * 100000, "&amp;" * 60000, "\u202e" * 100000, "مرحبا " * 50000]))
    def test_huge_attributes(self, tpl, val):
        pg = _typed(html_parse.parse_page, (tpl % ('"%s"' % val)).encode("utf-8", "replace") + b"</a></svg>", "https://example.com/")
        if pg is not None:
            check_page(self, pg)

    @fuzz(unit_examples=30)
    @given(st.sampled_from(["<a href=/x>t</a>", "<img src=/i.png>", "<meta name=a content=b>", "<link rel=icon href=/i>",
                            "<link rel=stylesheet href=/s%d.css>", "<h1>t</h1>", "<script src=/j></script>",
                            "<style>a{}</style>", "<p>text</p>", "<svg></svg>", "<link rel=alternate hreflang=en href=/e>",
                            "<div style=a:b>x</div>", "<script type=application/ld+json>{\"@type\":\"X\"}</script>",
                            "<noscript>n</noscript>"]),
           st.integers(min_value=2500, max_value=12000))
    def test_list_caps(self, piece, n):
        doc = "".join((piece % i) if "%d" in piece else piece for i in range(n))
        check_page(self, html_parse.parse_page(doc.encode("utf-8", "replace"), "https://example.com/"))

    @fuzz()
    @given(st.sampled_from(JSONLD_SNIPPETS) | html_doc() | st.integers(1, 300).map(lambda n: "[" * n + "]" * n),
           st.sampled_from(["application/ld+json", "application/ld+json; charset=x", "text/plain"]))
    def test_jsonld_hostile(self, payload, typ):
        doc = "<script type=\"%s\">%s</script>" % (typ, payload)
        pg = _typed(html_parse.parse_page, doc.encode("utf-8", "replace"), "https://example.com/")
        if pg is not None:
            check_page(self, pg)

    @fuzz()
    @given(_hyp.json_values(), st.sampled_from(URLS))
    def test_jsonld_structured(self, value, url):
        doc = "<script type=application/ld+json>%s</script>" % json.dumps(value)
        check_page(self, html_parse.parse_page(doc.encode("utf-8", "replace"), url))

    @fuzz(unit_examples=30, space=_hyp.deep_json_space())
    @given(_hyp.deep_json())
    def test_jsonld_deep(self, value):
        try:
            text = json.dumps(value)
        except RecursionError:
            return
        doc = "<script type=application/ld+json>%s</script>" % text
        check_page(self, html_parse.parse_page(doc.encode("utf-8", "replace"), "https://example.com/"))

    @fuzz()
    @given(st.binary(max_size=2000) | _hyp.hostile_text().map(lambda s: s.encode("utf-8", "replace")), st.sampled_from(CTYPES))
    def test_decode(self, body, ctype):
        text, enc = _typed(html_parse.decode, body, ctype)
        self.assertIsInstance(text, str)
        self.assertIsInstance(enc, str)
        text.encode("utf-8")              # a decoded page never holds a lone surrogate

    @fuzz()
    @given(st.sampled_from(BOMS), _hyp.hostile_text(), st.sampled_from(CTYPES))
    def test_decode_bom_variants(self, bom, s, ctype):
        text, _enc = _typed(html_parse.decode, bom + s.encode("utf-8", "replace"), ctype)
        self.assertIsInstance(text, str)

    @fuzz()
    @given(st.sampled_from(URLS) | _hyp.hostile_text(),
           _hyp.hostile_text() | st.sampled_from(["javascript:alert(1)", "data:text/html;base64,AAAA", "file:///C:/x",
                                                  "//evil/x", "\\\\server\\share", "http://a:99999/", "http://a:0/",
                                                  "http://[::1", "http://", "https:///x", "x" * 5000, "a\0b", "mailto:a@b",
                                                  "https://exa\0mple.com", "HTTP://A.B/%zz#f", "http://a b/", "  /x  ",
                                                  "\u202ehttp://x", "http://مثال.إختبار/"]))
    def test_http_url(self, base, ref):
        u = _typed(html_parse.http_url, base, ref)
        if u is not None:
            self.assertTrue(u.lower().startswith(("http://", "https://")))
            self.assertNotIn("#", u)
            self.assertLessEqual(len(ref.strip()), 4096)

    @fuzz()
    @given(st.binary(max_size=3000) | _hyp.json_values().map(lambda v: json.dumps(v).encode("utf-8")),
           st.sampled_from(URLS))
    def test_manifest(self, body, url):
        m = _typed(html_parse.parse_manifest, body, url)
        if m is not None:
            check_manifest(self, m)

    @fuzz(unit_examples=30, space=541 * 5 * 3)   # the whole strategy space is 8,115 combinations: Hypothesis stops at exhaustion
    @given(st.integers(60, 600), st.sampled_from(["https://x/%d.png", "javascript:%d", "/a/%d", "//h/%d", "data:x%d"]),
           st.sampled_from(["", "\ufeff", "\u202e"]))
    def test_manifest_icon_cap(self, n, tpl, prefix):
        body = (prefix + json.dumps({"name": "x" * 5000, "short_name": "\u202e" * 900, "theme_color": "#fff",
                                     "icons": [{"src": tpl % i, "sizes": "9" * 500, "type": 5} for i in range(n)]})
                ).encode("utf-8")
        m = html_parse.parse_manifest(body, "https://example.com/")
        check_manifest(self, m)

    @fuzz(unit_examples=30, space=2 * _hyp.deep_json_space())
    @given(_hyp.deep_json(), st.sampled_from(["", "\ufeff"]))
    def test_manifest_deep(self, value, prefix):
        try:
            text = json.dumps(value)
        except RecursionError:
            return
        check_manifest(self, html_parse.parse_manifest((prefix + text).encode("utf-8"), "https://example.com/"))


# ---- css_parse

CSS_BITS = ["{", "}", "(", ")", ";", "'", '"', "/*", "*/", "\\", "url(", "url('", 'url("', "@media x{", "@font-face{",
            "@import url(", "@import '", "@keyframes a{", "@supports (a:b){", "a{b:c}", "--x:", "!important", "<!--", "-->",
            "\n", "\r\n", "src:url(", "format(", "unicode-range:U+0-FF;", "\udc80", "\ud800", "\0", "\u202e", "مرحبا", " " * 50]


@requires_hypothesis
class FuzzCss(unittest.TestCase):
    @fuzz()
    @given(_hyp.hostile_text() | st.lists(st.sampled_from(CSS_BITS) | _hyp.hostile_text(), max_size=60).map("".join))
    def test_parse_css(self, text):
        sh = _typed(css_parse.parse_css, text)
        if sh is not None:
            check_sheet(self, sh)

    @fuzz(unit_examples=30)
    @given(st.sampled_from(["{", "(", "}", ")", "'", '"', "/*", "url(", "url('", 'url("', "@media a{", "a{", "\\", ";",
                            "a{b:url(", "@import url(", "{(", "(" + "{" * 3, "a{b:(", "@font-face{src:url("]),
           st.integers(min_value=1000, max_value=100000))
    def test_repeated_openers(self, bit, n):
        sh = _typed(css_parse.parse_css, bit * n)
        if sh is not None:
            check_sheet(self, sh)

    @fuzz(unit_examples=30)
    @given(st.sampled_from(["a{b:c;}", "@media x{", "@layer a{", "a{", "@font-face{"]),
           st.integers(min_value=65, max_value=3000))
    def test_depth_cap(self, bit, n):
        sh = _typed(css_parse.parse_css, bit * n + "x{y:z}" + "}" * n)
        if sh is not None:
            check_sheet(self, sh)

    @fuzz()
    @given(st.lists(st.sampled_from(["url(", "url('", 'url("', ")", "'", '"', "\\", " ", "a", "data:x", "\0", "\udc80", "\u202e"])
                    | _hyp.hostile_text(), max_size=80).map("".join))
    def test_urls_in(self, text):
        for u in _typed(css_parse.urls_in, text) or []:
            self.assertIsInstance(u, str)
            self.assertFalse(u.lower().startswith("data:"))

    @fuzz(unit_examples=30)
    @given(st.sampled_from(["url(", "url('", 'url("', "url( ", "url(\\", "url('\\"]), st.integers(10000, 100000),
           st.sampled_from(["", ")", "'", " "]))
    def test_urls_in_repeated(self, bit, n, tail):
        _typed(css_parse.urls_in, bit * n + tail)

    @fuzz()
    @given(st.sampled_from(CSS_BITS) | _hyp.hostile_text(), st.integers(1, 300))
    def test_font_face_and_import(self, bit, n):
        sh = _typed(css_parse.parse_css, "@import " + bit * n + ";@font-face{src:" + bit * n + ";font-family:" + bit * n + "}")
        if sh is not None:
            check_sheet(self, sh)


# ---- robots

ROBOTS_LINES = ["User-agent: *", "User-agent: WhyNotCut", "User-agent: WhyNotCut/3.0", "user-AGENT:\t*", "Disallow: /",
                "Disallow:", "Allow: /x", "Disallow: /*", "Disallow: /*$", "Disallow: /a*b*c$", "Allow: /$", "Crawl-delay: 5",
                "Crawl-delay: nan", "Crawl-delay: inf", "Crawl-delay: -1", "Crawl-delay: 1e999", "Disallow: /ملف", "Allow: /%61",
                "Disallow: /%zz", "Disallow: /\u202e", "# comment", "garbage", ":", "::", "Disallow: " + "*" * 3000,
                "Disallow: " + "/a*" * 1500 + "$", "Disallow: /" + "x" * 100000, "Sitemap: https://x/s.xml", "\ufeffUser-agent: *"]
PATHS = ["/", "", "/robots.txt", "/robots.txt?x", "/a/b", "/" + "a" * 5000, "/ملف/عربي", "/%61dmin", "/%", "/%2F", "/x?y=1",
         "/\u202e", "/\0", "/" + "ab" * 3000, "*", "$", "//"]
EOLS = ["\n", "\r\n", "\r", "\n\r", "\u2028", "\x0b", "\x0c", "\x1c", "\x85"]


@requires_hypothesis
class FuzzRobots(unittest.TestCase):
    def _run(self, text, paths):
        rules = _typed_robots(robots.parse, text)
        if rules is None:
            return
        self.assertIsInstance(rules, robots.Rules)
        if "robots_redos" in KNOWN_OPEN and any(l.count("*") > MAX_SAFE_STARS for l in text.splitlines()):
            return                        # open finding robots_redos: matching such a pattern can take minutes (filter goes with the entry)
        stars = max([l.count("*") for l in text.splitlines()] or [0])
        for p in paths:
            if "robots_redos" in KNOWN_OPEN and len(p) ** stars > MAX_OPEN_COST:
                continue                  # open finding robots_redos: matching costs about len(path) ** stars, minutes for 3 stars on 5000 chars
            r = _typed_robots(rules.allowed, p)
            if r is not None:
                self.assertIsInstance(r, bool)
        self.assertTrue(_hyp.within(CAP, rules.allowed, "/robots.txt"))

    @fuzz()
    @given(_hyp.hostile_text(), st.lists(_hyp.hostile_text(), max_size=4))
    def test_random_text(self, text, paths):
        self._run(text, paths)

    @fuzz()
    @given(st.lists(st.sampled_from(ROBOTS_LINES) | _hyp.hostile_text(), max_size=40), st.sampled_from(EOLS),
           st.lists(st.sampled_from(PATHS) | _hyp.hostile_text(), max_size=5))
    def test_structured(self, lines, eol, paths):
        self._run(eol.join(lines), paths)

    @fuzz()
    @given(st.lists(st.sampled_from(ROBOTS_LINES), min_size=1, max_size=12),
           st.lists(st.sampled_from(EOLS), min_size=12, max_size=12), st.sampled_from(PATHS))
    def test_mixed_line_endings(self, lines, eols, path):
        text = "User-agent: *\n" + "".join(l + e for l, e in zip(lines, eols))
        self._run(text, [path])

    @fuzz(unit_examples=30)
    @given(st.sampled_from(["*", "*a", "a*", "/*a", "$", "*$", "/a*$", "**", "*/", "?", "\\", "(", "[", ".*"]),
           st.integers(2, 3000), st.sampled_from(["a" * 30 + "b", "a" * 5000, "/" + "a" * 5000 + "x", "/a/a/a/a/b", "/*" * 500]))
    def test_wildcard_regex_blowup(self, unit, n, path):
        text = "User-agent: *\nDisallow: /" + unit * n + "\nAllow: /" + unit * n + "$\n"
        self._run(text, [path, "/" + "a" * 50 + "!"])

    @fuzz(unit_examples=30)
    @given(st.integers(2000, 8000), st.sampled_from(["Disallow: /a%d", "Allow: /b*%d$", "User-agent: u%d", "Crawl-delay: %d",
                                                      "Disallow: /%d*x*y"]))
    def test_many_rules(self, n, tpl):
        text = "User-agent: *\n" + "\n".join(tpl % i for i in range(n))
        self._run(text, ["/a1", "/" + "q" * 200])

    @fuzz()
    @given(st.sampled_from(["", "\ufeff", "\ufeff\ufeff"]), _hyp.hostile_text(), st.sampled_from(["whynotcut", "WhyNotCut", "*", "", "\u202e", "مرحبا", "A" * 5000]))
    def test_agent_argument(self, bom, text, agent):
        rules = _typed_robots(robots.parse, bom + "User-agent: *\nDisallow: /x\nUser-agent: WhyNotCut\nAllow: /\n" + text, agent)
        if rules is not None:
            _typed_robots(rules.allowed, "/x")

    @fuzz()
    @given(st.sampled_from(["allow_all", "deny_all"]), _hyp.hostile_text() | st.sampled_from(PATHS))
    def test_fixed_rules(self, which, path):
        r = getattr(robots, which)("5xx")
        res = _typed_robots(r.allowed, path)
        if res is not None:
            self.assertIsInstance(res, bool)


# ---- open findings: the strict test of each is an expected failure while its id is in KNOWN_OPEN. When the owner applies
# lane3/hooks/L-T10/robots-surrogate-redos.patch the tests show up as UNEXPECTED SUCCESS: delete the ids from KNOWN_OPEN and set
# the findings to fixed in regressions.json.
import time  # noqa: E402


def xfail_open(id_):
    return _hyp.xfail_while_open(id_, KNOWN_OPEN)


@requires_hypothesis
class OpenFindings(unittest.TestCase):
    @xfail_open("robots_lone_surrogate")
    def test_a_lone_surrogate_in_robots_is_not_a_crash(self):
        """robots._norm -> urllib.parse.quote strict UTF-8 encode: a lone surrogate in an Allow/Disallow value (parse) or in the
        path (Rules.allowed) raised UnicodeEncodeError."""
        robots.parse("User-agent: *\nDisallow: /\udc80")
        self.assertIsInstance(robots.parse("User-agent: *\nDisallow: /a").allowed("/\udc80"), bool)

    @xfail_open("robots_redos")
    def test_robots_matching_is_linear_not_backtracking(self):
        """robots.Rules._compile joins the pieces of a pattern with '.*' (re backtracking, O(n^stars)) and re holds the GIL, so
        no timeout can stop it: 'Disallow: /a*a*a*a*b' against '/' + 'a' * 1000 took 46 s (500 'a': 4.3 s)."""
        r = robots.parse("User-agent: *\nDisallow: /a*a*a*a*b")
        t0 = time.monotonic()
        r.allowed("/" + "a" * 500)
        self.assertLess(time.monotonic() - t0, 0.5, "matching took %.1f s" % (time.monotonic() - t0))


if __name__ == "__main__":
    unittest.main()
