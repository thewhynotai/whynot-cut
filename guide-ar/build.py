#!/usr/bin/env python3
"""Build the Arabic WhyNot Cut user guide PDF.

    ~/.whynot-cut/venv/Scripts/python.exe guide-ar/build.py [--out PATH]

Pipeline: assemble (index.html + chapters/*.html, TOC from h1.ch-title / h2[id])
-> lint (bidi isolation, digits, anchors, ids, forbidden words) -> print with
headless Edge/Chrome -> read the PDF outline -> fill the TOC page numbers ->
print again -> check TOC numbers == outline pages -> copy.

Outputs: whynot-cut/docs/WhyNot-Cut-Guide-AR.pdf and dist/WhyNot-Cut-Guide-AR.pdf
(or only --out PATH), plus guide-ar/.build/{guide.html,test.pdf,toc.json} for the
tests in guide-ar/tests. Exit 1 on lint problems or a TOC/outline mismatch.

Standard library only, except pypdf (reading the PDF outline), which is loaded
lazily: run with the WhyNot Cut engine venv python, which has it.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PDF_NAME = "WhyNot-Cut-Guide-AR.pdf"
DEFAULT_OUTPUTS = (REPO / "whynot-cut" / "docs" / PDF_NAME, REPO / "dist" / PDF_NAME)
MAX_PASSES = 4

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
_BIDI_CONTROLS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def plain_text(fragment: str) -> str:
    """Visible text of an HTML fragment, whitespace collapsed (matches PDF outline titles)."""
    text = re.sub(r"<[^>]+>", "", fragment)
    text = htmllib.unescape(text)
    text = _BIDI_CONTROLS.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


_ATTR = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')
_HEADING = re.compile(r"<(h1|h2)\b([^>]*)>(.*?)</\1\s*>", re.S | re.I)


def _attrs(raw: str) -> dict[str, str]:
    return {k.lower(): v for k, v in _ATTR.findall(raw)}


def toc_headings(html: str) -> list[tuple[str, str, str]]:
    """(level, id, inner_html) for every h1.ch-title and h2[id], in document order."""
    found = []
    for m in _HEADING.finditer(html):
        level, attrs, inner = m.group(1).lower(), _attrs(m.group(2)), m.group(3)
        hid = attrs.get("id")
        if not hid:
            continue
        if level == "h1" and "ch-title" not in attrs.get("class", "").split():
            continue
        found.append((level, hid, inner))
    return found


# ---------------------------------------------------------------- assemble
def _toc_label(inner: str) -> str:
    """Heading inner HTML for a TOC entry: keep <bdi>/<code>, drop ids and nested links."""
    inner = re.sub(r'\s+id="[^"]*"', "", inner)
    inner = re.sub(r"</?a\b[^>]*>", "", inner)
    return re.sub(r"\s+", " ", inner).strip()


def build_toc(chapters_html: str) -> str:
    items = []
    for level, hid, inner in toc_headings(chapters_html):
        items.append(
            f'<li class="toc-{level}"><a href="#{hid}"><span>{_toc_label(inner)}</span>'
            f'<span class="pg" data-for="{hid}"></span></a></li>'
        )
    return '<ol class="toc-list">\n' + "\n".join(items) + "\n</ol>"


def assemble(root: Path) -> str:
    """index.html with chapters/*.html (sorted by name) at <!--@chapters--> and the TOC at <!--@toc-->."""
    root = Path(root)
    shell = (root / "index.html").read_text(encoding="utf-8")
    if "<!--@chapters-->" not in shell:
        raise ValueError("index.html has no <!--@chapters--> marker")
    parts = [p.read_text(encoding="utf-8").strip() for p in sorted((root / "chapters").glob("*.html"))]
    chapters = "\n\n".join(parts)
    html = shell.replace("<!--@chapters-->", chapters, 1)
    toc = build_toc(chapters)
    if "<!--@toc-->" in html:
        html = html.replace("<!--@toc-->", toc, 1)
    else:
        html = re.sub(r'(<nav\b[^>]*\bid="toc"[^>]*>)', lambda m: m.group(1) + toc, html, count=1)
    return html


# ---------------------------------------------------------------- lint
_LATIN_RUN = re.compile(r"[A-Za-z0-9_\-./\\:@~%?=&#+]+(?: +[A-Za-z0-9_\-./\\:@~%?=&#+]+)*")
_NEEDS_ISOLATION = [re.compile(p) for p in (
    r"/whynot-cut:", r"\breel ", r"\\", r"/", r"\d\d:\d\d", r"@", r"\.md\b", r"\.mp4\b", r"http",
)]
_ARABIC_DIGIT = re.compile("[\u0660-\u0669\u06f0-\u06f9]")
_GATE = re.compile(r"\bGate [012]\b")
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
         "param", "source", "track", "wbr"}


class _Linter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # each frame: (tag, ltr, in_bdi, in_ch16, skip)
        self.stack: list[tuple[str, bool, bool, bool, bool]] = [("#root", False, False, False, False)]
        self.ids: dict[str, int] = {}
        self.hrefs: list[str] = []
        self.problems: list[str] = []

    def _frame(self, tag: str, attrs: list[tuple[str, str | None]]):
        a = {k.lower(): (v or "") for k, v in attrs}
        _, ltr, bdi, ch16, skip = self.stack[-1]
        if "dir" in a:
            ltr = a["dir"].lower() == "ltr"
        if tag == "bdi":
            bdi = True
        if a.get("id") == "ch16":
            ch16 = True
        if tag in ("style", "script"):
            skip = True
        if "id" in a:
            self.ids[a["id"]] = self.ids.get(a["id"], 0) + 1
        if a.get("href", "").startswith("#"):
            self.hrefs.append(a["href"][1:])
        return (tag, ltr, bdi, ch16, skip)

    def handle_starttag(self, tag, attrs):
        frame = self._frame(tag, attrs)
        if tag not in _VOID:
            self.stack.append(frame)

    def handle_startendtag(self, tag, attrs):
        self._frame(tag, attrs)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        _, ltr, bdi, ch16, skip = self.stack[-1]
        if skip or not data.strip():
            return
        snippet = re.sub(r"\s+", " ", data.strip())[:80]
        if not ltr:
            for m in _LATIN_RUN.finditer(data):
                run = m.group(0).strip()
                if len(run) >= 2 and any(p.search(run) for p in _NEEDS_ISOLATION):
                    self.problems.append(f'unisolated LTR run «{run}» — wrap it in <bdi dir="ltr">: «{snippet}»')
        if bdi and _ARABIC_DIGIT.search(data):
            self.problems.append(f"Arabic-Indic digit inside <bdi> (use 0-9): «{snippet}»")
        if not ch16 and _GATE.search(data):
            self.problems.append(f"internal gate name outside the glossary chapter (#ch16): «{snippet}»")


def lint(html: str) -> list[str]:
    """Problems that must be fixed before printing (empty list = clean)."""
    p = _Linter()
    p.feed(html)
    p.close()
    problems = list(p.problems)
    for hid, n in p.ids.items():
        if n > 1:
            problems.append(f'duplicate id="{hid}" ({n}×)')
    for target in p.hrefs:
        if target not in p.ids:
            problems.append(f'broken link href="#{target}" (no element has id="{target}")')
    if "logo-dark" in html:
        problems.append("logo-dark referenced — no dark logo variant may be used (white pages use the Syne wordmark)")
    seen: dict[str, str] = {}
    for _, hid, inner in toc_headings(html):
        title = plain_text(inner)
        if title in seen:
            problems.append(f"TOC headings #{seen[title]} and #{hid} share the text «{title}» (must be unique)")
        seen.setdefault(title, hid)
    return problems


# ---------------------------------------------------------------- TOC numbers
_PG = re.compile(r'(<span class="pg" data-for="([^"]+)">)([^<]*)(</span>)')


def fill_toc(html: str, pages: dict[str, int]) -> str:
    """Write the page of each TOC target into its <span class="pg" data-for=id>.

    `pages` maps heading text (as in the PDF outline) to a 1-based page; targets
    whose heading is not in `pages` get an empty number.
    """
    titles = {hid: plain_text(inner) for _, hid, inner in toc_headings(html)}

    def repl(m: re.Match) -> str:
        page = pages.get(titles.get(m.group(2), ""))
        return f"{m.group(1)}{'' if page is None else page}{m.group(4)}"

    return _PG.sub(repl, html)


def toc_numbers(html: str) -> dict[str, int | None]:
    """id -> number currently written in the TOC (None when empty)."""
    return {m.group(2): (int(m.group(3)) if m.group(3).strip().isdigit() else None) for m in _PG.finditer(html)}


def expected_numbers(html: str, pages: dict[str, int]) -> dict[str, int | None]:
    titles = {hid: plain_text(inner) for _, hid, inner in toc_headings(html)}
    return {hid: pages.get(titles.get(hid, "")) for hid in toc_numbers(html)}


# ---------------------------------------------------------------- browser / PDF
def find_browser() -> Path:
    """Edge, then Chrome. WNC_BROWSER (a path) wins."""
    env = os.environ.get("WNC_BROWSER")
    if env:
        if Path(env).exists():
            return Path(env)
        raise SystemExit(f"WNC_BROWSER points to a missing file: {env}")
    candidates = []
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(Path(base) / "Microsoft/Edge/Application/msedge.exe")
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(Path(base) / "Google/Chrome/Application/chrome.exe")
    candidates += [
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]
    for c in candidates:
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
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise SystemExit(f"browser did not write {pdf_path} (exit {res.returncode}):\n{res.stderr[-2000:]}")


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


_ANY_HEADING = re.compile(r"<(h[1-6])\b[^>]*>(.*?)</\1\s*>", re.S | re.I)


def _chars_key(text: str) -> list[str]:
    return sorted(_BIDI_CONTROLS.sub("", re.sub(r"\s+", "", text)))


def _num(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def fix_outline(pdf_path: Path, html: str) -> int:
    """Rewrite the bookmark titles Chrome generated, keeping its pages and positions.

    Chrome's --generate-pdf-document-outline emits a heading's text runs in layout
    order, so a mixed-direction title such as «1 · مقدمة» comes out as « · مقدمة1».
    Every bookmark is matched (in document order) with the h1–h6 it came from — the
    two must contain exactly the same characters — and re-added with the heading's
    logical text, nested by heading level. Returns the number of bookmarks.
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
    heads = [(int(m.group(1)[1]), plain_text(m.group(2))) for m in _ANY_HEADING.finditer(html)]
    heads = [h for h in heads if h[1]]
    if len(flat) != len(heads):
        raise SystemExit(f"PDF outline has {len(flat)} bookmarks but the HTML has {len(heads)} headings")

    writer = pypdf.PdfWriter(clone_from=reader)
    if "/Outlines" in writer._root_object:
        del writer._root_object["/Outlines"]
    parents: dict[int, object] = {}
    for item, (level, title) in zip(flat, heads):
        if _chars_key(str(item.title)) != _chars_key(title):
            raise SystemExit(f"bookmark «{item.title}» does not match heading «{title}» (document order)")
        page = reader.get_destination_page_number(item)
        parent = next((parents[lv] for lv in range(level - 1, 0, -1) if lv in parents), None)
        if str(item.get("/Type", "")) == "/XYZ" or getattr(item, "typ", None) == "/XYZ":
            fit = Fit.xyz(left=_num(item.left), top=_num(item.top), zoom=_num(item.zoom))
        else:
            fit = Fit.fit()
        parents[level] = writer.add_outline_item(title, page, parent=parent, fit=fit)
        for lv in [lv for lv in parents if lv > level]:
            del parents[lv]
    with open(pdf_path, "wb") as fh:
        writer.write(fh)
    return len(flat)


def page_count(pdf_path: Path) -> int:
    return len(_pypdf().PdfReader(str(pdf_path)).pages)


_RELATIVE_URL = re.compile(r'(\s(?:src|href)=")(?!#|[a-zA-Z][a-zA-Z0-9+.-]*:|/)')


def relocate(html: str, prefix: str = "../") -> str:
    """Prefix relative src/href so the document works from guide-ar/.build/ (anchors untouched)."""
    return _RELATIVE_URL.sub(lambda m: m.group(1) + prefix, html)


# ---------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Arabic WhyNot Cut guide PDF.")
    ap.add_argument("--out", type=Path, help="write the PDF only here (default: whynot-cut/docs/ and dist/)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    _pypdf()  # fail early with the venv hint

    html = assemble(ROOT)
    problems = lint(html)
    if problems:
        print(f"LINT: {len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        return 1
    print(f"lint: clean ({len(toc_headings(html))} TOC entries)")

    build_dir = ROOT / ".build"
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
        fix_outline(pass_pdf, current)
        final_pages = outline_pages(pass_pdf)
        want = expected_numbers(current, final_pages)
        missing = [hid for hid, n in want.items() if n is None]
        if missing:
            print("ERROR: TOC headings not found in the PDF outline:", ", ".join(missing))
            return 1
        have = toc_numbers(current)
        print(f"pass {attempt}: {page_count(pass_pdf)} pages, TOC {'matches' if have == want else 'updated'}")
        if have == want:
            break
        current = fill_toc(html, final_pages)
    else:
        print(f"ERROR: TOC numbers still differ from the outline after {MAX_PASSES} passes:")
        for hid, n in expected_numbers(current, final_pages).items():
            if toc_numbers(current).get(hid) != n:
                print(f"  - #{hid}: TOC {toc_numbers(current).get(hid)} vs outline {n}")
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
    print(f"pages: {page_count(pass_pdf)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
