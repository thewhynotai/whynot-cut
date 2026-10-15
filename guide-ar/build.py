#!/usr/bin/env python3
"""Build the Arabic WhyNot Cut user guide PDF.

    ~/.whynot-cut/venv/Scripts/python.exe guide-ar/build.py [--out PATH] [--release]

Pipeline: assemble (index.html + chapters/*.html; one-page TOC from h1.ch-title, a
chapter map per chapter from its h2[id]) -> lint (bidi isolation, digits, anchors,
ids, images, forbidden words) -> print with headless Edge/Chrome -> rebuild the
outline + write the PDF metadata (title, author, open with bookmarks, source hash)
-> read the outline -> fill the TOC and chapter-map page numbers -> print again ->
check those numbers == outline pages -> copy.

The default build is a DRAFT (placeholders allowed; the PDF subject says «مسودة»).
--release (or WNC_RELEASE=1) also fails on any .todo / data-phase, any .shot-frame
without an <img>, and draft-only phrases outside a .todo. The committed PDF of a
release must come from a --release build.

Outputs: whynot-cut/docs/WhyNot-Cut-Guide-AR.pdf and dist/WhyNot-Cut-Guide-AR.pdf
(or only --out PATH), plus guide-ar/.build/{guide.html,test.pdf,toc.json} for the
tests in guide-ar/tests. Exit 1 on lint problems or a TOC/outline mismatch.

Standard library only, except pypdf (reading the PDF outline), which is loaded
lazily: run with the WhyNot Cut engine venv python, which has it.
"""
from __future__ import annotations

import argparse
import hashlib
import html as htmllib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PDF_NAME = "WhyNot-Cut-Guide-AR.pdf"
DEFAULT_OUTPUTS = (REPO / "whynot-cut" / "docs" / PDF_NAME, REPO / "dist" / PDF_NAME)
MAX_PASSES = 4
DEFAULT_PRINT_TIMEOUT = 300
PDF_TITLE = "WhyNot Cut — دليل الاستخدام"
PDF_AUTHOR = "The Why Not AI"
PDF_SUBJECT = "دليل استخدام WhyNot Cut · Powered by thewhynot.ai"
PDF_SUBJECT_DRAFT = PDF_SUBJECT + " — مسودة (draft)"
HASH_KEY = "/WNC_SourceHash"


def _print_timeout(raw: str | None) -> int:
    """WNC_PRINT_TIMEOUT in seconds; anything that is not a positive whole number falls back to the default."""
    if raw is None or not raw.strip():
        return DEFAULT_PRINT_TIMEOUT
    try:
        value = int(raw.strip())
    except ValueError:
        value = 0
    if value <= 0:
        sys.stderr.write(f"warning: WNC_PRINT_TIMEOUT={raw!r} is not a positive number of seconds; "
                         f"using {DEFAULT_PRINT_TIMEOUT}\n")
        return DEFAULT_PRINT_TIMEOUT
    return value


PRINT_TIMEOUT = _print_timeout(os.environ.get("WNC_PRINT_TIMEOUT"))  # seconds per browser print

VENV_HINT = (
    "pypdf is not installed for this Python. Run the build with the WhyNot Cut engine venv:\n"
    "  Windows: %USERPROFILE%\\.whynot-cut\\venv\\Scripts\\python.exe guide-ar/build.py\n"
    "  macOS:   ~/.whynot-cut/venv/bin/python guide-ar/build.py"
)


def _pypdf():
    try:
        import pypdf  # noqa: WPS433 (lazy on purpose)
    except ImportError as exc:  # pragma: no cover - depends on the interpreter
        raise SystemExit(VENV_HINT) from exc
    return pypdf


# ---------------------------------------------------------------- text helpers
def _say(message: str) -> None:
    """print() that never fails on a console without UTF-8 (Windows cp1252)."""
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "backslashreplace").decode("ascii"))


_BIDI_CONTROLS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def plain_text(fragment: str) -> str:
    """Visible text of an HTML fragment, whitespace collapsed (matches PDF outline titles)."""
    text = re.sub(r"<[^>]+>", "", fragment)
    text = htmllib.unescape(text)
    text = _BIDI_CONTROLS.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class _HeadingParser(HTMLParser):
    """Collects h1–h6 with their attributes and inner HTML.

    A real parser, so headings inside <!-- comments -->, <style> or <script> are
    ignored and single-quoted / unquoted attributes work.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.found: list[tuple[str, dict[str, str], str]] = []
        self._cur: tuple[str, dict[str, str], list[str]] | None = None
        self._raw_depth = 0  # inside <style>/<script>

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._raw_depth += 1
            return
        if self._raw_depth:
            return
        if tag in _HEADING_TAGS and self._cur is None:
            self._cur = (tag, {k.lower(): (v or "") for k, v in attrs}, [])
        elif self._cur is not None:
            self._cur[2].append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if self._cur is not None and not self._raw_depth:
            self._cur[2].append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self._raw_depth = max(0, self._raw_depth - 1)
            return
        if self._raw_depth or self._cur is None:
            return
        if tag == self._cur[0]:
            self.found.append((self._cur[0], self._cur[1], "".join(self._cur[2])))
            self._cur = None
        else:
            self._cur[2].append(f"</{tag}>")

    def handle_data(self, data):
        if self._cur is not None and not self._raw_depth:
            self._cur[2].append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def all_headings(html: str) -> list[tuple[str, dict[str, str], str]]:
    """(tag, attrs, inner_html) for every h1–h6 outside comments/style/script, in document order."""
    p = _HeadingParser()
    p.feed(html)
    p.close()
    return p.found


def toc_headings(html: str) -> list[tuple[str, str, str]]:
    """(level, id, inner_html) for every h1.ch-title and h2[id], in document order."""
    found = []
    for tag, attrs, inner in all_headings(html):
        hid = attrs.get("id")
        if tag not in ("h1", "h2") or not hid:
            continue
        if tag == "h1" and "ch-title" not in attrs.get("class", "").split():
            continue
        found.append((tag, hid, inner))
    return found


# ---------------------------------------------------------------- assemble
def _toc_label(inner: str) -> str:
    """Heading inner HTML for a TOC entry: keep <bdi>/<code>, drop ids and nested links."""
    inner = re.sub(r"""\s+id\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", "", inner)
    inner = re.sub(r"</?a\b[^>]*>", "", inner)
    return re.sub(r"\s+", " ", inner).strip()


_NUM_LABEL = re.compile(r"\s*(\d+)\s*·\s*(.*)", re.S)


def _split_ch_num(label: str) -> str:
    """«N · العنوان» -> <span class="num">N</span><span class="ch-sep"> · </span>العنوان.

    The « · » stays in the text (hidden by CSS), so the plain text is unchanged.
    """
    m = _NUM_LABEL.fullmatch(label)
    if not m:
        return label
    return f'<span class="num">{m.group(1)}</span><span class="ch-sep"> · </span>{m.group(2)}'


def build_toc(chapters_html: str) -> str:
    """The TOC page: one row per chapter (h1.ch-title). Sections are listed in each chapter's map."""
    items = []
    for level, hid, inner in toc_headings(chapters_html):
        if level != "h1":
            continue
        items.append(
            f'<li class="toc-h1"><a href="#{hid}"><span>{_split_ch_num(_toc_label(inner))}</span>'
            f'<span class="pg" data-for="{hid}"></span></a></li>'
        )
    return '<ol class="toc-list">\n' + "\n".join(items) + "\n</ol>"


