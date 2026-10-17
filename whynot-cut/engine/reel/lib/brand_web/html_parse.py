# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""One fetched HTML page → the facts the brand extractors need (Addendum J3, J13.1). Stdlib `html.parser` only.

Everything on the page is data. Comments are dropped and never extracted; script, style, iframe, noembed, noframes
and xmp content never reaches the text fields (nor do tags written inside them); `<noscript>` / `<template>` text is
kept apart (`extra_text`); text fields of the page (title, meta, headings, links, alt, captions) are cut to FIELD_MAX.
JSON-LD objects are kept as parsed (at most JSONLD_MAX, flattened through @graph and nested objects); the J-T3
extractors cap and filter every value they take from them. URLs are made absolute against the page (or an http(s)
`<base href>`) and kept only when they are http(s). Inline SVGs are kept verbatim (the raw source slice, so `viewBox`
and `linearGradient` keep their case) for the sanitiser (J2.4); an unclosed SVG ends where HTML content starts, as in
a browser. Malformed HTML never raises: the parser is forgiving and every helper guards its own input.
"""
from __future__ import annotations

import codecs
import html
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

FIELD_MAX = 500
JSONLD_MAX = 200
JSONLD_DEPTH = 12
SVG_MAX_BYTES = 1_000_000
SVG_MAX = 30
LIST_MAX = 2000
STACK_MAX = 10000
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_SKIP_TEXT = {"script", "style"}
_RAW = {"iframe", "noembed", "noframes", "xmp"}          # raw text a browser never shows as page text
_EXTRA_TEXT = {"noscript", "template"}
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_MOUNT_IDS = {"root", "app", "__next", "__nuxt", "___gatsby", "svelte", "q-app"}
_SVG_BREAKOUT = {"b", "big", "blockquote", "body", "br", "center", "code", "dd", "div", "dl", "dt", "em", "embed",
                 "h1", "h2", "h3", "h4", "h5", "h6", "head", "hr", "i", "img", "li", "listing", "menu", "meta", "nobr",
                 "ol", "p", "pre", "ruby", "s", "small", "span", "strong", "strike", "sub", "sup", "table", "tt",
                 "u", "ul", "var"}                       # the HTML parsing spec's list (an SVG may hold its own <a>)
_EXEC_SCRIPT = {"", "text/javascript", "application/javascript", "module", "text/ecmascript",
                "application/ecmascript", "text/jscript", "application/x-javascript"}
_WS = re.compile(r"\s+")
# The WHATWG Encoding Standard's labels → Python codecs. Nothing else is accepted (utf-7, unicode_escape, EBCDIC,
# mbcs/oem … would decode differently or per machine): an unknown label means UTF-8.
_WHATWG = {}
for _codec, _labels in {
    "utf-8": "utf-8 utf8 unicode-1-1-utf-8 unicode11utf8 unicode20utf8 x-unicode20utf8",
    "cp1252": "windows-1252 cp1252 latin1 latin-1 l1 iso-8859-1 iso8859-1 iso88591 iso_8859-1 iso-ir-100 ascii "
              "us-ascii ansi_x3.4-1968 cp819 csisolatin1 ibm819 x-cp1252 x-user-defined",
    "cp1250": "windows-1250 cp1250 x-cp1250", "cp1251": "windows-1251 cp1251 x-cp1251",
    "cp1253": "windows-1253 cp1253 x-cp1253", "cp1254": "windows-1254 cp1254 x-cp1254 latin5 iso-8859-9 l5",
    "cp1255": "windows-1255 cp1255 x-cp1255", "cp1256": "windows-1256 cp1256 x-cp1256",
    "cp1257": "windows-1257 cp1257 x-cp1257", "cp1258": "windows-1258 cp1258 x-cp1258",
    "iso8859_2": "iso-8859-2 iso8859-2 latin2 l2", "iso8859_5": "iso-8859-5 iso8859-5 cyrillic",
    "iso8859_6": "iso-8859-6 iso8859-6 arabic asmo-708 ecma-114 iso-8859-6-e iso-8859-6-i",
    "iso8859_7": "iso-8859-7 iso8859-7 greek", "iso8859_8": "iso-8859-8 iso8859-8 hebrew visual",
    "iso8859_15": "iso-8859-15 iso8859-15 latin9 l9", "koi8_r": "koi8-r koi8 koi", "koi8_u": "koi8-u koi8-ru",
    "mac_roman": "macintosh mac x-mac-roman csmacintosh", "cp866": "ibm866 866 cp866 csibm866",
    "cp874": "windows-874 tis-620 iso-8859-11", "gb18030": "gb18030 gbk gb2312 x-gbk chinese csgb2312",
    "big5": "big5 big5-hkscs cn-big5 x-x-big5", "shift_jis": "shift_jis shift-jis sjis ms_kanji windows-31j x-sjis",
    "euc_jp": "euc-jp x-euc-jp", "iso2022_jp": "iso-2022-jp", "euc_kr": "euc-kr ks_c_5601-1987 windows-949 korean",
    "utf-16-le": "utf-16le utf-16", "utf-16-be": "utf-16be",
}.items():
    for _l in _labels.split():
        _WHATWG[_l] = _codec
_META_UTF16 = re.compile(r"^utf-?16", re.I)


def clip(s: str, n: int = FIELD_MAX) -> str:
    return (s or "")[:n]


def _clean(s: str) -> str:
    return clip(_WS.sub(" ", (s or "").replace("\x00", "")).strip())


def _charset_from_ctype(ctype: str) -> str | None:
    m = re.search(r"charset\s*=\s*[\"']?([\w.:-]+)", ctype or "", re.I)
    return m.group(1) if m else None


def _text_codec(name: str | None, from_meta: bool = False) -> str | None:
    """A codec that really decodes text (base64, rot13, zlib, idna … are refused), with browser label mapping."""
    if not name:
        return None
    n = name.strip().lower()
    if from_meta and _META_UTF16.match(n):
        return "utf-8"                                    # HTML: a <meta> can't switch to UTF-16
    codec = _WHATWG.get(n)
    if not codec:
        return None
    try:
        return codecs.lookup(codec).name
    except LookupError:
        return None


def decode(body: bytes, ctype: str = "") -> tuple:
    """(text, encoding): BOM, then the Content-Type charset, then <meta charset>, else UTF-8 (bad bytes replaced)."""
    for bom, enc in ((codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be")):
        if body.startswith(bom):
            return body[len(bom):].decode(enc, "replace"), enc
    enc = _text_codec(_charset_from_ctype(ctype))
    if not enc:
        head = body[:4096].decode("ascii", "replace")
        m = re.search(r"<meta[^>]+charset\s*=\s*[\"']?([\w.:-]+)", head, re.I)
        enc = _text_codec(m.group(1), from_meta=True) if m else None
    enc = enc or "utf-8"
    try:
        return body.decode(enc, "replace"), enc
    except (LookupError, UnicodeError, ValueError, TypeError):
        return body.decode("utf-8", "replace"), "utf-8"


def http_url(base: str, ref: str) -> str | None:
    """An absolute http(s) URL for `ref` on a page at `base`, else None (data:, javascript:, mailto:, garbage)."""
    ref = (ref or "").strip().replace("\x00", "")
    if not ref or len(ref) > 4096:
        return None
    try:
        u = urljoin(base, ref)
        p = urlsplit(u)
        if p.scheme not in ("http", "https") or not p.hostname:
            return None
        p.port                                    # noqa: B018 — raises for a bad port
    except ValueError:
        return None
    return u.split("#", 1)[0]


def _srcset_best(srcset: str) -> str | None:
    best, best_v = None, -1.0
    for part in (srcset or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        v = 1.0
        if len(bits) > 1:
            d = bits[1].lower()
            try:
                v = float(d[:-1]) if d[-1:] in ("w", "x") else 1.0
            except ValueError:
                v = 1.0
        if v > best_v:
            best, best_v = bits[0], v
    return best


def _flatten_jsonld(obj, out: list, paths: list, depth: int = 0, path: str = ""):
    """Every object with an @type or a name, through @graph, lists and nested values (an employee Physician too).
    `paths` gets, for each object, the keys it was found under ("" top level, "employee", "review.author"), so the
    extractors can tell a clinic's doctor from a reviewer."""
    if len(out) >= JSONLD_MAX or depth > JSONLD_DEPTH:
        return
    if isinstance(obj, list):
        for x in obj:
            _flatten_jsonld(x, out, paths, depth + 1, path)
        return
    if not isinstance(obj, dict):
        return
    if "@type" in obj or "name" in obj:
        out.append(obj)
        paths.append(path)
    for k, v in obj.items():
        if isinstance(v, (dict, list)):
            sub = path if k == "@graph" else (f"{path}.{k}" if path else str(k))[:200]
            _flatten_jsonld(v, out, paths, depth + 1, sub)


