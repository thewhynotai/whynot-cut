#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Gate 4 check (BL-20): is any test green only because it is skipped "for now"? Dev tool, not shipped in the plugin.

    python tools/skip_audit.py                          every skip site under whynot-cut/tests, dated ones fail
    python tools/skip_audit.py --since v3.0.0-p3.1      gate mode: a NEW unknown skip since the tag fails too
    options: --root DIR (the repo top), --all (list every site, not only the failing ones), --json (machine report)

Reads the test files (AST, never runs one) and finds every skip site: unittest skip / skipIf / skipUnless /
expectedFailure, self.skipTest, raise SkipTest, pytest skip / skipif / xfail, and a module-level skip decorator
assigned to a name. Each site is classed:
  dated          a dated-skip marker ("dated skip", a name with _PENDING, "waits for ... patch", "until ... lands",
                 an ISO date in the reason) in the reason, the condition, a comment on the skip or 3 lines above it, or
                 the block that sets the condition's name (the `except ImportError:` shape of 61feeb2). Always a FAIL.
  platform/tool  the condition is about the machine (platform, a tool, a file in a checkout, free RAM, an opt-in env var),
                 and neither the reason nor a comment on the skip (or 3 lines above) says "for now" ("yet", "not built",
                 "executor", "patch" ...): that wording makes it unknown, since a file that "is not built yet" is a temporary skip.
  unknown        the rest. Listed; a FAIL only for a line added since --since.
The classes are a helper, not a proof: the executor reads the list. A moved or reformatted old skip shows as added
since the tag, so it is listed as unknown (known limit; moves are not diffed). Aliased imports (`import unittest as u`)
are not followed.