CH_MAP_MIN = 2  # a chapter with fewer sections gets no map
_CH_OPENING = re.compile(r"""<h1\b[^>]*\bclass\s*=\s*["'][^"']*\bch-title\b[^"']*["'][^>]*>.*?</h1>"""
                         r"""(?:\s*<p\b[^>]*>.*?</p>)?""", re.S | re.I)


def build_chapter_map(chapter_html: str) -> str:
    """Insert <ol class="ch-map"> (the chapter's h2[id] with page numbers) after the chapter's
    first paragraph (or right after its h1 when no paragraph follows it)."""
    h2s = [(hid, inner) for level, hid, inner in toc_headings(chapter_html) if level == "h2"]
    if len(h2s) < CH_MAP_MIN:
        return chapter_html
    items = "\n".join(
        f'<li><a href="#{hid}"><span>{_toc_label(inner)}</span>'
        f'<span class="map-pg" data-for="{hid}"></span></a></li>' for hid, inner in h2s)
    block = f'\n\n<ol class="ch-map">\n{items}\n</ol>'
    m = _CH_OPENING.search(chapter_html)
    if not m:
        return chapter_html
    return chapter_html[:m.end()] + block + chapter_html[m.end():]


_CH_H1_NUM = re.compile(r"""(<h1\b[^>]*\bclass\s*=\s*["'][^"']*\bch-title\b[^"']*["'][^>]*>)\s*(\d+)\s*·\s*""", re.I)


def mark_chapter_numbers(html: str) -> str:
    """Wrap the leading «N · » of every h1.ch-title as <span class="ch-num">N<span class="ch-sep"> · </span></span>.

    The heading's plain text (bookmark title, TOC check) stays «N · العنوان». Idempotent.
    """
    return _CH_H1_NUM.sub(lambda m: f'{m.group(1)}<span class="ch-num">{m.group(2)}'
                                    f'<span class="ch-sep"> · </span></span>', html)


_SHOT_THEN_TODO = re.compile(r"""(<figure\b[^>]*\bclass="shot"[^>]*>(?:(?!</figure>).)*</figure>)(\s*)"""
                             r"""(<aside\b[^>]*\bclass="todo"[^>]*>.*?</aside>)""", re.S)


def keep_shot_with_todo(html: str) -> str:
    """Wrap a screenshot slot and the 3.0 line right after it in <div class="keep"> (CSS: break-inside
    avoid), so the one-line box never opens a page alone. Chrome ignores break-after on the
    table-display figure. Idempotent."""
    return _SHOT_THEN_TODO.sub(
        lambda m: m.group(0) if m.string[max(0, m.start() - 20):m.start()].endswith('<div class="keep">')
        else f'<div class="keep">{m.group(1)}{m.group(2)}{m.group(3)}</div>', html)


_FIX_THEN_TODO = re.compile(r"""(<div\b[^>]*\bclass="fix"[^>]*>(?:(?!</div>).)*</div>)(\s*)"""
                            r"""(<aside\b[^>]*\bclass="todo"[^>]*>.*?</aside>)""", re.S)


def keep_fix_with_todo(html: str) -> str:
    """Wrap a troubleshooting entry and the 3.0 line right after it in <div class="keep">, so that line never
    opens a page alone (same reason as keep_shot_with_todo). Idempotent."""
    return _FIX_THEN_TODO.sub(
        lambda m: m.group(0) if m.string[max(0, m.start() - 20):m.start()].endswith('<div class="keep">')
        else f'<div class="keep">{m.group(1)}{m.group(2)}{m.group(3)}</div>', html)


_MENU_PATH = re.compile(r'<bdi dir="ltr">([^<]*›[^<]*)</bdi>')


def mark_menu_paths(html: str) -> str:
    """Give every plain LTR <bdi> holding a menu path («Window › Extensions») the .path chip class."""
    return _MENU_PATH.sub(r'<bdi dir="ltr" class="path">\1</bdi>', html)


_CMD_BLOCK = re.compile(r"""(<div\b[^>]*\bclass\s*=\s*["'][^"']*\bcmd\b[^"']*["'][^>]*>)(.*?)(</div\s*>)""",
                        re.S | re.I)
CMD_MAX_TOKEN = 75  # IBM Plex Mono 10 pt ≈ 6 pt per character; the .cmd line is ≈ 462 pt wide


def _cmd_tokens(inner: str) -> list[str]:
    parts = re.split(r"(<[^>]+>)", inner)
    return [t for i, part in enumerate(parts) if i % 2 == 0 for t in re.findall(r"\S+", part)]


def nowrap_cmd_tokens(html: str) -> str:
    """Wrap every space-free token inside a .cmd block in <span class="nw"> (CSS: nowrap).

    A command then wraps only at its spaces — never after the hyphen of
    `example-clinic` or inside a path — so copying it from the PDF never puts a
    line break inside a token. Tags and entities are left intact; idempotent.
    """
    def block(m: re.Match) -> str:
        inner = re.sub(r'<span class="nw">(.*?)</span>', r"\1", m.group(2), flags=re.S)
        parts = re.split(r"(<[^>]+>)", inner)
        for i in range(0, len(parts), 2):
            parts[i] = re.sub(r"\S+", lambda t: f'<span class="nw">{t.group(0)}</span>', parts[i])
        return m.group(1) + "".join(parts) + m.group(3)

    return _CMD_BLOCK.sub(block, html)


def assemble(root: Path) -> str:
    """index.html with chapters/*.html (sorted by name) at <!--@chapters--> and the TOC at <!--@toc-->.

    Print-only markup is added here, never in the chapter sources: the chapter map after each
    chapter's first paragraph, the .ch-num wrapper of chapter numbers, .path chips and the
    no-wrap spans of command blocks.
    """
    root = Path(root)
    shell = (root / "index.html").read_text(encoding="utf-8")
    if "<!--@chapters-->" not in shell:
        raise ValueError("index.html has no <!--@chapters--> marker")
    parts = [p.read_text(encoding="utf-8").strip() for p in sorted((root / "chapters").glob("*.html"))]
    chapters = "\n\n".join(parts)
    printed = "\n\n".join(build_chapter_map(p) for p in parts)
    printed = mark_chapter_numbers(mark_menu_paths(keep_fix_with_todo(keep_shot_with_todo(nowrap_cmd_tokens(printed)))))
    html = shell.replace("<!--@chapters-->", printed, 1)
    toc = build_toc(chapters)
    if "<!--@toc-->" in html:
        html = html.replace("<!--@toc-->", toc, 1)
    else:
        html = re.sub(r'(<nav\b[^>]*\bid="toc"[^>]*>)', lambda m: m.group(1) + toc, html, count=1)
    return html