def _load_json(text: str):
    """First JSON value in `text` (trailing junk ignored); HTML-escaped JSON is unescaped once. Raises ValueError."""
    t = text.strip()
    if not t:
        raise ValueError("empty")
    dec = json.JSONDecoder(strict=False)
    try:
        return dec.raw_decode(t)[0]
    except (ValueError, RecursionError):
        if "&quot;" in t or "&#34;" in t:
            try:
                return dec.raw_decode(html.unescape(t))[0]
            except (ValueError, RecursionError):
                pass
        raise ValueError("bad json") from None


class Page:
    def __init__(self, url: str):
        self.url = url
        self.encoding = "utf-8"
        self.lang = ""
        self.dir = ""
        self.title = ""
        self.meta = []                 # {key, content, media}
        self.links = []                # {url, text}
        self.alternates = []           # (hreflang, url)
        self.stylesheets = []
        self.icons = []                # {rel, url, sizes, type, color}
        self.manifest = None
        self.images = []
        self.svgs = []
        self.style_blocks = []
        self.style_attrs = []
        self.jsonld = []
        self.jsonld_paths = []         # where each JSON-LD object was found ("", "employee", "review.author")
        self.jsonld_errors = 0
        self.headings = []             # (level, text)
        self.text = []
        self.extra_text = []
        self.script_bytes = 0
        self.script_srcs = []
        self.mount_point_empty = False

    def meta_values(self, key: str) -> list:
        k = key.lower()
        return [m["content"] for m in self.meta if m["key"] == k]

    def visible_text_length(self) -> int:
        return sum(len(t) for t in self.text)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("url", "encoding", "lang", "dir", "title", "meta", "links",
                                               "alternates", "stylesheets", "icons", "manifest", "images", "svgs",
                                               "style_blocks", "style_attrs", "jsonld", "jsonld_paths", "jsonld_errors", "headings",
                                               "text", "extra_text", "script_bytes", "script_srcs",
                                               "mount_point_empty")}


