# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""A small, forgiving CSS reader for the brand extractors (Addendum J3): declarations with their selector and the
at-rules around them (@media, @supports, @layer, @container nest; @keyframes, @page and other at-rules are skipped),
@import targets, url() references and @font-face blocks.

It is a tokenizer, not a validator: comments are removed, strings are kept whole (a bad string ends at the line
end, as in the CSS syntax spec), `;` `{` `}` inside parentheses don't split, and malformed input (unclosed braces,
strings, comments or parentheses) ends the current block at the end of the text. Nesting deeper than DEPTH_MAX is
counted and skipped, so no input can raise.
"""
from __future__ import annotations

import re

DEPTH_MAX = 64
_NEST = {"@media", "@supports", "@layer", "@container", "@document", "@scope", "@-moz-document"}
_SPECIAL = re.compile(r"[/\"'\\(){};]")
_URL = re.compile(r"url\(\s*(?:\"((?:[^\"\\]|\\.)*)\"|'((?:[^'\\]|\\.)*)'|([^)\s\"'(]*))\s*\)", re.I)
_WS = re.compile(r"\s+")


def _split_important(value: str) -> tuple:
    """(value, important) with plain string steps (a regex anchored at `$` is quadratic on long runs of spaces)."""
    t = value.rstrip()
    if t[-9:].lower() == "important":
        head = t[:-9].rstrip()
        if head.endswith("!"):
            return head[:-1].strip(), True
    return value.strip(), False


class Sheet:
    def __init__(self):
        self.rules = []            # {"selector", "decls": [(prop, value, important)], "at": [at-rule preludes]}
        self.imports = []          # (url, media)
        self.urls = []             # (url, property)
        self.font_faces = []       # {"family", "weight", "style", "src": [(url, format)], "unicode_range"}


def _tokens(text: str) -> list:
    """[("t", text) | ("{",) | ("}",) | (";",)] with comments removed."""
    out, buf, i, n, paren = [], [], 0, len(text), 0
    while i < n:
        m = _SPECIAL.search(text, i)
        if not m:
            buf.append(text[i:])
            break
        j = m.start()
        if j > i:
            buf.append(text[i:j])
        c = text[j]
        if c == "/":
            if text.startswith("/*", j):
                k = text.find("*/", j + 2)
                i = n if k < 0 else k + 2
                buf.append(" ")
                continue
            buf.append(c)
            i = j + 1
            continue
        if c in "\"'":
            k = j + 1
            while k < n:
                ch = text[k]
                if ch == "\\":
                    k += 2
                    continue
                if ch == c:
                    k += 1
                    break
                if ch == "\n":
                    break
                k += 1
            buf.append(text[j:min(k, n)])
            i = k
            continue
        if c == "\\":
            buf.append(text[j:j + 2])
            i = j + 2
            continue
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        elif paren == 0:
            out.append(("t", "".join(buf)))
            buf = []
            out.append((c,))
            i = j + 1
            continue
        buf.append(c)
        i = j + 1
    out.append(("t", "".join(buf)))
    return out


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
    return s.replace("\\\"", "\"").replace("\\'", "'")


def _decl(text: str):
    if ":" not in text:
        return None
    prop, value = text.split(":", 1)
    prop = prop.strip()
    if not prop or " " in prop or "{" in prop:
        return None
    if not prop.startswith("--"):
        prop = prop.lower()
    value, important = _split_important(value)
    value = _WS.sub(" ", value)
    return prop, value, important


def urls_in(value: str) -> list:
    out = []
    for m in _URL.finditer(value or ""):
        u = (m.group(1) if m.group(1) is not None else m.group(2) if m.group(2) is not None else m.group(3) or "")
        u = u.strip().replace("\\\"", "\"").replace("\\'", "'")
        if u and not u.lower().startswith("data:"):
            out.append(u)
    return out


def _import(text: str):
    rest = text.strip()[len("@import"):].strip()
    m = _URL.match(rest)
    if m:
        url = urls_in(m.group(0))
        media = rest[m.end():].strip()
    elif rest and rest[0] in "\"'":
        q = rest[0]
        k = rest.find(q, 1)
        if k < 0:
            return None
        url, media = [rest[1:k]], rest[k + 1:].strip()
    else:
        return None
    return (url[0], _WS.sub(" ", media)) if url else None


def _split_top(value: str, sep: str = ",") -> list:
    parts, depth, cur, q = [], 0, [], None
    for ch in value:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
            continue
        if ch in "\"'":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _font_face(decls: list) -> dict:
    d = {p: v for p, v, _ in decls}
    src = []
    for part in _split_top(d.get("src", "")):
        u = urls_in(part)
        if not u:
            continue
        fm = re.search(r"format\(\s*[\"']?([\w.-]+)", part, re.I)
        src.append((u[0], fm.group(1).lower() if fm else ""))
    return {"family": _unquote(d.get("font-family", "")), "weight": d.get("font-weight", ""),
            "style": d.get("font-style", ""), "src": src, "unicode_range": d.get("unicode-range", "").replace(" ", "")}


def parse_css(text: str) -> Sheet:
    sheet = Sheet()
    stack = []                    # ["at", prelude] | ["rule", selector, decls] | ["font", decls] | ["skip"]
    overflow = 0
    pending = ""

    def at_context():
        return [s[1] for s in stack if s[0] == "at"]

    def add_decl(entry, raw):
        d = _decl(raw)
        if d:
            (entry[2] if entry[0] == "rule" else entry[1]).append(d)

    def close(entry):
        if entry[0] == "rule" and entry[2]:
            sheet.rules.append({"selector": entry[1], "decls": entry[2], "at": entry[3]})
            for prop, value, _imp in entry[2]:
                for u in urls_in(value):
                    sheet.urls.append((u, prop))
        elif entry[0] == "font":
            sheet.font_faces.append(_font_face(entry[1]))

    text = (text or "").replace("<!--", " ").replace("-->", " ")      # old-style comment wrappers (CDO / CDC)
    for tok in _tokens(text):
        kind = tok[0]
        if kind == "t":
            pending += tok[1]
            continue
        top = stack[-1] if stack else None
        if kind == ";":
            if top is not None and top[0] in ("rule", "font") and not overflow:
                add_decl(top, pending)
            elif (top is None or top[0] == "at") and pending.strip().lower().startswith("@import"):
                imp = _import(pending)
                if imp:
                    sheet.imports.append(imp)
            pending = ""
        elif kind == "{":
            prelude = _WS.sub(" ", pending).strip()
            pending = ""
            if overflow or len(stack) >= DEPTH_MAX:
                overflow += 1
                continue
            if top is not None and top[0] in ("rule", "font", "skip"):
                stack.append(["skip"])
            elif prelude.startswith("@"):
                name = prelude.split(None, 1)[0].lower()
                if name in _NEST:
                    stack.append(["at", prelude])
                elif name == "@font-face":
                    stack.append(["font", []])
                else:
                    stack.append(["skip"])
            else:
                stack.append(["rule", prelude, [], at_context()])
        else:                     # "}"
            if overflow:
                overflow -= 1
                pending = ""
                continue
            if top is not None and top[0] in ("rule", "font"):
                add_decl(top, pending)
            pending = ""
            if stack:
                close(stack.pop())
    while stack:                  # unclosed blocks at the end of the text: keep what was read
        top = stack.pop()
        if top[0] in ("rule", "font") and pending.strip():
            add_decl(top, pending)
            pending = ""
        close(top)
    return sheet