# ---------------------------------------------------------------- lint
_LATIN_RUN = re.compile(r"[A-Za-z0-9_\-./\\:@~%?=&#+]+(?: +[A-Za-z0-9_\-./\\:@~%?=&#+]+)*")
# A token (space-separated part of a Latin run) is "technical" — a command, path,
# file name, flag, id, version, time, URL or email — and must sit inside an LTR
# isolate (<bdi dir="ltr">, or any ancestor with dir="ltr") when it matches one of:
_TECHNICAL = [(why, re.compile(p)) for why, p in (
    ("path or URL", r"[/\\]"),
    ("email", r"@"),
    ("URL", r"(?i)^(https?|www\.)"),
    ("colon inside a token (time, drive, /whynot-cut:cmd)", r"\w:\w"),
    ("CLI flag", r"^--?[A-Za-z]"),
    ("underscore name", r"_"),
    ("hyphenated name", r"[A-Za-z0-9]-[A-Za-z0-9]"),
    ("file name / extension", r"[A-Za-z0-9_]\.[A-Za-z][A-Za-z0-9]{0,6}$|^\.[A-Za-z][A-Za-z0-9]{0,6}$"),
    ("version or dotted number", r"^v?\d+(\.\d+)+$"),
    ("id mixing letters and digits", r"^(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]+$"),
    ("the reel command", r"^reel$"),
)]
# Plain words never need isolation (Premiere Pro, After Effects, Claude, WhyNot Cut,
# YouTube, TikTok, Whisper, NVIDIA, macOS …): only technical tokens are flagged.
# Bare format/size names that contain digits or a hyphen are allowed as words:
_ALLOWED_TOKENS = {"MP4", "MP3", "M4A", "H.264", "H.265", "4K", "8K", "A4", "1080p", "2160p", "B-roll"}


def _technical_reason(run: str) -> str | None:
    for raw in run.split():
        token = raw.rstrip(".,;:!?")  # sentence punctuation after a word is not part of it
        if len(token) < 2 or token in _ALLOWED_TOKENS:
            continue
        for why, pattern in _TECHNICAL:
            if pattern.search(token):
                return why
    return None
_ARABIC_DIGIT = re.compile("[\u0660-\u0669\u06f0-\u06f9]")
_GATE = re.compile(r"\bGate [012]\b")
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
         "param", "source", "track", "wbr"}


# Phrases that only make sense in a draft (a placeholder or a "later" promise). A
# release build fails on them outside a .todo (inside one, the .todo itself fails).
# Matched on the text with Arabic diacritics removed, so «المخطَّط» = «المخطط».
DRAFT_PHRASES = [(label, re.compile(p)) for label, p in (
    ("قيد الإعداد", r"قيد الإعداد"),
    ("قيد البناء", r"قيد البناء"),
    # «المونتاج المخطَّط» is "the planned edit" (a real feature), not a draft promise
    ("المخطَّط", r"(?<!المونتاج )(?<!للمونتاج )المخطط"),
    ("حتى ذلك الحين", r"حتى ذلك الحين"),
    ("النسخة الحالية", r"النسخة الحالية"),
    ("مرحلة N", r"مرحلة \d"),
)]
_DIACRITICS = re.compile("[ً-ْٰ]")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


