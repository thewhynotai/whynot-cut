"""Static CSP / safety scan of the installer UI sources (installer/app/ui/**).

The runtime CSP test proves what the browser blocked; this scan stops the patterns before they reach a page:
inline <script> and <style>, style="" and on*="" attributes, javascript: URLs, HTML string sinks (innerHTML,
outerHTML, insertAdjacentHTML, document.write), eval and new Function, string timers, on* property handlers,
setAttribute("style"/"on…"), and any remote URL (http, https, ws, protocol-relative) in any file.
"""
from __future__ import annotations

import pathlib
import re

# a namespace name is an identifier, never fetched: the SVG namespace is the one the DOM needs (createElementNS)
NAMESPACES = {"http://www.w3.org/2000/svg"}
URL = re.compile(r"""\b(?:https?|wss?|ftp)://[^\s"'`)<>]*""", re.I)
RULES_ALL = [
    ("remote URL", URL),
    ("protocol-relative URL", re.compile(r"""(?:src|href|url\()\s*=?\s*["']?//""", re.I)),
]
RULES_HTML = [
    ("inline <script>", re.compile(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>", re.I)),
    ("inline <style>", re.compile(r"<style\b", re.I)),
    ("style attribute", re.compile(r"<[^>]*\sstyle\s*=", re.I)),
    ("inline event handler", re.compile(r"<[^>]*\son[a-z]+\s*=", re.I)),
    ("javascript: URL", re.compile(r"javascript\s*:", re.I)),
    ("iframe", re.compile(r"<iframe\b", re.I)),
]
RULES_JS = [
    ("innerHTML", re.compile(r"\binnerHTML\b")),
    ("outerHTML", re.compile(r"\bouterHTML\b")),
    ("insertAdjacentHTML", re.compile(r"\binsertAdjacentHTML\b")),
    ("document.write", re.compile(r"\bdocument\s*\.\s*write(?:ln)?\b")),
    ("eval", re.compile(r"(?<![\w.])eval\s*\(")),
    ("new Function", re.compile(r"\bnew\s+Function\b|(?<![\w.])Function\s*\(")),
    ("string timer", re.compile(r"\bset(?:Timeout|Interval)\s*\(\s*[\"'`]")),
    ("on* property handler", re.compile(r"\.\s*on[a-z]+\s*=(?!=)")),
    ("setAttribute style/on*", re.compile(r"setAttribute\s*\(\s*[\"'`](?:style|on[a-z]*)[\"'`]", re.I)),
    ("javascript: URL", re.compile(r"javascript\s*:", re.I)),
    ("iframe", re.compile(r"""createElement\(\s*["'`]iframe|<iframe\b""", re.I)),
]
RULES_CSS = [
    ("CSS expression()", re.compile(r"expression\s*\(", re.I)),
    ("javascript: URL", re.compile(r"javascript\s*:", re.I)),
]


def scan_text(name: str, text: str) -> list[str]:
    """Problems in one file's text, as 'name:line: rule'."""
    suffix = pathlib.PurePath(name).suffix.lower()
    rules = list(RULES_ALL)
    rules += {".html": RULES_HTML, ".htm": RULES_HTML, ".js": RULES_JS, ".mjs": RULES_JS, ".css": RULES_CSS}.get(suffix, [])
    out = []
    for rule, rx in rules:
        for m in rx.finditer(text):
            if rx is URL and m.group(0) in NAMESPACES:
                continue
            line = text.count("\n", 0, m.start()) + 1
            out.append(f"{name}:{line}: {rule}")
    return out


def scan_tree(root: pathlib.Path) -> list[str]:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".html", ".htm", ".js", ".mjs", ".css", ".json"}:
            out += scan_text(p.relative_to(root).as_posix(), p.read_text(encoding="utf-8"))
    return out