Exit: 0 clean | 1 at least one FAIL | 2 the check could not run (a file that does not parse, git missing, the tag
missing, --root not the top of a repo, uncommitted test changes in --since mode). Read-only: files are opened "rb" and
git runs only `rev-parse`, `diff` and `status`.
Stdlib only.
"""
import argparse
import ast
import collections
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from pathlib import Path

TESTS = "whynot-cut/tests"
FIXTURES = TESTS + "/fixtures"      # the tool's own planted skips live here: excluded
CLASSES = ("dated", "platform/tool", "unknown")

Site = collections.namedtuple("Site", "file line end kind cls reason cond")

CALL_KINDS = {
    "unittest.expectedFailure": "expectedFailure", "expectedFailure": "expectedFailure",
    "unittest.skip": "skip", "skip": "skip", "pytest.skip": "skip", "pytest.mark.skip": "skip", "mark.skip": "skip",
    "unittest.skipIf": "skipIf", "skipIf": "skipIf", "unittest.skipUnless": "skipUnless", "skipUnless": "skipUnless",
    "pytest.mark.skipif": "skipif", "mark.skipif": "skipif", "pytest.mark.xfail": "xfail", "mark.xfail": "xfail",
    "pytest.importorskip": "importorskip", "SkipTest": "SkipTest", "unittest.SkipTest": "SkipTest",
}
BARE_KINDS = {"unittest.expectedFailure": "expectedFailure", "expectedFailure": "expectedFailure",
              "pytest.mark.skip": "skip", "mark.skip": "skip", "pytest.mark.xfail": "xfail", "mark.xfail": "xfail"}
CONDITION_KINDS = ("skipIf", "skipUnless", "skipif", "xfail")

DATED_RE = re.compile(r"dated skip|\bwaits? for\b[^\n]*\bpatch\b|\buntil\b[^\n]*\blands?\b", re.I)
DATED_NAME_RE = re.compile(r"_PENDING")       # a name: case matters (a prose "pending" is not a marker)
ISO_DATE_RE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
TEMPORARY_RE = re.compile(r"\byet\b|\bnot (?:built|applied|ported|generated|committed)|\bexecutor\b|\bpatch\b", re.I)
PLATFORM_RE = re.compile(
    r"sys\.platform|\bos\.name\b|platform\.system|\bwindows\b|\bwin32\b|\bdarwin\b|\bmacos\b|\bIS_(?:WIN|MAC)\w*"
    r"|shutil\.which|\bNODE\b|\w*AVAILABLE\b|\bHAVE_\w+|\w*_PRESENT\b|\.is_file\(\)|\.is_dir\(\)|\.exists\(\)"
    r"|os\.environ|\bgetenv\b|\bfree_?(?:ram|disk)|\bavailable_ram|\bram\b|\bsymlinks?\b|\bjunctions?\b", re.I)
# the reason is prose: only words that say "this machine" count there (not "available", "node", "windows", "ram")
REASON_PLATFORM_RE = re.compile(r"\bsymlinks?\b|\bjunctions?\b|\bfree RAM\b|\bMB free\b", re.I)


class NotRun(Exception):
    """The check could not run: exit 2, never a clean answer."""


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _strings(nodes):
    return [n.value for t in nodes for n in ast.walk(t) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _names(nodes):
    out = set()
    for t in nodes:
        for n in ast.walk(t):
            if isinstance(n, ast.Name):
                out.add(n.id)
    return out


def _collect_assigns(body, handler, out):
    for st in body:
        if isinstance(st, ast.Assign):
            for t in st.targets:
                if isinstance(t, ast.Name):
                    out.setdefault(t.id, []).append((st.value, st, handler))
        elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
            out.setdefault(st.target.id, []).append((st.value, st, handler))
        elif isinstance(st, ast.Try):
            _collect_assigns(st.body, handler, out)
            for h in st.handlers:
                _collect_assigns(h.body, h, out)
            _collect_assigns(st.orelse, handler, out)
            _collect_assigns(st.finalbody, handler, out)
        elif isinstance(st, ast.If):
            _collect_assigns(st.body, handler, out)
            _collect_assigns(st.orelse, handler, out)


def _comments(text):
    out = {}
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.COMMENT:
            out[tok.start[0]] = tok.string
    return out


def _site_nodes(tree, parents):
    """(node, kind) for every skip site."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            kind = CALL_KINDS.get(name) or ("skipTest" if name.endswith(".skipTest") else None)
            if kind:
                yield node, kind
        elif isinstance(node, (ast.Name, ast.Attribute)) and not isinstance(getattr(node, "ctx", None), ast.Store):
            kind = BARE_KINDS.get(_dotted(node))
            par = parents.get(node)
            if kind and not (isinstance(par, ast.Call) and par.func is node) and not isinstance(par, ast.Attribute):
                yield node, kind
        elif isinstance(node, ast.Raise) and isinstance(node.exc, (ast.Name, ast.Attribute)):
            if _dotted(node.exc) in ("SkipTest", "unittest.SkipTest"):
                yield node, "SkipTest"


