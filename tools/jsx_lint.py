#!/usr/bin/env python3
"""Lint for the ExtendScript files (`wnc_*.jsx`) that the signed CEP bridge runs inside Premiere and After Effects.

Rules (Addendum A2, last paragraph; the ExtendScript notes of the Hush, Kalam and Tidy PRDs):
  ascii    source is ASCII only (strings and comments too; write non-ASCII as \\uXXXX escapes)
  es3      ES3 only: no .map( .forEach( .filter( .reduce( .reduceRight( .some( .every( .trim(, no =>, let, const,
           template literals, class
  namespace  every top-level `var`, `function` and bare assignment is the file's namespace (or NAMESPACE_x), so the
           libraries share ExtendScript's one global scope without collisions. `var X = X || {};` followed by
           `X.thing = ...` is the bridge pattern and passes. ALLOWED_GLOBALS lists the few extra helpers
  ternary  a `?:` nested in another `?:` operand is parenthesised: `a ? x : (b ? y : z)` (ExtendScript evaluates the
           unparenthesised form wrongly)

Strings, regex literals and comments are blanked before the code rules run, so `"use .map( here"`, `// const x` and
`/=>/` never trigger them. Standard library only (runs on the engine runtime).

    python tools/jsx_lint.py <files...>     exit 1 and `file:line rule message` per finding
    python tools/jsx_lint.py                every whynot-cut/templates/**/wnc_*.jsx and adobe/**/wnc_*.jsx
    python tools/jsx_lint.py --report-only <files...>   per-file and per-rule counts, always exit 0 (size of a cleanup)
    python tools/jsx_lint.py --namespace wnc_hush.jsx=WNC_HUSH --allow helperName <files...>
Exit: 0 clean, 1 findings, 2 usage or I/O error.
"""
import argparse
import re
import sys
from collections import Counter, namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- configuration -------------------------------------------------------------------------------------------------
# Allowed namespace per file. Default: the file stem upper-cased (wnc_hush.jsx -> WNC_HUSH, wnc_tidy.jsx -> WNC_TIDY,
# wnc_kalam.jsx -> WNC_KALAM, wnc_audio.jsx -> WNC_AUDIO). The core libraries keep their short historical names.
CORE_NAMESPACES = {
    "wnc_ppro_lib.jsx": "WNCPP",
    "wnc_ae_bridge.jsx": "WNCAE",
    "wnc_ae_lib.jsx": "WNC",
    "wnc_motion_lib.jsx": "WNCM",
    "wnc_ps_lib.jsx": "WNCPS",
}

# D18 (3.0 only, removed in 3.1): the legacy 3.1.1 bridge evaluates `NHPP.run(...)` / `NHAE.run(...)` after the
# library, so these two files may also declare that one old name, as `var NHPP = WNCPP;` / `var NHAE = WNCAE;`.
LEGACY_ALIASES = {
    "wnc_ppro_lib.jsx": frozenset({"NHPP"}),
    "wnc_ae_bridge.jsx": frozenset({"NHAE"}),
}

# Top-level helpers a library needs besides its namespace object (none today). Everything else is reported.
# The AE bridge's own folder is WNCAE_HERE (inside the WNCAE namespace), read at TOP LEVEL because the libraries it
# $.evalFile()s must run at top level too (inside a function their globals would stay local: "NHM is undefined", seen
# live in AE 26.5 with the pre-D18 names).
ALLOWED_GLOBALS = frozenset()

RULES = ("ascii", "es3", "namespace", "ternary")

Finding = namedtuple("Finding", "path line rule message")
Finding.__str__ = lambda f: "%s:%d %s %s" % (f.path, f.line, f.rule, f.message)

_REGEX_AFTER_WORD = frozenset("return typeof instanceof in of new delete void throw case do else".split())
_STATEMENT_WORDS = frozenset("var return if for while switch break continue throw try do".split())
_ES3_METHODS = ("map", "forEach", "filter", "reduce", "reduceRight", "some", "every", "trim")

_TOKEN = re.compile(r"[A-Za-z_$][\w$]*|\d[\w.]*|=>|\S")
_ES3_METHOD = re.compile(r"\.\s*(%s)\s*\(" % "|".join(_ES3_METHODS))
_ES3_ARROW = re.compile(r"=>")
_ES3_KEYWORD = re.compile(r"(?<![\w$.])(let|const)\s+(?=[A-Za-z_$\[{])|(?<![\w$.])(class)\s+(?=[A-Za-z_$])")


def namespace_for(path, overrides=None):
    """The namespace a file may declare: an explicit override, the core map, else the file stem upper-cased."""
    name = Path(str(path)).name
    if overrides and name in overrides:
        return overrides[name]
    if name in CORE_NAMESPACES:
        return CORE_NAMESPACES[name]
    return re.sub(r"\W", "_", Path(name).stem).upper()


