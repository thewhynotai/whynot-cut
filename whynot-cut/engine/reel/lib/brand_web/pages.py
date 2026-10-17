# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Which pages of the client's site are read, in what order (Addendum J3 "Which pages").

The home page first, then ONE hreflang alternate home in the other language (ar ↔ en, same host; the exact `ar` /
`en` tag before a regional one), then same-site links ranked by their URL path and link text, in the spec's order:
about (about / من نحن / عن / نبذة), contact (contact / تواصل / اتصل), team (team / doctors / فريق / الأطباء), a
person's page (link text that starts with an honorific, or /dr-…, /doctors/<name>). Link text counts only when it is
a navigation label (the keyword with at most a few filler words such as "us", "our", «معنا»): "Read more about laser"
is not an about page. Ties keep the order the links were first seen. Links found on every page read join the queue;
the same page reached twice (a redirect, a trailing slash, the same bytes) is read once; same-site http links are
upgraded on an https site. Other hosts are listed (never fetched); files, mail, phone and fragment links are never
candidates. When the page cap is reached, what was left is reported. A page with almost no static text and a script
bundle (an empty app mount point, or no links and no images at all) is a site built with JavaScript: the run ends
there with that one outcome (no headless browser, G13).
"""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit, urlunsplit

from . import fetch, html_parse

RANK = ("about", "contact", "team", "person")
JS_SITE_MESSAGE = ("الموقع مبني بطريقة ما نقدرش نقراها من غير متصفح؛ اطلب ملفات الهوية من العميل",
                   "the site is built in a way we can't read without a browser; ask the client for the brand files")
EXTERNAL_MAX = 200
ALTERNATES_MAX = 2
JS_TEXT_MIN = 200
LABEL_WORDS_MAX = 5

_SEGMENTS = {
    "about": {"about", "about-us", "aboutus", "about_us", "who-we-are", "our-story", "من-نحن", "من_نحن", "عن",
              "عن-العيادة", "عن-المركز", "نبذة", "نبذة-عنا"},
    "contact": {"contact", "contact-us", "contactus", "contact_us", "تواصل", "تواصل-معنا", "اتصل", "اتصل-بنا"},
    "team": {"team", "our-team", "the-team", "meet-the-team", "doctors", "our-doctors", "physicians", "فريق",
             "فريق-العمل", "فريقنا", "الأطباء", "الاطباء", "أطباء", "اطباء", "أطباؤنا"},
}
_KEYWORDS = {
    "about": {"about", "عن", "نبذة"},
    "contact": {"contact", "تواصل", "اتصل"},
    "team": {"team", "doctors", "doctor", "physicians", "فريق", "فريقنا", "الفريق", "الأطباء", "الاطباء", "أطباء",
             "اطباء", "أطباؤنا", "أطبائنا", "اطبائنا", "طاقم"},
}
_PHRASES = {
    "about": {"من نحن", "who we are", "our story"},
    "contact": {"get in touch", "اتصل بنا", "تواصل معنا"},
    "team": {"meet the team"},
}
_FILLER = {"us", "our", "the", "page", "meet", "with", "clinic", "center", "centre", "medical", "doctor", "dr",
           "info", "information", "details", "معنا", "بنا", "عنا", "العيادة", "المركز", "العمل", "لنا", "الطبي",
           "الطبيب", "الدكتور", "تعرف", "على"}
_PUNCT = re.compile(r"[؟?!.:،,;|»«\"'()\[\]{}\-–—]+")
_NOT_PAGES = {"blog", "blogs", "news", "tag", "tags", "category", "categories", "product", "products", "shop",
              "store", "article", "articles", "post", "posts", "مقالات", "المقالات", "المدونة", "مدونة", "اخبار",
              "أخبار", "الأخبار", "منتجات", "المنتجات"}
_PAGE_EXT = re.compile(r"\.(html?|php|aspx?|jsp|shtml)$")
_HONORIFIC = re.compile(r"^(dr\.?|dra\.?|prof\.?|professor|د\s*\.|أ\s*\.\s*د\s*\.|ا\s*\.\s*د\s*\.|الدكتور|الدكتورة|"
                        r"الأستاذ|الأستاذة|الاستاذ|الاستاذة|استشاري|استشارية)(\s|$)", re.I)
_PERSON_PATH = re.compile(r"(^|/)(dr|dra)[-_.][^/]+|/(doctors?|physicians?|team|الأطباء|الاطباء|اطباء|أطباء)/"
                          r"(?!index\b|default\b|page\b|\d+/?$)[^/.]+/?$", re.I)
_FILE_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".rar", ".mp4", ".mov", ".mp3",
             ".m4a", ".wav", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".ico", ".css", ".js", ".json",
             ".xml", ".txt", ".avif", ".heic", ".woff", ".woff2", ".ttf", ".otf", ".exe", ".dmg", ".apk"}


def _label_category(text: str) -> str | None:
    t = " ".join(_PUNCT.sub(" ", (text or "").lower()).split())
    if not t:
        return None
    for cat in ("about", "contact", "team"):
        if t in _PHRASES[cat]:
            return cat
    words = re.findall(r"[\w؀-ۿ]+", t)
    if not words or len(words) > LABEL_WORDS_MAX:
        return None
    for cat in ("about", "contact", "team"):
        if any(w in _KEYWORDS[cat] for w in words) and all(w in _KEYWORDS[cat] or w in _FILLER for w in words):
            return cat
    return None


def link_category(url: str, text: str = "") -> str | None:
    """about | contact | team | person, or None. A path under a blog, news, tag, category or shop folder (or a
    dated one) is never ranked by its path; its link text still counts when it is a navigation label."""
    try:
        path = unquote(urlsplit(url).path or "/").lower()
    except ValueError:
        return None
    t = " ".join((text or "").split())
    if _HONORIFIC.match(t):
        return "person"
    segs = [_PAGE_EXT.sub("", s) for s in path.split("/") if s]
    if any(s in _NOT_PAGES or re.fullmatch(r"\d{4}", s) for s in segs):
        return _label_category(t)
    if _PERSON_PATH.search(path):
        return "person"
    for cat in ("about", "contact", "team"):
        if any(s in _SEGMENTS[cat] for s in segs):
            return cat
    if len(segs) <= 2:
        for seg in segs:                                   # a slug is read like a label: /about-the-clinic
            cat = _label_category(seg.replace("-", " ").replace("_", " "))
            if cat:
                return cat
    return _label_category(t)


def _same_site(u: str, page_url: str) -> bool:
    a = (urlsplit(u).hostname or "").removeprefix("www.")
    b = (urlsplit(page_url).hostname or "").removeprefix("www.")
    return a == b


def _pixel(img) -> bool:
    return img.get("width") in ("0", "1") or img.get("height") in ("0", "1")


def is_js_shell(page) -> bool:
    """Almost no static text, a script bundle, and nothing else to read: no images or inline SVGs outside the app
    mount point (a loader inside it, a <noscript> tracking pixel or a 1 px pixel don't count), and either no links
    of its own outside the mount or an empty mount (no text). An image-based one-pager with a widget script is a
    real page."""
    if page.visible_text_length() >= JS_TEXT_MIN:
        return False
    if not (page.script_srcs or page.script_bytes):
        return False
    in_mount = [x for x in page.images + page.svgs if x.get("in_mount") and not x.get("in_noscript")]
    loader = page.mount_point_empty and len(in_mount) <= 1     # one logo/spinner in an EMPTY mount is a loader

    def counts(x):
        return not (loader and x.get("in_mount"))
    content = [i for i in page.images if not i.get("in_noscript") and not _pixel(i) and counts(i)]
    if content or [s for s in page.svgs if counts(s)]:
        return False
    own_links = [lk for lk in page.links if _same_site(lk["url"], page.url) and counts(lk)]
    return not own_links or page.mount_point_empty


def _is_html(r) -> bool:
    ctype = (r.headers.get("content-type") or "").lower()
    if "html" in ctype:
        return True
    if ctype and not ctype.startswith(("text/plain", "application/octet-stream")):
        return False
    head = (r.body or b"")[:2048].lstrip().lower()
    return head.startswith((b"<!doctype html", b"<html", b"<head", b"<body")) or b"<html" in head


def _is_file(url: str) -> bool:
    path = urlsplit(url).path.lower()
    dot = path.rfind(".")
    return dot > path.rfind("/") and path[dot:] in _FILE_EXT


def _key(u: str) -> str:
    """One page, one key: www. or not, http or https, a trailing slash or index.html don't make another page."""
    p = urlsplit(u)
    path = re.sub(r"/index\.(html?|php|aspx?)$", "/", p.path, flags=re.I).rstrip("/") or "/"
    host = (p.netloc or "").lower().removeprefix("www.")
    return urlunsplit(("", host, path, p.query, ""))


class PageRecord:
    def __init__(self, result, role: str, page):
        self.url = result.url
        self.final_url = result.final_url
        self.role = role
        self.body = result.body
        self.sha256 = result.sha256
        self.headers = result.headers
        self.page = page


class Crawl:
    def __init__(self):
        self.pages = []
        self.skipped = []            # (url, reason)
        self.external_links = []
        self.js_site = False
        self.stop = None             # fetch.FetchStop for the home page
        self.cap = None              # the cap that ended the crawl ("pages" or a run cap)


def _parse(r):
    return html_parse.parse_page(r.body or b"", r.final_url, r.headers.get("content-type", ""))


def _home_language(page, home_key: str) -> str:
    """ar | en | "": the hreflang that points at the home page itself (themes often leave lang="en" on Arabic
    sites), else the page's lang, else its direction and script."""
    for lang, u in page.alternates:
        try:
            if _key(fetch.normalize(u)) == home_key and lang.split("-")[0] in ("ar", "en"):
                return lang.split("-")[0]
        except (ValueError, UnicodeError):
            continue
    mine = (page.lang or "").split("-")[0].lower()
    if mine:
        return mine
    if (page.dir or "").lower() == "rtl":
        return "ar"
    text = "".join(page.text)
    arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return ("ar" if arabic > latin else "en") if (arabic or latin) else ""


def _alternates(page, home_key: str, seen: set) -> list:
    """The alternate homes to try, best first: the other of ar/en, the exact tag before a regional one."""
    mine = _home_language(page, home_key)
    out = []
    for i, (lang, u) in enumerate(page.alternates):
        primary = lang.split("-")[0]
        if primary not in ("ar", "en") or (mine and primary == mine):
            continue
        try:
            n = fetch.normalize(u)
        except (ValueError, UnicodeError):
            continue
        if _key(n) in seen or _key(n) == home_key:
            continue
        out.append((0 if lang == primary else 1, i, n))
    return [n for _r, _i, n in sorted(out)]


def crawl(fetcher, on_page=None) -> Crawl:
    c = Crawl()
    scope = fetcher.scope
    seen = set()                     # keys of every URL queued or read
    read = set()                     # keys and hashes of pages recorded
    queue = []                       # [rank index, order, url, category]
    order = [0]

    def norm(u):
        try:
            n = fetch.normalize(u)
        except (ValueError, UnicodeError):
            return None
        if scope.scheme == "https" and n.startswith("http://") and scope.is_site_host(urlsplit(n).hostname or ""):
            n = "https://" + n[len("http://"):]
        return n

    def add_links(page):
        for lk in page.links:
            u = norm(lk["url"])
            if not u or _key(u) in seen or _is_file(u):
                continue
            ok, why = scope.page_ok(u)
            if not ok:
                if why == "offsite" and u not in c.external_links and len(c.external_links) < EXTERNAL_MAX:
                    c.external_links.append(u)
                continue
            cat = link_category(u, lk.get("text", ""))
            if cat is None:
                continue
            seen.add(_key(u))
            order[0] += 1
            queue.append([RANK.index(cat), order[0], u, cat])

    def record(r, role):
        fk = _key(norm(r.final_url) or r.final_url)
        if fk in read or r.sha256 in read:
            c.skipped.append((r.url, "duplicate"))
            return None
        read.update((fk, r.sha256, _key(r.url)))
        seen.add(fk)
        page = _parse(r)
        rec = PageRecord(r, role, page)
        c.pages.append(rec)
        if on_page:
            on_page(rec)
        return page

    try:
        home = fetcher.fetch_home()
    except fetch.FetchStop as e:
        c.stop = e
        return c
    if not _is_html(home):
        c.stop = fetch.FetchStop("bad_url")
        return c
    seen.add(_key(home.url))
    home_page = record(home, "home")
    if is_js_shell(home_page):
        c.js_site = True
        return c
    alts = _alternates(home_page, _key(home.final_url), seen)[:ALTERNATES_MAX]
    add_links(home_page)
    for alt in alts:                                       # one alternate home; the next one only if this one fails
        alt = norm(alt) or alt
        if _key(alt) in seen:
            continue
        seen.add(_key(alt))
        r = fetcher.fetch(alt, "page", alternate=True)
        if r.ok and _is_html(r):
            page = record(r, "alternate")
            if page is not None:
                add_links(page)
                break
        else:
            c.skipped.append((alt, r.reason or ("not_html" if r.ok else r.outcome)))
    while queue and not fetcher.stopped:
        queue.sort()
        _rank, _o, u, cat = queue.pop(0)
        r = fetcher.fetch(u, "page")
        if r.outcome == "cap" and r.reason == "pages":
            c.cap = "pages"
            c.skipped.append((u, "pages"))
            c.skipped.extend((q[2], "pages") for q in sorted(queue))
            queue.clear()
            break
        if not r.ok:
            c.skipped.append((u, r.reason or r.outcome))
            continue
        if not _is_html(r):
            c.skipped.append((u, "not_html"))
            continue
        page = record(r, cat)
        if page is not None:
            add_links(page)
    c.cap = c.cap or fetcher.stopped
    return c