class _Parser(HTMLParser):
    def __init__(self, page: Page, source: str):
        super().__init__(convert_charrefs=True)
        self.p = page
        self.src = source
        self._line_starts = None
        self.base = page.url
        self.base_set = False
        self.stack = []                 # open element names
        self.open = {}                  # name → how many are open (end tags stay O(1) on deep pages)
        self.skip = 0                   # inside script/style
        self.raw = 0                    # inside iframe/noembed/noframes/xmp
        self.extra = 0                  # inside noscript/template
        self.svg_depth = 0
        self.fo = 0                     # inside an SVG <foreignObject>: HTML there doesn't end the SVG
        self.tmpl = 0                   # inside <template>: inert, its tags are not page content
        self.tmpl_code = 0              # inside a script/style within a template
        self.svg_start = None
        self.svg_meta = None
        self.a = None                   # the open <a>: {url, text, home}
        self.first_home_link_done = False
        self.in_home_link = False
        self.title_buf = None
        self.heading = None             # [level, parts]
        self.last_heading = ""
        self.figure_imgs = []           # images of the open <figure>
        self.figcap = None
        self.script_type = None
        self.script_buf = []
        self.style_buf = None
        self.mount = None               # [id, depth, had_content]
        self.in_body = False

    # ---- helpers
    def _offset(self) -> int:
        if self._line_starts is None:
            starts, i = [0], 0
            while True:
                i = self.src.find("\n", i)
                if i < 0:
                    break
                i += 1
                starts.append(i)
            self._line_starts = starts
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def _url(self, ref):
        return http_url(self.base, ref)

    def _flags(self) -> dict:
        return {"in_header": bool(self.open.get("header") or self.open.get("nav")), "in_nav": bool(self.open.get("nav")),
                "home_link": self.in_home_link, "in_noscript": bool(self.open.get("noscript")),
                "in_mount": self.mount is not None}

    def _push(self, tag):
        if len(self.stack) < STACK_MAX:
            self.stack.append(tag)
            self.open[tag] = self.open.get(tag, 0) + 1

    def _pop_to(self, tag):
        if not self.open.get(tag):
            return
        while self.stack:
            t = self.stack.pop()
            self.open[t] -= 1
            if t == tag:
                break

    def _mark_content(self):
        if self.mount is not None:
            self.mount[2] = True

    # ---- events
    def handle_starttag(self, tag, attrs):
        if self.raw:
            if tag in _RAW:
                self.raw += 1
            return
        if self.tmpl:
            if tag == "template":
                self.tmpl += 1
            elif tag in _SKIP_TEXT:
                self.tmpl_code += 1
            return
        if self.svg_depth and tag == "foreignobject":
            self.fo += 1
        if self.svg_depth and not self.fo and tag in _SVG_BREAKOUT:
            self._svg_close(self._offset())                # HTML content ends an unclosed SVG, as in a browser
        if tag == "svg" or self.svg_depth:
            self._svg_open(tag, {k: (v or "") for k, v in attrs if k})
            return
        a = {k: (v or "") for k, v in attrs if k}
        if tag not in _VOID:
            self._push(tag)
        if tag == "body":
            self.in_body = True
        if tag == "html":
            self.p.lang = clip(a.get("lang", ""), 20)
            self.p.dir = clip(a.get("dir", ""), 5)
        elif tag == "base" and not self.base_set:
            u = self._url(a.get("href"))
            self.base_set = True
            if u:
                self.base = u
        elif tag == "title":
            self.title_buf = []
        elif tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").strip().lower()
            if key and "content" in a and len(self.p.meta) < LIST_MAX:
                content = a["content"]
                if key in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src",
                           "og:url"):
                    content = self._url(content) or ""
                self.p.meta.append({"key": clip(key, 100), "content": _clean(content),
                                    "media": clip(a.get("media", ""), 200)})
        elif tag == "link":
            self._link(a)
        elif tag == "a":
            self._a_start(a)
        elif tag == "img":
            self._img(a)
        elif tag in _HEADINGS:
            self.heading = [_HEADINGS[tag], []]
        elif tag == "figure":
            self.figure_imgs = []
        elif tag == "figcaption":
            self.figcap = []
        elif tag in _SKIP_TEXT:
            self.skip += 1
            if tag == "style":
                self.style_buf = []
            if tag == "script":
                self.script_type = a.get("type", "").split(";", 1)[0].strip().lower()
                self.script_buf = []
                src = self._url(a.get("src"))
                if src and len(self.p.script_srcs) < LIST_MAX:
                    self.p.script_srcs.append(src)
        elif tag in _RAW:
            self.raw = 1
        elif tag == "template":
            self.tmpl = 1
            self.extra += 1
        elif tag in _EXTRA_TEXT:
            self.extra += 1
        if "style" in a and len(self.p.style_attrs) < LIST_MAX:
            self.p.style_attrs.append(clip(a["style"], 4000))
        body_child = len(self.stack) >= 2 and self.stack[-2] == "body"
        if self.mount is None and tag not in _VOID and (
                a.get("id", "").strip().lower() in _MOUNT_IDS or ("-" in tag and body_child)):
            self.mount = [a.get("id", tag), len(self.stack), False]

    def handle_startendtag(self, tag, attrs):
        if self.raw:
            return
        if tag == "svg" and not self.svg_depth:
            markup = self.get_starttag_text() or ""
            a = {k: (v or "") for k, v in attrs if k}
            self._svg_store(markup, self._svg_meta(a))
            return
        if self.svg_depth and tag not in _SVG_BREAKOUT:
            return                                         # self-closing children are part of the SVG slice
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.raw:
            if tag in _RAW:
                self.raw -= 1
            return
        if self.tmpl:
            if tag in _SKIP_TEXT and self.tmpl_code:
                self.tmpl_code -= 1
            if tag == "template":
                self.tmpl -= 1
                if not self.tmpl:
                    self.extra = max(0, self.extra - 1)
                    self._pop_to("template")
            return
        if self.svg_depth:
            if tag == "foreignobject" and self.fo:
                self.fo -= 1
            if tag == "svg":
                self.svg_depth -= 1
                if self.svg_depth == 0:
                    here = self._offset()
                    close = self.src.find(">", here)
                    self._svg_close(len(self.src) if close < 0 else close + 1)
            return
        if tag in _SKIP_TEXT and self.skip:
            self.skip -= 1
            if tag == "script":
                self._script_end()
            elif tag == "style" and self.style_buf is not None:
                if len(self.p.style_blocks) < LIST_MAX:
                    self.p.style_blocks.append("".join(self.style_buf)[:2_000_000])
                self.style_buf = None
        elif tag in _EXTRA_TEXT and self.extra:
            self.extra -= 1
        elif tag == "title" and self.title_buf is not None:
            if not self.p.title:
                self.p.title = _clean("".join(self.title_buf))
            self.title_buf = None
        elif tag in _HEADINGS and self.heading:
            text = _clean("".join(self.heading[1]))
            if text and len(self.p.headings) < LIST_MAX:
                self.p.headings.append((self.heading[0], text))
                self.last_heading = text
            self.heading = None
        elif tag == "a" and self.a is not None:
            self._a_end()
        elif tag == "figcaption" and self.figcap is not None:
            text = _clean("".join(self.figcap))
            for img in self.figure_imgs:
                img["figcaption"] = text
            self.figcap = None
        elif tag == "figure":
            self.figure_imgs = []
        self._pop_to(tag)
        if self.mount is not None and len(self.stack) < self.mount[1]:
            self.p.mount_point_empty = self.p.mount_point_empty or not self.mount[2]
            self.mount = None

    def handle_data(self, data):
        if self.raw or self.svg_depth or self.tmpl_code:
            return
        if self.skip:
            if self.style_buf is not None and sum(map(len, self.style_buf)) < 2_000_000:
                self.style_buf.append(data)
            if self.script_type is not None:
                if self.script_type in _EXEC_SCRIPT:          # JSON data blocks are not a script bundle
                    self.p.script_bytes += len(data)
                if self.script_type == "application/ld+json" and sum(map(len, self.script_buf)) < 2_000_000:
                    self.script_buf.append(data)
            return
        if self.title_buf is not None:
            self.title_buf.append(data)
            return
        text = _clean(data)
        if not text:
            return
        if self.extra:
            if len(self.p.extra_text) < LIST_MAX:
                self.p.extra_text.append(text)
            return
        self._mark_content()
        if self.heading is not None:
            self.heading[1].append(data)
        if self.a is not None:
            self.a["text"].append(data)
        if self.figcap is not None:
            self.figcap.append(data)
        if len(self.p.text) < LIST_MAX * 5:
            self.p.text.append(text)

    def handle_comment(self, data):
        return                                    # comments are never data (J13.1)

    # ---- elements
    def _link(self, a):
        rel = " ".join(a.get("rel", "").lower().split())
        url = self._url(a.get("href"))
        if not url:
            return
        rels = set(rel.split())
        if "stylesheet" in rels and "alternate" not in rels:
            if url not in self.p.stylesheets and len(self.p.stylesheets) < LIST_MAX:
                self.p.stylesheets.append(url)
        elif "alternate" in rels and a.get("hreflang"):
            if len(self.p.alternates) < 50:
                self.p.alternates.append((clip(a["hreflang"].strip().lower(), 20), url))
        elif "manifest" in rels:
            self.p.manifest = self.p.manifest or url
        elif rels & {"icon", "shortcut", "apple-touch-icon", "apple-touch-icon-precomposed", "mask-icon"}:
            if len(self.p.icons) < 100:
                self.p.icons.append({"rel": rel.replace("shortcut icon", "icon"), "url": url,
                                     "sizes": clip(a.get("sizes", ""), 50), "type": clip(a.get("type", ""), 50),
                                     "color": clip(a.get("color", ""), 50)})

    def _a_start(self, a):
        if self.a is not None:
            self._a_end()                         # an unclosed <a> ends where the next one starts
        raw = a.get("href", "").strip()
        url = self._url(raw)
        home = False
        if url and "#" not in raw and not self.first_home_link_done:   # a skip link (#main, /#main) is not it
            pu, pb = urlsplit(url), urlsplit(self.p.url)
            home = (pu.hostname or "").removeprefix("www.") == (pb.hostname or "").removeprefix("www.") and \
                pu.path in ("", "/") and not pu.query
            if home:
                self.first_home_link_done = True
        self.a = {"url": url, "text": [], "home": home, "label": a.get("aria-label", "") or a.get("title", ""),
                  "in_mount": self.mount is not None}
        self.in_home_link = home

    def _a_end(self):
        a = self.a
        self.a = None
        self.in_home_link = False
        if a["url"] and len(self.p.links) < LIST_MAX:
            text = _clean("".join(a["text"])) or _clean(a["label"])
            self.p.links.append({"url": a["url"], "text": text, "in_mount": a["in_mount"]})

    def _img(self, a):
        src = a.get("src") or a.get("data-src") or ""
        url = self._url(src)
        best = _srcset_best(a.get("srcset", "")) if a.get("srcset") else None
        best_url = self._url(best) if best else None
        if not url and not best_url:
            return
        if len(self.p.images) >= LIST_MAX:
            return
        img = {"url": url or best_url, "srcset_best": best_url, "alt": _clean(a.get("alt", "")),
               "title": _clean(a.get("title", "")), "cls": clip(a.get("class", ""), 200),
               "id": clip(a.get("id", ""), 100), "width": clip(a.get("width", ""), 10),
               "height": clip(a.get("height", ""), 10), "figcaption": "", "heading": self.last_heading,
               **self._flags()}
        self.p.images.append(img)
        if self.open.get("figure"):
            self.figure_imgs.append(img)

    def _svg_meta(self, a) -> dict:
        return {"cls": clip(a.get("class", ""), 200), "id": clip(a.get("id", ""), 100),
                "aria_label": _clean(a.get("aria-label", "")), **self._flags()}

    def _svg_open(self, tag, a):
        if tag != "svg":
            return
        if self.svg_depth == 0:
            self.svg_start = self._offset()
            self.svg_meta = self._svg_meta(a)
        self.svg_depth += 1

    def _svg_store(self, markup: str, meta: dict):
        if len(markup.encode("utf-8", "replace")) <= SVG_MAX_BYTES and len(self.p.svgs) < SVG_MAX:
            self.p.svgs.append({"markup": markup, **meta})

    def _svg_close(self, end: int):
        if self.svg_start is not None:
            self._svg_store(self.src[self.svg_start:end], self.svg_meta or {})
        self.svg_depth, self.fo, self.svg_start, self.svg_meta = 0, 0, None, None

    def _script_end(self):
        if self.script_type == "application/ld+json":
            text = "".join(self.script_buf)
            try:
                obj = _load_json(text)
                before = len(self.p.jsonld)
                _flatten_jsonld(obj, self.p.jsonld, self.p.jsonld_paths)
                if len(self.p.jsonld) == before and not isinstance(obj, (dict, list)):
                    self.p.jsonld_errors += 1
            except ValueError:
                if text.strip():
                    self.p.jsonld_errors += 1
        self.script_type = None
        self.script_buf = []