def default_files(root=ROOT):
    """Every whynot-cut/templates/**/wnc_*.jsx and adobe/**/wnc_*.jsx (node_modules excluded)."""
    root = Path(root)
    found = set()
    for sub in ("whynot-cut/templates", "adobe"):
        base = root / sub
        if base.is_dir():
            found.update(p for p in base.rglob("wnc_*.jsx") if "node_modules" not in p.parts)
    return sorted(found)


# --- stripping ----------------------------------------------------------------------------------------------------
def strip(src):
    """Blank comments, string contents, regex literals and `#` directive lines; offsets and newlines are preserved.

    Returns (stripped, template_offsets); the offsets are where a backtick template literal starts (an ES3 error).
    """
    out = list(src)
    n = len(src)
    templates = []

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    regex_ok = True       # can a `/` here start a regex literal (after an operator, not after an operand)
    line_blank = True     # only whitespace so far on this line
    while i < n:
        c = src[i]
        if c == "\n":
            line_blank = True
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        if c == "#" and line_blank:                       # ExtendScript #target / #include / #targetengine
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        line_blank = False
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c in "'\"":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1 if j < n and src[j] == c else j
            regex_ok = False
        elif c == "`":
            templates.append(i)
            j = i + 1
            while j < n and src[j] != "`":
                j += 2 if src[j] == "\\" else 1
            blank(i + 1, j)
            i = j + 1
            regex_ok = False
        elif c == "/":
            j = i + 1
            in_class = False
            closed = False
            if regex_ok:
                while j < n and src[j] != "\n":
                    ch = src[j]
                    if ch == "\\":
                        j += 2
                        continue
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        closed = True
                        break
                    j += 1
            if closed:
                k = j + 1
                while k < n and (src[k].isalpha() or src[k] == "_"):
                    k += 1
                blank(i + 1, k)
                i = k
                regex_ok = False
            else:
                i += 1
                regex_ok = True
        elif c.isalpha() or c in "_$":
            m = re.compile(r"[A-Za-z_$][\w$]*").match(src, i)
            word = m.group(0) if m else c
            regex_ok = word in _REGEX_AFTER_WORD
            i += max(len(word), 1)
        elif c.isdigit():
            m = re.compile(r"[\w.]+").match(src, i)
            i = m.end()
            regex_ok = False
        else:
            regex_ok = c not in ")]"
            i += 1
    return "".join(out), templates


# --- rules ---------------------------------------------------------------------------------------------------------
def _line_of(starts, off):
    """1-based line of a character offset (starts = offsets of every line start)."""
    lo, hi = 0, len(starts)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if starts[mid] <= off:
            lo = mid
        else:
            hi = mid
    return lo + 1


def _check_ascii(src, path, out):
    for n, line in enumerate(src.split("\n"), 1):
        for col, ch in enumerate(line, 1):
            if ord(ch) > 127:
                out.append(Finding(path, n, "ascii", "non-ASCII character U+%04X at column %d (write it as a \\u escape)"
                                   % (ord(ch), col)))
                break


def _check_es3(code, templates, starts, path, out):
    for m in _ES3_METHOD.finditer(code):
        out.append(Finding(path, _line_of(starts, m.start()), "es3", ".%s() is not ES3 (use a for loop)" % m.group(1)))
    for m in _ES3_ARROW.finditer(code):
        out.append(Finding(path, _line_of(starts, m.start()), "es3", "arrow function (=>) is not ES3"))
    for m in _ES3_KEYWORD.finditer(code):
        word = m.group(1) or m.group(2)
        out.append(Finding(path, _line_of(starts, m.start()), "es3", "'%s' is not ES3" % word))
    for off in templates:
        out.append(Finding(path, _line_of(starts, off), "es3", "template literal is not ES3 (concatenate strings)"))


class _Frame:
    __slots__ = ("kind", "func", "params", "tern")

    def __init__(self, kind, func=False, params=False):
        self.kind = kind          # '(' '[' '{' or None for the file itself
        self.func = func          # a function body
        self.params = params      # a function's parameter list
        self.tern = []            # open conditionals of this nesting level: 'then' / 'else'


def _declared_names(toks, i):
    """Names declared by the `var` at toks[i]: the identifier after `var` and after each top-level comma."""
    names, depth, want = [], 0, True
    j = i + 1
    while j < len(toks):
        t, off = toks[j]
        if t in "([{":
            depth += 1
        elif t in ")]}":
            depth -= 1
            if depth < 0:
                break
        elif depth == 0:
            if t == ";" or t in ("var", "function", "in"):
                break
            if t == ",":
                want = True
            elif want and re.match(r"[A-Za-z_$]", t):
                names.append((t, off))
                want = False
        j += 1
    return names