class _Linter(HTMLParser):
    def __init__(self, root: Path, release: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Path(root)
        self.release = release
        # each frame: (tag, ltr, in_bdi, in_ch16, skip, in_todo)
        self.stack: list[tuple[str, bool, bool, bool, bool, bool]] = [("#root", False, False, False, False, False)]
        self.ids: dict[str, int] = {}
        self.hrefs: list[str] = []
        self.problems: list[str] = []
        self.images: list[str] = []  # src of every <img>, in document order
        # open .shot-frame elements: [stack depth, has an <img>, text seen inside]
        self.frames: list[list] = []

    def _frame(self, tag: str, attrs: list[tuple[str, str | None]]):
        a = {k.lower(): (v or "") for k, v in attrs}
        classes = a.get("class", "").split()
        _, ltr, bdi, ch16, skip, todo = self.stack[-1]
        if "dir" in a:
            ltr = a["dir"].lower() == "ltr"
        if tag == "bdi":
            bdi = True
        if a.get("id") == "ch19":
            ch16 = True
        if tag in ("style", "script"):
            skip = True
        if "id" in a:
            self.ids[a["id"]] = self.ids.get(a["id"], 0) + 1
        if a.get("href", "").startswith("#"):
            self.hrefs.append(a["href"][1:])
        if "todo" in classes:
            todo = True
            if not a.get("data-phase", "").strip():
                self.problems.append('.todo without data-phase — name the phase that finalises it: '
                                     '<aside class="todo" data-phase="N">')
        if self.release and ("todo" in classes or "data-phase" in a):
            self.problems.append(f'release: placeholder left (<{tag} class="{a.get("class", "")}" '
                                 f'data-phase="{a.get("data-phase", "")}">) — write the final text or remove it')
        if tag == "img":
            self._image(a)
            for f in self.frames:
                f[1] = True
        return (tag, ltr, bdi, ch16, skip, todo), "shot-frame" in classes

    def _image(self, a: dict[str, str]) -> None:
        raw = self.get_starttag_text() or ""
        src = a.get("src", "")
        if not re.search(r'\ssrc="[^"]+"', raw):
            self.problems.append(f'<img> src must be a non-empty double-quoted path ( src="img/…" ): {raw[:100]}')
        if not src:
            return
        self.images.append(src)
        if _SCHEME.match(src) or src.startswith(("/", "\\")):
            self.problems.append(f'<img src="{src}"> must be a relative path to a file under guide-ar/ '
                                 "(no URL, data: or absolute path)")
        elif not (self.root / src).is_file():
            self.problems.append(f'<img src="{src}">: file not found (guide-ar/{src})')

    def handle_starttag(self, tag, attrs):
        frame, is_shot = self._frame(tag, attrs)
        if tag not in _VOID:
            self.stack.append(frame)
            if is_shot:
                self.frames.append([len(self.stack), False, []])

    def handle_startendtag(self, tag, attrs):
        self._frame(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        while self.frames and self.frames[-1][0] > len(self.stack):
            self._close_shot(self.frames.pop())

    def _close_shot(self, frame: list) -> None:
        if self.release and not frame[1]:
            text = re.sub(r"\s+", " ", " ".join(frame[2])).strip()[:70]
            self.problems.append(f"release: screenshot slot without an <img>: «{text}»")

    def close(self):
        super().close()
        while self.frames:
            self._close_shot(self.frames.pop())

    def handle_data(self, data):
        _, ltr, bdi, ch16, skip, todo = self.stack[-1]
        if skip or not data.strip():
            return
        for f in self.frames:
            f[2].append(data)
        snippet = re.sub(r"\s+", " ", data.strip())[:80]
        if not ltr:
            for m in _LATIN_RUN.finditer(data):
                run = m.group(0).strip()
                why = _technical_reason(run) if len(run) >= 2 else None
                if why:
                    self.problems.append(
                        f'unisolated LTR run «{run}» ({why}) — wrap it in <bdi dir="ltr">: «{snippet}»')
        if bdi and _ARABIC_DIGIT.search(data):
            self.problems.append(f"Arabic-Indic digit inside <bdi> (use 0-9): «{snippet}»")
        if not ch16 and _GATE.search(data):
            self.problems.append(f"internal gate name outside the glossary chapter (#ch19): «{snippet}»")
        if self.release and not todo:
            bare = _DIACRITICS.sub("", data)
            for label, pattern in DRAFT_PHRASES:
                if pattern.search(bare):
                    self.problems.append(f"release: draft phrase «{label}» outside a .todo: «{snippet}»")


def is_release(flag: bool = False) -> bool:
    """--release, or WNC_RELEASE set to 1/true/yes."""
    return flag or os.environ.get("WNC_RELEASE", "").strip().lower() in ("1", "true", "yes")


def lint(html: str, release: bool = False, root: Path | None = None) -> list[str]:
    """Problems that must be fixed before printing (empty list = clean).

    `root` is the folder <img src> paths are relative to (default: guide-ar/).
    `release` adds the release-only checks (placeholders, empty screenshot slots,
    draft phrases).
    """
    p = _Linter(ROOT if root is None else root, release)
    p.feed(html)
    p.close()
    problems = list(p.problems)
    for hid, n in p.ids.items():
        if n > 1:
            problems.append(f'duplicate id="{hid}" ({n}×)')
    for target in p.hrefs:
        if target not in p.ids:
            problems.append(f'broken link href="#{target}" (no element has id="{target}")')
    for m in _CMD_BLOCK.finditer(html):
        for token in _cmd_tokens(m.group(2)):
            if len(htmllib.unescape(token)) > CMD_MAX_TOKEN:
                problems.append(f"command token longer than {CMD_MAX_TOKEN} characters cannot wrap (only spaces "
                                f"break a .cmd line): «{htmllib.unescape(token)[:60]}…» — shorten it")
    if "logo-dark" in html:
        problems.append("logo-dark referenced — no dark logo variant may be used (white pages use the Syne wordmark)")
    seen: dict[str, str] = {}
    for _, hid, inner in toc_headings(html):
        title = plain_text(inner)
        if title in seen:
            problems.append(f"TOC headings #{seen[title]} and #{hid} share the text «{title}» (must be unique)")
        seen.setdefault(title, hid)
    return problems


# ---------------------------------------------------------------- developer words (Addendum G2)
# "No developer words anywhere a user sees." A word here fails the build in visible prose unless STYLE.md's
# «explained once» table lists it and its first use carries data-term-first. «hook» is NOT here: the guide uses it
# only as the editing term «البداية الجاذبة (hook)» (round 3 ruling). Matched as whole words, in any
# case (acronyms too: «json», «Api»; only PATH is case-sensitive); Arabic forms with any prefix (و ف ب ل ك ال) and
# suffix, diacritics ignored.
DEV_WORDS: tuple[str, ...] = (
    "token", "daemon", "JSON", "CLI", "API", "venv", "Python", "MCP", "PATH", "XML", "CEP",
    "repo", "commit", "cache", "flag", "session", "localhost", "stdout", "traceback",
    "توكن", "بايثون", "سكريبت", "سكربت", "سطر أوامر", "سطر الأوامر", "خطاف", "جلسة", "كاش",
    "جذر", "برمجيًا", "برمجي", "للمطوّر", "المطوّر", "مكتبات", "مسار", "امتداد", "كود", "أكواد",
    "script", "server", "config", "debug", "sha256", "ترمينال", "تيرمينال", "سيرفر", "جيسون",
)
# «لوج» is not listed: it matches «لوجو». PATH stays case-sensitive: «Copy as path» is a Windows menu label.
CASE_SENSITIVE_WORDS = ("PATH",)
# visible phrases that contain a listed word but are plain editor vocabulary
DEV_ALLOWED = ("التايم كود", "تايم كود", "بأكواد HEX", "أكواد ألوان HEX")  # timecode; designers' colour codes
STYLE_MD = ROOT / "STYLE.md"
_ARABIC_LETTER = "ء-ي"
_ARABIC_MARKS = re.compile("[ً-ْٰـ]")  # harakat, superscript alef, tatweel


def _word_regex(word: str) -> re.Pattern:
    word = _ARABIC_MARKS.sub("", word)
    if re.search(f"[{_ARABIC_LETTER}]", word):
        return re.compile(rf"(?<![{_ARABIC_LETTER}])[وفبلكا]{{0,4}}(?P<w>{re.escape(word)})")
    flags = 0 if word in CASE_SENSITIVE_WORDS else re.I
    return re.compile(rf"(?<![A-Za-z])(?P<w>{re.escape(word)})(?:e?s)?(?![A-Za-z])", flags)


_DEV_RES = [(w, _word_regex(w)) for w in DEV_WORDS]
_MENU_PATH_BDI = re.compile(r"<bdi\b[^>]*>[^<]*›[^<]*</bdi>")
# text markup inside a sentence: no word break at its edges (everything else, <code> included, is a boundary)
_INLINE_TAGS = {"a", "abbr", "b", "bdi", "bdo", "em", "i", "kbd", "mark", "s", "small", "span", "strong", "sub",
                "sup", "u"}


class _ProseParser(HTMLParser):
    """Visible text runs, each with the data-term-first keys of its open elements.

    Dropped: <code>, .cmd blocks, <style>/<script>, comments (team notes), and an LTR <bdi> holding only a menu
    path («Window › UXP Plugins»), which is a UI label the reader must match. Kept: headings, table cells,
    captions, plain <bdi> text («engine not installed») and the one-line .todo sentence.

    Every element that is not inline text markup (<p>, <td>, <li>, <h2>, <br>, a dropped <code> …) is a boundary:
    the text on either side is separated by a space, so «<p>x</p><p>JSON</p>» is «x JSON», not «xJSON» (round-3
    review I2: a glued word would slip past the whole-word match)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, frozenset]] = [("#root", False, frozenset())]
        self.runs: list[tuple[str, frozenset]] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        _, skip, keys = self.stack[-1]
        if tag in ("code", "style", "script") or "cmd" in a.get("class", "").split():
            skip = True
        if a.get("data-term-first", "").strip():
            keys = keys | {a["data-term-first"].strip()}
        if tag not in _INLINE_TAGS or skip != self.stack[-1][1]:
            self.runs.append((" ", self.stack[-1][2]))
        if tag not in _VOID:
            self.stack.append((tag, skip, keys))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0] == tag:
                closed_skip = self.stack[i][1]
                del self.stack[i:]
                if tag not in _INLINE_TAGS or closed_skip != self.stack[-1][1]:
                    self.runs.append((" ", self.stack[-1][2]))
                break

    def handle_data(self, data):
        _, skip, keys = self.stack[-1]
        if not skip:
            self.runs.append((data, keys))


def _prose_runs(html: str, menu_paths: bool = False) -> list[tuple[str, frozenset]]:
    """Visible text runs. Menu-path labels are dropped unless `menu_paths` (they are visible, but UI labels the
    reader must match, so the developer-word lint ignores them)."""
    p = _ProseParser()
    p.feed(html if menu_paths else _MENU_PATH_BDI.sub("", html))
    p.close()
    return [(_ARABIC_MARKS.sub("", text.replace("\xa0", " ")), keys) for text, keys in p.runs]


def visible_prose(html: str) -> str:
    """The text a reader sees, without code, command boxes, comments and menu-path labels (whitespace collapsed)."""
    return re.sub(r"\s+", " ", "".join(text for text, _ in _prose_runs(html))).strip()


_WAW_LATIN = re.compile(r"(?<![ء-ي])و(?=[A-Za-z])")


def waw_latin_problems(html: str) -> list[str]:
    """A «و» glued to Latin text in the visible prose («Premiere Pro وAfter Effects»). The font draws it like a Latin
    "g" there («After Effectsg Premiere Pro»), so repeat the preposition or reword: «في Premiere وفي After Effects».
    Code, command boxes, comments and attributes are not prose; a «و» before a <code> chip is fine (the chip is boxed)."""
    text = "".join(t for t, _ in _prose_runs(html, menu_paths=True))
    problems = []
    for m in _WAW_LATIN.finditer(text):
        around = re.sub(r"\s+", " ", text[max(0, m.start() - 25):m.end() + 25]).strip()
        problems.append(f"«و» glued to Latin text (it prints like a Latin g): repeat the preposition or reword: "
                        f"«{around}»")
    return problems


def explained_once_terms(style: Path = STYLE_MD) -> dict[str, tuple[str, ...]]:
    """STYLE.md «Explained once» table: term key (first backticked form of the first cell) -> every backticked form."""
    text = Path(style).read_text(encoding="utf-8")
    m = re.search(r"^## Explained once.*?(?=^## |\Z)", text, flags=re.S | re.M)
    terms: dict[str, tuple[str, ...]] = {}
    for line in (m.group(0).splitlines() if m else []):
        cells = line.strip().strip("|").split("|")
        forms = tuple(re.findall(r"`([^`]+)`", cells[0])) if line.lstrip().startswith("|") else ()
        if forms:
            terms[forms[0]] = forms
    return terms


def chapter_sources(root: Path = ROOT) -> str:
    """Every chapter source in reading order (the TOC and chapter maps would repeat headings ahead of their text)."""
    return "\n\n".join(p.read_text(encoding="utf-8") for p in sorted((Path(root) / "chapters").glob("*.html")))


def prose_sources(root: Path = ROOT) -> str:
    """What the prose lints read: the shell index.html (cover, back cover, any page placed there) and then every
    chapter in reading order."""
    return (Path(root) / "index.html").read_text(encoding="utf-8") + "\n\n" + chapter_sources(root)


def dev_word_problems(html: str, terms: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """Developer words in visible prose, and explained-once terms whose first use lacks data-term-first."""
    terms = explained_once_terms() if terms is None else terms
    runs = _prose_runs(html)
    text, starts, pos = "", [], 0
    for chunk, _ in runs:
        starts.append(pos)
        text += chunk
        pos += len(chunk)
    for phrase in DEV_ALLOWED:
        text = text.replace(phrase, " " * len(phrase))

    def keys_at(i: int) -> frozenset:
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= i:
                lo = mid
            else:
                hi = mid - 1
        return runs[lo][1] if runs else frozenset()

    def around(i: int, j: int) -> str:
        return re.sub(r"\s+", " ", text[max(0, i - 30):j + 30]).strip()

    problems, covered = [], []
    for key, forms in terms.items():
        hits = sorted((m.start("w"), m.end()) for f in forms for m in _word_regex(f).finditer(text))
        covered.extend(hits)
        if hits and key not in keys_at(hits[0][0]):
            problems.append(f"«{key}» is in STYLE.md's explained-once table: its first use needs "
                            f'data-term-first="{key}" and the explanation: «{around(*hits[0])}»')
    known = set(terms)
    for _, keys in runs:
        for key in keys - known:
            problems.append(f'data-term-first="{key}" names a term that is not in STYLE.md\'s explained-once table')
            known.add(key)
    for word, rx in _DEV_RES:
        for m in rx.finditer(text):
            if not any(s <= m.start("w") < e for s, e in covered):
                problems.append(f"developer word «{word}» in visible text (replace it, or add it to STYLE.md's "
                                f"explained-once table): «{around(m.start(), m.end())}»")
    return problems


# ---------------------------------------------------------------- macOS first (Addendum G11)
# "macOS is treated as the primary platform": every two-platform passage names macOS first. The guide writes its
# pairs in body prose, lead-ins, list items, table cells, captions and headings (round-3 audit Part C), so the lint
# reads every block element, not only dedicated platform blocks. App names count as their system. The text is the
# visible prose (no <code>, .cmd boxes, comments), but menu-path labels are kept: «Open with › Notepad» is a pair.
MAC_MARKS = re.compile(r"(?<![A-Za-z])(?:(?:macOS|Mac|Terminal|TextEdit|Finder|Apple Silicon)(?![A-Za-z])|Cmd\+)")
WIN_MARKS = re.compile(r"(?<![A-Za-z])(?:(?:Windows|PowerShell|Notepad|File Explorer)(?![A-Za-z])|Ctrl\+)")
_ORDER_BLOCKS = {"p", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "figure", "dt", "dd",
                 "caption", "summary"}
_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_SIBLING_BLOCKS = {"p", "li", "div", "figure", "ul", "ol", "table", "tbody", "tr", "aside", "dl", "dt", "dd",
                   "blockquote", "section", "pre"}


class _OrderNode:
    __slots__ = ("tag", "children")

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.children: list = []  # _OrderNode or str

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


class _OrderParser(HTMLParser):
    """An element tree of the visible text: <code>, .cmd boxes, <style>/<script> and comments are left out."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _OrderNode("#root")
        self.stack: list[tuple[_OrderNode, bool]] = [(self.root, False)]

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        parent, skip = self.stack[-1]
        if tag in ("code", "style", "script") or "cmd" in a.get("class", "").split():
            skip = True
        if tag in _VOID:
            return
        node = _OrderNode(tag)
        if not skip:
            parent.children.append(node)
        self.stack.append((node, skip))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        node, skip = self.stack[-1]
        if not skip:
            node.children.append(_ARABIC_MARKS.sub("", data.replace("\xa0", " ")))


def _platforms(text: str) -> tuple[int | None, int | None]:
    """(position of the first macOS mention, position of the first Windows mention), None when absent."""
    m, w = MAC_MARKS.search(text), WIN_MARKS.search(text)
    return (m.start() if m else None), (w.start() if w else None)


def platform_order_problems(html: str) -> list[str]:
    """Places that name Windows before macOS (G11). Empty list = clean.

    1. A block element (paragraph, list item, cell, caption, figure, heading) that names both systems names macOS
       first.
    2. A pair split over sibling elements: a Windows-only sibling followed by a macOS-only sibling in the same part
       (a heading starts a new part), e.g. two lead-ins with their command boxes, or two list items.
    3. Two sibling headings of the same level: a Windows-only one followed by a macOS-only one.
    """
    p = _OrderParser()
    p.feed(html)
    p.close()
    problems: list[str] = []

    def short(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()[:90]

    def only(node) -> str | None:
        mac, win = _platforms(node.text())
        if mac is not None and win is None:
            return "mac"
        if win is not None and mac is None:
            return "win"
        return None

    def walk(node: _OrderNode) -> None:
        if node.tag in _ORDER_BLOCKS:
            text = node.text()
            mac, win = _platforms(text)
            if mac is not None and win is not None and win < mac:
                problems.append(f"<{node.tag}> names Windows before macOS (G11: macOS first): «{short(text)}»")
        elements = [c for c in node.children if isinstance(c, _OrderNode)]
        win_only = None
        last_heading: dict[str, _OrderNode] = {}
        for child in elements:
            kind = only(child)
            if child.tag in _HEADINGS:
                win_only = None
                prev = last_heading.get(child.tag)
                if child.tag in ("h3", "h4", "h5", "h6") and prev is not None and only(prev) == "win" \
                        and kind == "mac":
                    problems.append(f"<{child.tag}> «{short(child.text())}» comes after the Windows heading "
                                    f"«{short(prev.text())}» (G11: the macOS heading first)")
                last_heading[child.tag] = child
                walk(child)
                continue
            if child.tag not in _SIBLING_BLOCKS:  # inline parts of one sentence are rule 1's business
                walk(child)
                continue
            if kind == "win" and win_only is None:
                win_only = child
            elif kind == "mac" and win_only is not None:
                problems.append(f"Windows part «{short(win_only.text())}» comes before the macOS part "
                                f"«{short(child.text())}» (G11: macOS first)")
                win_only = None
            walk(child)

    walk(p.root)
    return problems


# ---------------------------------------------------------------- troubleshooting shape (Addendum G2)
# "Every error says what happened, why, and the one button that fixes it." Each ch17 entry is
# <div class="fix"> with exactly one .fix-what, .fix-why and .fix-do <p>, in that order, each opening with its
# visible label; .fix-do is ONE action (one sentence); when it names both systems, macOS comes first (G11).
TROUBLESHOOTING_CHAPTER = "17-troubleshooting.html"
FIX_PARTS = (("fix-what", "اللي حصل"), ("fix-why", "ليه"), ("fix-do", "اعمل كده"))
_FIX_BLOCK = re.compile(r'<div\b[^>]*\bclass="fix"[^>]*>(.*?)</div>', re.S)
_FIX_PART = re.compile(r'<p\b[^>]*\bclass="(fix-[a-z]+)"[^>]*>(.*?)</p>', re.S)
_FIX_LABEL = re.compile(r'^\s*<span class="fix-label">(.*?)</span>', re.S)
# the label is an inline span: with no space after it the browser shapes its last letter into the next word
# («اللي حصل» + «رسالة» prints «حصا» + a joined «ـر», and the PDF text layer reads «حصلرسالة»)
_SENTENCE_END = re.compile(r"[.!؟](?=\s+\S)")


def fix_problems(html: str) -> list[str]:
    """Shape problems of the troubleshooting entries in `html` (a chapter source). Empty list = clean."""
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    problems = []
    if re.search(r"<t(?:able|r)\b", html):
        problems.append('troubleshooting: a table is left; write every entry as <div class="fix"> '
                        "(what happened / why / one action)")
    for block in _FIX_BLOCK.finditer(html):
        inner = block.group(1)
        parts = _FIX_PART.findall(inner)
        what = visible_prose(inner)[:60]
        if [c for c, _ in parts] != [c for c, _ in FIX_PARTS]:
            problems.append(f"troubleshooting entry needs exactly .fix-what, .fix-why, .fix-do in that order "
                            f"(has {[c for c, _ in parts]}): «{what}»")
            continue
        if _FIX_PART.sub("", inner).strip():
            problems.append(f"troubleshooting entry has content outside its three parts: «{what}»")
        for (cls, body), (_, label) in zip(parts, FIX_PARTS):
            m = _FIX_LABEL.match(body)
            if not m or plain_text(m.group(1)) != label:
                problems.append(f'«.{cls}» must open with <span class="fix-label">{label}</span>: «{what}»')
                continue
            if not body[m.end():m.end() + 1].isspace():
                problems.append(f'«.{cls}» needs a space right after its label (…</span> text), or the label and the '
                                f'first word are shaped as one Arabic word: «{what}»')
            text = visible_prose(body[m.end():])
            if not text:
                problems.append(f"«.{cls}» is empty: «{what}»")
            elif cls == "fix-do":
                if _SENTENCE_END.search(text) or re.search(r"<(?:br|ul|ol|li|div)\b", body):
                    problems.append(f"«اعمل كده» must be ONE action (one sentence): «{text[:80]}»")
                mac = re.search(r"(?<![A-Za-z])(?:Mac|macOS)(?![A-Za-z])", text)
                win = re.search(r"(?<![A-Za-z])Windows(?![A-Za-z])", text)
                if mac and win and win.start() < mac.start():
                    problems.append(f"«اعمل كده» names Windows before macOS (G11): «{text[:80]}»")
    return problems


# ---------------------------------------------------------------- TOC numbers
_PG = re.compile(r'(<span class="pg" data-for="([^"]+)">)([^<]*)(</span>)')          # TOC page
_MAP_PG = re.compile(r'(<span class="map-pg" data-for="([^"]+)">)([^<]*)(</span>)')  # chapter maps


def fill_toc(html: str, pages: dict[str, int]) -> str:
    """Write the page of each TOC and chapter-map target into its <span class="pg|map-pg" data-for=id>.

    `pages` maps heading text (as in the PDF outline) to a 1-based page; targets
    whose heading is not in `pages` get an empty number.
    """
    titles = {hid: plain_text(inner) for _, hid, inner in toc_headings(html)}

    def repl(m: re.Match) -> str:
        page = pages.get(titles.get(m.group(2), ""))
        return f"{m.group(1)}{'' if page is None else page}{m.group(4)}"

    return _MAP_PG.sub(repl, _PG.sub(repl, html))


def _numbers(html: str, pattern: re.Pattern) -> dict[str, int | None]:
    return {m.group(2): (int(m.group(3)) if m.group(3).strip().isdigit() else None)
            for m in pattern.finditer(html)}


def toc_numbers(html: str) -> dict[str, int | None]:
    """id -> number currently written in the TOC page (None when empty)."""
    return _numbers(html, _PG)


def map_numbers(html: str) -> dict[str, int | None]:
    """id -> number currently written in the chapter maps (None when empty)."""
    return _numbers(html, _MAP_PG)


def expected_numbers(html: str, pages: dict[str, int], current: dict[str, int | None] | None = None
                     ) -> dict[str, int | None]:
    """id -> outline page, for the ids of `current` (default: the TOC page entries)."""
    titles = {hid: plain_text(inner) for _, hid, inner in toc_headings(html)}
    return {hid: pages.get(titles.get(hid, "")) for hid in (toc_numbers(html) if current is None else current)}


# ---------------------------------------------------------------- browser / PDF
_MAC_APPS = (
    "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "Google Chrome.app/Contents/MacOS/Google Chrome",
    "Chromium.app/Contents/MacOS/Chromium",
)


def browser_candidates() -> list[Path]:
    """Install locations checked in order: Windows (Edge, Chrome), then macOS /Applications and ~/Applications."""
    candidates = []
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(Path(base) / "Microsoft/Edge/Application/msedge.exe")
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(Path(base) / "Google/Chrome/Application/chrome.exe")
    for app in _MAC_APPS:
        candidates.append(Path("/Applications") / app)
        try:
            candidates.append(Path.home() / "Applications" / app)  # per-user install
        except RuntimeError:  # no home directory
            pass
    return candidates


def find_browser() -> Path:
    """Edge, then Chrome. WNC_BROWSER (a path) wins."""
    env = os.environ.get("WNC_BROWSER")
    if env:
        if Path(env).exists():
            return Path(env)
        raise SystemExit(f"WNC_BROWSER points to a missing file: {env}")
    for c in browser_candidates():
        if c.exists():
            return c
    for name in ("msedge", "microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable",
                 "chrome", "chromium", "chromium-browser"):
        hit = shutil.which(name)
        if hit:
            return Path(hit)
    raise SystemExit("No Edge or Chrome found. Install one, or set WNC_BROWSER to the browser executable.")


def print_pdf(html_path: Path, pdf_path: Path, browser: Path) -> None:
    """Print html_path to pdf_path with a headless Chromium browser and a throwaway profile."""
    pdf_path = Path(pdf_path).resolve()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()
    profile = tempfile.mkdtemp(prefix="wnc-guide-browser-", dir=os.environ.get("WNC_BROWSER_TMP") or None)
    cmd = [
        str(browser), "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--disable-extensions", "--disable-sync", f"--user-data-dir={profile}",
        "--no-pdf-header-footer", "--generate-pdf-document-outline", "--virtual-time-budget=10000",
        f"--print-to-pdf={pdf_path}", Path(html_path).resolve().as_uri(),
    ]
    # own process group, so a hung browser and all its child processes can be killed
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
             else {"start_new_session": True})
    started = time.monotonic()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", **group)
        try:
            _, stderr = proc.communicate(timeout=PRINT_TIMEOUT)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            raise SystemExit(
                f"the browser did not finish printing within {PRINT_TIMEOUT} s and was stopped "
                f"({browser}). Close other Edge/Chrome windows started for printing and run the build "
                "again, or point WNC_BROWSER to another Edge/Chrome.") from None
        # Edge 155+ (new headless): the launcher exits 0 at once and a detached browser writes the PDF later
        if proc.returncode == 0 and not wait_for_file(
                pdf_path, max(1.0, PRINT_TIMEOUT - (time.monotonic() - started)), settle=PDF_SETTLE):
            raise SystemExit(f"the browser did not finish writing {pdf_path} within {PRINT_TIMEOUT} s ({browser}). "
                             "Close other Edge/Chrome windows started for printing and run the build again.")
    finally:
        _remove_profile(profile)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise SystemExit(f"browser did not write {pdf_path} (exit {proc.returncode}):\n{(stderr or '')[-2000:]}")


PDF_SETTLE = 2.0  # seconds a printed PDF must keep its size before it counts as written


def _ends_with_eof(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 1024))
            return b"%%EOF" in fh.read()
    except OSError:
        return False


def wait_for_file(path: Path, timeout: float, settle: float = PDF_SETTLE, poll: float = 0.5) -> bool:
    """True once `path` exists, is not empty, ends with the PDF end marker (%%EOF) and its size has not changed for
    `settle` seconds; False after `timeout` seconds. A detached browser writes the PDF after its launcher has exited,
    so a file that is still growing, or stopped half-written, never counts as done."""
    path, deadline = Path(path), time.monotonic() + timeout
    last, since = -1, None
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size if path.exists() else -1
        except OSError:  # the browser is replacing the file right now
            size = -1
        if size > 0 and size == last:
            since = since or time.monotonic()
            if time.monotonic() - since >= settle and _ends_with_eof(path):
                return True
        else:
            last, since = size, None
        time.sleep(poll)
    return False


def _remove_profile(profile: str, tries: int = 20) -> None:
    """Delete the throwaway browser profile; a detached browser may hold it for a few seconds after printing."""
    for _ in range(tries):
        shutil.rmtree(profile, ignore_errors=True)
        if not os.path.exists(profile):
            return
        time.sleep(0.5)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop the browser and every child process it started."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        else:
            import signal

            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
        proc.communicate(timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def outline_pages(pdf_path: Path) -> dict[str, int]:
    """Bookmark title -> 1-based page, from the PDF outline (first occurrence wins)."""
    reader = _pypdf().PdfReader(str(pdf_path))
    pages: dict[str, int] = {}

    def walk(items) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item)
                continue
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:  # noqa: BLE001 - an unresolvable bookmark is just skipped
                continue
            pages.setdefault(plain_text(str(item.title)), page)

    walk(reader.outline)
    return pages


def _chars_key(text: str) -> list[str]:
    return sorted(_BIDI_CONTROLS.sub("", re.sub(r"\s+", "", text)))


def _num(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


# A bookmark whose /XYZ top is this close to the bottom edge of its page is not a
# heading: it is the sliver of a heading that starts on the NEXT page (see below).
SLIVER_TOP_PT = 72.0  # bottom page margin is 22 mm = 62.4 pt


def match_outline(marks: list[dict], heads: list[tuple[int, str]], page_heights: list[float]) -> list[dict]:
    """Pair Chrome's bookmarks with the HTML headings they came from, by document order.

    `marks`: one dict per bookmark in outline order: title, page (0-based), top,
    left, zoom (None when not an /XYZ destination). `heads`: (level, logical text)
    of every h1–h6 in document order. Titles are NOT trusted: Chrome writes the
    runs of a mixed-direction title in layout order, and when a heading lands at
    the top of a page Edge may also paint the hamza of أ/إ as a sliver at the
    bottom of the previous page, then write the title twice and point the bookmark
    at that sliver. Such a bookmark (top within SLIVER_TOP_PT of the page bottom)
    is moved to the top of the next page. Raises ValueError when the bookmark
    count differs from the heading count or the pages go backwards.
    """
    if len(marks) != len(heads):
        raise ValueError(f"PDF outline has {len(marks)} bookmarks but the HTML has {len(heads)} headings")
    out, last_page = [], 0
    for mark, (level, title) in zip(marks, heads):
        page, top, notes = mark["page"], mark.get("top"), []
        if _chars_key(str(mark["title"])) != _chars_key(title):
            notes.append(f"Edge title «{mark['title']}» garbled")
        if top is not None and top <= SLIVER_TOP_PT and page + 1 < len(page_heights):
            page, top = page + 1, page_heights[page + 1]
            notes.append("moved from a page-break sliver to the next page")
        if page < last_page:
            raise ValueError(f"bookmark for «{title}» is on page {page + 1}, before the previous heading "
                             f"(page {last_page + 1}): outline and headings are out of order")
        last_page = page
        out.append({"level": level, "title": title, "page": page, "top": top,
                    "left": mark.get("left"), "zoom": mark.get("zoom"), "notes": notes})
    return out


def pdf_metadata(source_digest: str | None = None, release: bool = False) -> dict[str, str]:
    """Document info written into the guide PDF (the subject marks a draft build)."""
    meta = {"/Title": PDF_TITLE, "/Author": PDF_AUTHOR,
            "/Subject": PDF_SUBJECT if release else PDF_SUBJECT_DRAFT}
    if source_digest:
        meta[HASH_KEY] = source_digest
    return meta


def fix_outline(pdf_path: Path, html: str, metadata: dict[str, str] | None = None) -> int:
    """Rebuild the outline Chrome generated: logical heading titles, Chrome's positions.

    Chrome's --generate-pdf-document-outline gives the right positions but
    unreliable titles (see match_outline). Every bookmark is re-added with its
    heading's logical text, nested by heading level. The PDF opens with the
    bookmarks panel (/UseOutlines); `metadata` (see pdf_metadata) is merged into
    the document info. Returns the number of bookmarks; prints a note for each
    title or page it had to repair.
    """
    import io

    pypdf = _pypdf()
    from pypdf.generic import Fit

    pdf_path = Path(pdf_path)
    reader = pypdf.PdfReader(io.BytesIO(pdf_path.read_bytes()))
    flat = []

    def walk(items) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item)
            else:
                flat.append(item)

    walk(reader.outline)
    marks = []
    for item in flat:
        xyz = str(item.get("/Type", "")) == "/XYZ" or getattr(item, "typ", None) == "/XYZ"
        marks.append({"title": str(item.title), "page": reader.get_destination_page_number(item),
                      "top": _num(item.top) if xyz else None, "left": _num(item.left) if xyz else None,
                      "zoom": _num(item.zoom) if xyz else None})
    heads = [(int(tag[1]), plain_text(inner)) for tag, _, inner in all_headings(html)]
    heads = [h for h in heads if h[1]]
    heights = [float(pg.mediabox.top) for pg in reader.pages]
    try:
        entries = match_outline(marks, heads, heights)
    except ValueError as exc:
        raise SystemExit(f"cannot rebuild the PDF bookmarks: {exc}") from None

    writer = pypdf.PdfWriter(clone_from=reader)
    if "/Outlines" in writer._root_object:
        del writer._root_object["/Outlines"]
    parents: dict[int, object] = {}
    for e in entries:
        for note in e["notes"]:
            _say(f"  outline: «{e['title']}» (page {e['page'] + 1}): {note}")
        level = e["level"]
        parent = next((parents[lv] for lv in range(level - 1, 0, -1) if lv in parents), None)
        fit = Fit.xyz(left=e["left"], top=e["top"], zoom=e["zoom"]) if e["top"] is not None else Fit.fit()
        parents[level] = writer.add_outline_item(e["title"], e["page"], parent=parent, fit=fit)
        for lv in [lv for lv in parents if lv > level]:
            del parents[lv]
    writer.page_mode = "/UseOutlines"
    if metadata:
        writer.add_metadata(metadata)
    with open(pdf_path, "wb") as fh:
        writer.write(fh)
    return len(entries)


def page_count(pdf_path: Path) -> int:
    return len(_pypdf().PdfReader(str(pdf_path)).pages)


_RELATIVE_URL = re.compile(r"""(\s(?:src|href)\s*=\s*(["']))(?!#|[a-zA-Z][a-zA-Z0-9+.-]*:|/|\\|["'])""",
                           re.I)


def relocate(html: str, prefix: str = "../") -> str:
    """Prefix relative src/href (stylesheet, logo, screenshots) so the document works from
    guide-ar/.build/; anchors, URLs and absolute paths are untouched."""
    return _RELATIVE_URL.sub(lambda m: m.group(1) + prefix, html)


_IMG_SRC = re.compile(r"""<img\b[^>]*?\ssrc\s*=\s*["']([^"']+)["']""", re.I)


def source_hash(root: Path = ROOT, html: str | None = None) -> str:
    """SHA-256 over what the PDF is printed from: the assembled HTML, styles.css and every local <img>.

    Written into the PDF (HASH_KEY) so a test can tell when the committed PDF is
    older than its sources.
    """
    root = Path(root)
    html = assemble(root) if html is None else html
    h = hashlib.sha256()
    h.update(html.replace("\r\n", "\n").encode("utf-8"))
    h.update(b"\0styles.css\0")
    h.update((root / "styles.css").read_bytes().replace(b"\r\n", b"\n"))
    for src in sorted(set(_IMG_SRC.findall(html))):
        path = root / src
        if not _SCHEME.match(src) and path.is_file():
            data = path.read_bytes()
            if path.suffix.lower() == ".svg":  # text: same hash with LF or CRLF checkouts
                data = data.replace(b"\r\n", b"\n")
            h.update(b"\0" + src.encode("utf-8") + b"\0")
            h.update(data)
    return h.hexdigest()


# ---------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Arabic WhyNot Cut guide PDF.")
    ap.add_argument("--out", type=Path, help="write the PDF only here (default: whynot-cut/docs/ and dist/)")
    ap.add_argument("--release", action="store_true",
                    help="release build: also fail on placeholders (.todo), empty screenshot slots and draft "
                         "phrases (same as WNC_RELEASE=1)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    release = is_release(args.release)
    _pypdf()  # fail early with the venv hint

    # a failed build must never leave last run's artefacts for the PDF tests to pass on
    build_dir = ROOT / ".build"
    for stale in ("test.pdf", "toc.json", "pass.pdf", "guide.html"):
        (build_dir / stale).unlink(missing_ok=True)

    html = assemble(ROOT)
    sources = chapter_sources(ROOT)
    prose = prose_sources(ROOT)  # the shell index.html as well (cover, back cover)
    problems = (lint(html, release=release) + dev_word_problems(prose) + waw_latin_problems(prose)
                + platform_order_problems(sources))
    troubleshooting = ROOT / "chapters" / TROUBLESHOOTING_CHAPTER
    if troubleshooting.is_file():
        problems += fix_problems(troubleshooting.read_text(encoding="utf-8"))
    if problems:
        print(f"LINT{' (release)' if release else ''}: {len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        return 1
    print(f"lint{' (release)' if release else ' (draft)'}: clean ({len(toc_headings(html))} TOC entries)")
    meta = pdf_metadata(source_hash(ROOT, html), release)

    build_dir.mkdir(exist_ok=True)
    guide_html = build_dir / "guide.html"
    pass_pdf = build_dir / "pass.pdf"
    browser = find_browser()
    print(f"browser: {browser}")

    current = fill_toc(html, {})
    final_pages: dict[str, int] = {}
    for attempt in range(1, MAX_PASSES + 1):
        guide_html.write_text(relocate(current), encoding="utf-8")
        print_pdf(guide_html, pass_pdf, browser)
        if not _pypdf().PdfReader(str(pass_pdf)).outline:
            print("ERROR: the printed PDF has no outline (bookmarks); the browser ignored "
                  "--generate-pdf-document-outline. Use a newer Edge/Chrome or set WNC_BROWSER.")
            return 1
        fix_outline(pass_pdf, current, meta)
        final_pages = outline_pages(pass_pdf)
        want = expected_numbers(current, final_pages)
        map_have = map_numbers(current)
        map_want = expected_numbers(current, final_pages, map_have)
        missing = [hid for hid, n in {**want, **map_want}.items() if n is None]
        if missing:
            print("ERROR: TOC / chapter-map headings not found in the PDF outline:", ", ".join(missing))
            return 1
        have = toc_numbers(current)
        done = have == want and map_have == map_want
        print(f"pass {attempt}: {page_count(pass_pdf)} pages, TOC and chapter maps {'match' if done else 'updated'}")
        if done:
            break
        current = fill_toc(html, final_pages)
    else:
        print(f"ERROR: TOC / chapter-map numbers still differ from the outline after {MAX_PASSES} passes:")
        for have_now in (toc_numbers(current), map_numbers(current)):
            for hid, n in expected_numbers(current, final_pages, have_now).items():
                if have_now.get(hid) != n:
                    print(f"  - #{hid}: printed {have_now.get(hid)} vs outline {n}")
        return 1

    titles = {hid: plain_text(inner) for _, hid, inner in toc_headings(current)}
    toc = [{"id": hid, "title": titles[hid], "page": n} for hid, n in toc_numbers(current).items()]
    (build_dir / "toc.json").write_text(json.dumps(toc, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copyfile(pass_pdf, build_dir / "test.pdf")

    outputs = [args.out] if args.out else list(DEFAULT_OUTPUTS)
    for out in outputs:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pass_pdf, out)
        print(f"wrote {out}")
    print(f"pages: {page_count(pass_pdf)} ({'release' if release else 'draft'}; source hash {meta[HASH_KEY][:12]}…)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