def audit_source(rel, text):
    """The skip sites of one test file (Site list). Raises SyntaxError / tokenize.TokenError / ValueError."""
    tree = ast.parse(text)
    comments = _comments(text)
    lines = text.splitlines()
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    assigns = {}
    _collect_assigns(tree.body, None, assigns)

    def comment_text(lo, hi):
        return " ".join(comments[n] for n in range(max(lo, 1), hi + 1) if n in comments)

    def resolve(names, depth=2):
        """(assigned value nodes, raw source text of where each name is set), following names through assignments."""
        nodes, raw, seen, todo = [], [], set(), set(names)
        for _ in range(depth):
            nxt = set()
            for n in sorted(todo - seen):
                seen.add(n)
                for value, st, handler in assigns.get(n, ()):
                    nodes.append(value)
                    if handler is not None:
                        raw.append("\n".join(lines[handler.lineno - 1:handler.end_lineno]))
                    else:
                        raw.append(comment_text(st.lineno - 3, st.lineno - 1) + "\n" +
                                   "\n".join(lines[st.lineno - 1:st.end_lineno]))
                    nxt |= _names([value])
            todo = nxt
        return nodes, raw

    sites = []
    for node, kind in _site_nodes(tree, parents):
        call = node if isinstance(node, ast.Call) else None
        cond_nodes, reason_nodes = [], []
        if call is not None:
            args = list(call.args)
            kw = {k.arg: k.value for k in call.keywords if k.arg}
            if kind in CONDITION_KINDS and (args and not (isinstance(args[0], ast.Constant) and isinstance(args[0].value, str))
                                            or "condition" in kw):
                cond_nodes.append(kw["condition"] if "condition" in kw else args.pop(0))
            reason_nodes = args + [v for k, v in kw.items() if k != "condition"]
        if not cond_nodes:                      # an inline skip: the enclosing `if` and `except` say why
            par = parents.get(node)
            while par is not None and not isinstance(par, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if isinstance(par, ast.If):
                    cond_nodes.append(par.test)
                elif isinstance(par, ast.ExceptHandler) and par.type is not None:
                    cond_nodes.append(par.type)
                par = parents.get(par)
        resolved, raw = resolve(_names(cond_nodes + reason_nodes))
        reason_parts = [s for s in _strings(reason_nodes + [r for r in resolved if isinstance(r, ast.Constant)]) if s]
        reason = " ".join(reason_parts)
        cond = " ".join(ast.unparse(n) for n in cond_nodes)
        end = getattr(node, "end_lineno", node.lineno)
        context = " ".join([comment_text(node.lineno - 3, end), cond, ast.unparse(node), *raw])
        if DATED_RE.search(context) or DATED_RE.search(reason) or ISO_DATE_RE.search(reason) \
                or DATED_NAME_RE.search(" ".join(sorted(_names(cond_nodes + reason_nodes + resolved)))):
            cls = "dated"
        elif TEMPORARY_RE.search(reason + " " + comment_text(node.lineno - 3, end)):
            cls = "unknown"                     # "not built yet" beats a platform-looking condition
        elif PLATFORM_RE.search(" ".join([cond, *(ast.unparse(r) for r in resolved)])) or REASON_PLATFORM_RE.search(reason):
            cls = "platform/tool"
        else:
            cls = "unknown"
        sites.append(Site(rel, node.lineno, end, kind, cls, reason, cond))
    return sorted(sites, key=lambda s: (s.line, s.kind))


def _git(root, *args):
    try:
        p = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except OSError as e:
        raise NotRun("git could not run (%s): is git on PATH?" % e)
    return p.returncode, p.stdout, p.stderr.strip()


def _check_repo(root):
    rc, top, err = _git(root, "rev-parse", "--show-toplevel")
    if rc != 0 or not top.strip():
        raise NotRun("--root %s is not a git repo (%s)" % (root, err or "no answer from git"))
    if not os.path.samefile(top.strip(), str(root)):
        raise NotRun("--root %s is not a git repo top (the top is %s)" % (root, top.strip()))
    if not (root / TESTS).is_dir():
        raise NotRun("%s not found under %s" % (TESTS, root))


def _check_committed(root):
    """--since reads `git diff <tag>..HEAD`: a test change that is not committed would be missed, so say so."""
    rc, out, err = _git(root, "status", "--porcelain", "--", TESTS)
    if rc != 0:
        raise NotRun("git status failed: %s" % err)
    if out.strip():
        raise NotRun("uncommitted test changes under %s, so --since cannot see them: commit or stash, then rerun:\n  %s"
                     % (TESTS, "\n  ".join(out.rstrip().splitlines()[:10])))


def _added_lines(root, tag):
    """{repo-relative path: set of line numbers added since the tag}, from read-only `git diff`."""
    if tag.startswith("-") or _git(root, "rev-parse", "--verify", "--quiet", tag + "^{commit}")[0] != 0:
        raise NotRun("the tag/ref %r does not exist in %s" % (tag, root))
    rc, out, err = _git(root, "-c", "core.quotepath=off", "diff", "--unified=0", "--no-color", "--no-ext-diff",
                        tag + "..HEAD", "--", TESTS)
    if rc != 0:
        raise NotRun("git diff %s..HEAD failed: %s" % (tag, err))
    added, path = {}, None
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[4:] if line[4:] != "/dev/null" else None
            if path and path.startswith("b/"):
                path = path[2:]
        elif line.startswith("@@") and path:
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                added.setdefault(path, set()).update(range(start, start + count))
    return added


def _test_files(root):
    top = root / TESTS
    for dirpath, dirnames, filenames in os.walk(str(top)):
        rel = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__" and (rel + "/" + d) != FIXTURES)
        for f in sorted(filenames):
            if f.endswith(".py"):
                yield Path(dirpath) / f


def audit_tree(root):
    """(file count, sites); raises NotRun naming every file that did not parse."""
    sites, bad, count = [], [], 0
    for p in _test_files(root):
        rel = p.relative_to(root).as_posix()
        count += 1
        try:
            with open(str(p), "rb") as f:
                text = f.read().decode("utf-8-sig")
            sites += audit_source(rel, text)
        except (SyntaxError, tokenize.TokenError, ValueError) as e:
            bad.append("%s: %s" % (rel, e))
    if bad:
        raise NotRun("%d test file(s) did not parse, so the audit did not cover them:\n  %s" % (len(bad), "\n  ".join(bad)))
    return count, sites


def _site_dict(s, new):
    return {"file": s.file, "line": s.line, "end_line": s.end, "kind": s.kind, "class": s.cls, "reason": s.reason,
            "new": new}


def run(root, since, show_all, as_json):
    _check_repo(root)
    if since:
        _check_committed(root)
    added = _added_lines(root, since) if since else None
    count, sites = audit_tree(root)
    rows = []
    for s in sites:
        new = None if added is None else any(n in added.get(s.file, ()) for n in range(s.line, s.end + 1))
        rows.append((s, new))
    fails = [(s, new) for s, new in rows if s.cls == "dated" or (since and s.cls == "unknown" and new)]
    counts = {c: sum(1 for s, _ in rows if s.cls == c) for c in CLASSES}
    code = 1 if fails else 0
    if as_json:
        print(json.dumps({"exit": code, "since": since, "files": count, "counts": counts,
                          "fail": [_site_dict(s, n) for s, n in fails],
                          "sites": [_site_dict(s, n) for s, n in rows]}, ensure_ascii=False, indent=2))
        return code
    print("skip audit: %d test files under %s (fixtures excluded)" % (count, TESTS))
    line = "sites: " + ", ".join("%s %d" % (c, counts[c]) for c in CLASSES)
    if since:
        line += "; new since %s: %d unknown" % (since, sum(1 for s, n in rows if s.cls == "unknown" and n))
    print(line)
    for s, new in (rows if show_all else fails):
        mark = "FAIL" if (s, new) in fails else "NEW " if new else "    "
        print("%s  %s:%d  %s  %s  %s" % (mark, s.file, s.line, s.cls, s.kind, s.reason[:100]))
    if fails:
        print("RESULT: FAIL (%d site%s), exit 1" % (len(fails), "" if len(fails) == 1 else "s"))
    else:
        print("RESULT: clean (no dated skip%s), exit 0" % (" and no new unknown skip since %s" % since if since else ""))
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gate 4: no temporary dated skips in whynot-cut/tests (BL-20).")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="the repo top (default: this repo)")
    ap.add_argument("--since", metavar="TAG", help="gate mode: a new unknown skip since TAG fails too")
    ap.add_argument("--all", action="store_true", help="list every site, not only the failing ones")
    ap.add_argument("--json", action="store_true", help="a machine report on stdout")
    a = ap.parse_args(argv)
    try:
        return run(Path(a.root).resolve(), a.since, a.all, a.json)
    except NotRun as e:
        if a.json:
            print(json.dumps({"exit": 2, "error": str(e)}, ensure_ascii=False))
        else:
            print("NOT RUN: %s\nThe skip audit did not run to the end; this is not a pass. Exit 2." % e)
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")        # Arabic reasons on a cp1252 console
    sys.exit(main())