def _check_code(code, starts, path, namespace, allowed, out):
    toks = [(m.group(0), m.start()) for m in _TOKEN.finditer(code)]
    frames = [_Frame(None)]
    prev = prev2 = None
    closed_params = False
    ok = lambda name: (namespace is None or name == namespace or name.startswith(namespace + "_")
                       or name in ALLOWED_GLOBALS or name in allowed)

    def flag_global(name, off, what):
        if not ok(name):
            out.append(Finding(path, _line_of(starts, off), "namespace",
                               "top-level %s '%s' is not in namespace %s (declare it as %s.%s or inside a function)"
                               % (what, name, namespace, namespace, name)))

    for i, (t, off) in enumerate(toks):
        was_params, closed_params = closed_params, False
        top = frames[-1]
        in_func = any(f.func for f in frames)
        nxt = toks[i + 1][0] if i + 1 < len(toks) else None
        nxt2 = toks[i + 2][0] if i + 2 < len(toks) else None

        if t in "([{" and len(t) == 1:
            fr = _Frame(t)
            if t == "(" and (prev == "function" or (prev2 == "function" and re.match(r"[A-Za-z_$]", prev or ""))):
                fr.params = True
            if t == "{" and was_params:
                fr.func = True
            frames.append(fr)
        elif t in ")]}" and len(t) == 1:
            if len(frames) > 1:
                fr = frames.pop()
                closed_params = (t == ")" and fr.params)
        elif t == "?":
            if top.tern:
                out.append(Finding(path, _line_of(starts, off), "ternary",
                                   "nested conditional is not parenthesised: write a ? x : (b ? y : z)"))
            top.tern.append("then")
        elif t == ":":
            if top.tern and top.tern[-1] == "then":
                top.tern[-1] = "else"
        elif t in (",", ";") or t in _STATEMENT_WORDS:
            del top.tern[:]

        if namespace is not None and not in_func:
            if t == "var":
                for name, noff in _declared_names(toks, i):
                    flag_global(name, noff, "var")
            elif t == "function" and prev in (None, ";", "}", "{") and nxt and re.match(r"[A-Za-z_$]", nxt):
                flag_global(nxt, toks[i + 1][1], "function")
            elif (re.match(r"[A-Za-z_$]", t) and prev in (None, ";", "}", "{") and nxt == "=" and nxt2 != "="
                  and t not in _STATEMENT_WORDS and all(f.kind in (None, "{") for f in frames)):
                flag_global(t, off, "assignment")
        prev2, prev = prev, t


def lint_source(src, namespace, filename="<source>", allowed=()):
    """Lint ExtendScript source text. `namespace` None skips the namespace rule. Returns Findings sorted by line."""
    allowed = frozenset(allowed)
    out = []
    _check_ascii(src, filename, out)
    code, templates = strip(src)
    starts = [0] + [m.end() for m in re.finditer("\n", src)]
    _check_es3(code, templates, starts, filename, out)
    _check_code(code, starts, filename, namespace, allowed, out)
    return sorted(out, key=lambda f: (f.line, RULES.index(f.rule)))


def lint_file(path, namespace=None, overrides=None, allowed=(), display=None):
    path = Path(path)
    text = path.read_bytes().decode("utf-8", errors="replace")
    ns = namespace or namespace_for(path, overrides)
    allowed = frozenset(allowed) | LEGACY_ALIASES.get(path.name, frozenset())
    return lint_source(text, ns, display or str(path), allowed)


# --- command line ------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="jsx_lint", description="Lint ExtendScript (wnc_*.jsx): ASCII, ES3, namespaced "
                                 "globals, parenthesised nested conditionals.")
    ap.add_argument("files", nargs="*", help="files to lint (default: every wnc_*.jsx under whynot-cut/templates and adobe)")
    ap.add_argument("--namespace", action="append", default=[], metavar="FILE=NS",
                    help="allowed namespace for a file name (repeatable); default derives from the file name")
    ap.add_argument("--allow", action="append", default=[], metavar="NAME", help="extra allowed top-level name (repeatable)")
    ap.add_argument("--report-only", action="store_true", help="print counts per file and rule, always exit 0")
    args = ap.parse_args(argv)

    overrides = {}
    for item in args.namespace:
        name, sep, ns = item.partition("=")
        if not sep or not name or not ns:
            print("jsx_lint: --namespace expects FILE=NS, got %r" % item, file=sys.stderr)
            return 2
        overrides[name] = ns

    if args.files:
        targets = [(Path(f), f) for f in args.files]
    else:
        targets = [(p, p.relative_to(ROOT).as_posix()) for p in default_files(ROOT)]

    findings, per_file = [], []
    for path, shown in targets:
        if not path.is_file():
            print("jsx_lint: not a file: %s" % shown, file=sys.stderr)
            return 2
        got = lint_file(path, overrides=overrides, allowed=args.allow, display=shown)
        per_file.append((shown, got))
        findings += got

    for f in findings:
        print(f)
    if args.report_only:
        by_rule = Counter(f.rule for f in findings)
        for shown, got in per_file:
            print("report: %s: %d" % (shown, len(got)))
        print("report: %d file(s), %d finding(s) (%s)" % (
            len(per_file), len(findings), ", ".join("%s=%d" % (r, by_rule.get(r, 0)) for r in RULES)))
        return 0
    if findings:
        print("jsx_lint: %d finding(s) in %d file(s)" % (len(findings), len({f.path for f in findings})), file=sys.stderr)
        return 1
    if not per_file:
        print("jsx_lint: no wnc_*.jsx files found (nothing to lint)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