def parse_page(body: bytes, url: str, ctype: str = "") -> Page:
    page = Page(url)
    text, page.encoding = decode(body or b"", ctype)
    parser = _Parser(page, text)
    try:
        parser.feed(text)
        parser.close()
    except (AssertionError, ValueError, IndexError, RecursionError):
        pass                                      # keep whatever was read before the parser gave up
    if parser.svg_depth:
        parser._svg_close(len(text))
    if parser.a is not None:
        parser._a_end()
    if parser.mount is not None:
        page.mount_point_empty = page.mount_point_empty or not parser.mount[2]
    return page


def parse_manifest(body: bytes, url: str) -> dict:
    """The web manifest's name, colours and icons; anything invalid → empty."""
    try:
        obj = json.loads((body or b"").decode("utf-8-sig", "strict"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        return {"icons": []}
    if not isinstance(obj, dict):
        return {"icons": []}
    out = {k: _clean(str(obj[k])) for k in ("name", "short_name", "theme_color", "background_color")
           if isinstance(obj.get(k), str)}
    icons = []
    for ic in obj.get("icons") if isinstance(obj.get("icons"), list) else []:
        if not isinstance(ic, dict) or not isinstance(ic.get("src"), str):
            continue
        u = http_url(url, ic["src"])
        if u and len(icons) < 50:
            icons.append({"url": u, "sizes": clip(str(ic.get("sizes", "")), 50),
                          "type": clip(str(ic.get("type", "")), 50)})
    out["icons"] = icons
    return out
