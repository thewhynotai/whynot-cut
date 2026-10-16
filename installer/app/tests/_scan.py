"""Static CSP / safety scan of the installer UI sources (installer/app/ui/**): a TRIPWIRE, not the control.

The real controls are the browser's: the CSP (script-src 'self' with no 'unsafe-inline' / 'unsafe-eval', object-src,
base-uri, form-action) and Trusted Types (require-trusted-types-for 'script'; trusted-types 'none'), under which every
HTML or script sink (innerHTML, outerHTML, insertAdjacentHTML, document.write, srcdoc, createContextualFragment,
DOMParser, setHTMLUnsafe, script.src/text, eval-like timers) throws, however it is spelled; tests/test_ui_shell.py
proves it with a computed property name. Navigation and new windows are not governed by CSP: the app host denies them
with ET1-17's on_navigation lock and its new-window refusal.

This scan stops the patterns before they reach a page: inline <script> and <style>, style="" and on*="" attributes,
javascript: URLs (also with a tab or newline inside), HTML string sinks and HTML parsers, computed "inner"+"HTML",
Reflect.set, eval and Function (also through .constructor), string timers, on* property handlers (also computed),
setAttribute("style"/"on…") and setAttributeNS, document.execCommand, iframes and srcdoc, script elements, <use>
references, an http-equiv meta, CSS url() and cssText built in script, navigation (location =, location[…], .href =,
.assign, .replace) and window.open, dynamic import of anything but a relative path, and any remote URL (http, https,
ws, protocol-relative) in any file.

Known misses: examples, not exhaustive. Text cannot tell these apart from harmless code, so the scan does not try:
- a computed property write: `el[k] = s`, a template key (el[`inner${…}`]), a built key `el[k + "HTML"]`;
- an indirect global: `globalThis[name](s)`, `window[...]`, and a wrapped constructor `new (Function)(s)`;
- a timer given a variable `setTimeout(fnOrString)`, and `el.setAttribute(k, v)` with a computed name (text.js h()
  refuses on*, style and formaction names at run time);
- elements built through h() that the CSP governs: form (form-action 'none'), base (base-uri 'none'), object and
  embed (object-src 'none').
The backstop for every one of them is the browser: Trusted Types plus the CSP (script, HTML sinks, eval, forms, base,
plugins). The ones that navigate (location[...], a meta refresh made in script) are ET1-17's on_navigation lock.
"""
from __future__ import annotations

import pathlib
import re

# a namespace name is an identifier, never fetched: the SVG namespace is the one the DOM needs (createElementNS)
NAMESPACES = {"http://www.w3.org/2000/svg"}
URL = re.compile(r"""\b(?:https?|wss?|ftp)://[^\s"'`)<>]*""", re.I)
# "javascript:" also with whitespace or an escaped tab/newline/C0 inside (the URL parser drops them)
JS_URL = re.compile(r"""j\s*a\s*v\s*a(?:\s|\\[tnr]|\\u00[01][0-9a-f]|\\x[01][0-9a-f])*s\s*c\s*r\s*i\s*p\s*t\s*:""", re.I)
RULES_ALL = [
    ("remote URL", URL),
    ("protocol-relative URL", re.compile(r"""(?:src|href|url\()\s*=?\s*["']?//""", re.I)),
]
RULES_HTML = [
    ("inline <script>", re.compile(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>", re.I)),
    ("inline <style>", re.compile(r"<style\b", re.I)),
    ("style attribute", re.compile(r"<[^>]*\sstyle\s*=", re.I)),
    ("inline event handler", re.compile(r"<[^>]*\son[a-z]+\s*=", re.I)),
    ("javascript: URL", JS_URL),
    ("iframe", re.compile(r"<iframe\b", re.I)),
    ("srcdoc", re.compile(r"\bsrcdoc\b", re.I)),
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
    ("javascript: URL", JS_URL),
    ("iframe", re.compile(r"""createElement\(\s*["'`]iframe|<iframe\b|\(\s*["'`]iframe["'`]""", re.I)),
    ("computed HTML sink", re.compile(r"""["'`](?:inner|outer)["'`]\s*\+""")),
    ("Reflect.set", re.compile(r"\bReflect\s*\.\s*set\b")),
    ("HTML parser", re.compile(r"\b(?:createContextualFragment|DOMParser|parseFromString|setHTMLUnsafe|parseHTMLUnsafe)\b")),
    ("srcdoc", re.compile(r"\bsrcdoc\b")),
    ("navigation", re.compile(r"\blocation\s*=(?!=)|\blocation\s*\.\s*(?:href\s*=(?!=)|assign\b|replace\b)")),
    ("window.open", re.compile(r"\bwindow\s*\.\s*open\b|(?<![\w.])open\s*\(")),
    (".constructor()", re.compile(r"\.\s*constructor\s*\(")),
    ("dynamic import", re.compile(r"""\bimport\s*\(\s*(?!["'`]\.\.?/)""")),
    ("computed on* handler", re.compile(r"""\[\s*["'`]on[a-z]*["'`]\s*[\]+]""")),
    ("<use> reference", re.compile(r"""["'`]use["'`]\s*[,)]""")),
    ("CSS url() in script", re.compile(r"""["'`]\s*url\(""")),
    ("cssText", re.compile(r"\bcssText\b")),
    ("script element", re.compile(r"""createElement(?:NS)?\s*\([^)]*["'`]script["'`]""")),
    ("navigation (computed)", re.compile(r"\blocation\s*\[")),
    ("setAttributeNS", re.compile(r"\bsetAttributeNS\b")),
    ("execCommand", re.compile(r"\bexecCommand\b")),
    ("http-equiv", re.compile(r"http-equiv", re.I)),
]
RULES_CSS = [
    ("CSS expression()", re.compile(r"expression\s*\(", re.I)),
    ("javascript: URL", JS_URL),
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
