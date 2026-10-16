"""ET1-07 static checks of the installer UI bundle (installer/app/ui): no browser needed.

- the CSP scan (inline script/style, handlers, HTML sinks, eval, remote URLs) and the scanner's own detections;
- the CSP meta in index.html is the target policy, first in <head>;
- tokens: brand/tokens.css + the direction.md §15 additive tokens (verbatim, as --twn-*), no --mk-* left, every var()
  defined;
- vendor.json: every vendored file comes from one source in the repo, outside ui/, and every vendor/ reference is
  mapped;
- the strings stub: strict JSON in an ES module, en and ar with the same keys, every key the code asks for present;
- the icon subset: in sync with the Adobe track's icons.js (scripts/sync_icons.py --check).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest

import _harness as H
import _scan

UI = H.UI


def ui_files(*suffixes: str):
    return sorted(p for p in UI.rglob("*") if p.is_file() and p.suffix in suffixes)


class ScannerDetects(unittest.TestCase):
    """The scanner must catch each pattern it claims to (else a clean tree proves nothing)."""

    BAD = {
        "a.html": ['<script>alert(1)</script>', '<div style="color:red">', '<div onclick="x()">',
                   '<a href="javascript:void(0)">', '<style>p{}</style>', '<img src="https://x.example/a.png">',
                   '<script src="//cdn.example/x.js"></script>'],
        "a.js": ['el.innerHTML = name;', 'el.outerHTML = s;', 'el.insertAdjacentHTML("beforeend", s);',
                 'document.write(s);', 'eval(s);', 'new Function("return 1");', 'setTimeout("x()", 10);',
                 'el.onclick = go;', 'el.setAttribute("style", "x");', 'el.setAttribute("onerror", "x");',
                 'import("https://x.example/m.js");', 'document.createElement("iframe");', 'fetch("http://www.w3.org/2000/svg/x.js");'],
        "a.css": ['p { background: url(https://x.example/a.png); }', 'p { width: expression(1); }',
                  '@import url("//cdn.example/x.css");'],
    }

    def test_each_bad_pattern_is_caught(self):
        for name, samples in self.BAD.items():
            for s in samples:
                with self.subTest(name=name, sample=s):
                    self.assertTrue(_scan.scan_text(name, s), f"not caught: {s}")

    def test_clean_patterns_pass(self):
        ok = {"a.js": 'el.textContent = name; el.style.width = pct + "%"; el.addEventListener("scroll", f);'
                      ' if (a.onx === b) {} el.setAttribute("dir", "ltr");',
              "b.js": 'const SVG_NS = "http://www.w3.org/2000/svg"; document.createElementNS(SVG_NS, "svg");',
              "a.html": '<script src="js/main.js" type="module"></script><link rel="stylesheet" href="css/a.css">',
              "a.css": 'p { background: url("../vendor/a.png"); }'}
        for name, s in ok.items():
            with self.subTest(name=name):
                self.assertEqual(_scan.scan_text(name, s), [])


class BundleIsCspClean(unittest.TestCase):
    def test_ui_tree_exists(self):
        self.assertTrue((UI / "index.html").is_file(), "installer/app/ui/index.html is missing")

    def test_static_scan_finds_nothing(self):
        self.assertTrue(UI.is_dir())
        self.assertEqual(_scan.scan_tree(UI), [])

    def test_csp_meta_is_the_target_and_comes_first(self):
        src = (UI / "index.html").read_text(encoding="utf-8")
        metas = re.findall(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">', src)
        self.assertEqual(metas, [H.CSP_TARGET])
        head = src[src.index("<head>"):src.index("</head>")]
        first_loader = min(i for i in (head.find("<script"), head.find("<link")) if i >= 0)
        self.assertLess(head.index("Content-Security-Policy"), first_loader,
                        "the CSP meta must come before any script or stylesheet")

    def test_scripts_are_files_and_modules_except_the_guard(self):
        src = (UI / "index.html").read_text(encoding="utf-8")
        tags = re.findall(r"<script\b[^>]*>", src)
        self.assertGreaterEqual(len(tags), 2)
        self.assertIn('src="js/guard.js"', tags[0], "the CSP/error guard must be the first script")
        for t in tags[1:]:
            self.assertIn('type="module"', t)


class Tokens(unittest.TestCase):
    @staticmethod
    def decls(css: str) -> dict:
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", css)}

    def section15(self) -> dict:
        md = (H.REPO / "docs" / "design" / "direction.md").read_text(encoding="utf-8")
        start = md.index("## 15.")
        block = md[start:].split("```css", 1)[1].split("```", 1)[0]
        return self.decls(block)

    def test_section15_tokens_verbatim(self):
        sec = self.section15()
        self.assertEqual(len(sec), 63, "direction.md §15 lists 63 tokens")
        css = (UI / "css" / "tokens-additive.css").read_text(encoding="utf-8")
        block = css.split("/* §15 begin */", 1)[1].split("/* §15 end */", 1)[0]
        self.assertEqual(self.decls(block), sec)

    def test_additive_never_redefines_brand_tokens(self):
        brand = self.decls((H.REPO / "brand" / "tokens.css").read_text(encoding="utf-8"))
        add = self.decls((UI / "css" / "tokens-additive.css").read_text(encoding="utf-8"))
        self.assertEqual(sorted(set(brand) & set(add)), [])

    def test_no_mockup_prefix_left(self):
        for p in ui_files(".css", ".js", ".html"):
            code = re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)
            with self.subTest(p=p.name):
                self.assertEqual(re.findall(r"--mk-[\w-]+", code), [])

    def test_every_var_is_defined(self):
        defined = set(self.decls((H.REPO / "brand" / "tokens.css").read_text(encoding="utf-8")))
        for p in ui_files(".css"):
            defined |= set(self.decls(p.read_text(encoding="utf-8")))
        for p in ui_files(".css"):
            used = set(re.findall(r"var\(\s*(--[\w-]+)", p.read_text(encoding="utf-8")))
            with self.subTest(p=p.name):
                self.assertEqual(sorted(used - defined), [])

    def test_index_links_brand_tokens_first(self):
        src = (UI / "index.html").read_text(encoding="utf-8")
        links = re.findall(r'<link rel="stylesheet" href="([^"]+)">', src)
        self.assertEqual(links[0], "vendor/brand/tokens.css")
        self.assertIn("css/tokens-additive.css", links)


class Vendor(unittest.TestCase):
    def test_every_source_exists_once_outside_ui(self):
        files = H.vendor_map()
        self.assertTrue(files)
        tos = [f["to"] for f in files]
        self.assertEqual(len(tos), len(set(tos)))
        for f in files:
            with self.subTest(f=f["to"]):
                self.assertTrue(f["to"].startswith("vendor/"))
                src = (H.REPO / f["from"]).resolve()
                self.assertTrue(src.is_file(), f["from"])
                self.assertTrue(src.is_relative_to(H.REPO.resolve()))
                self.assertFalse(src.is_relative_to(UI.resolve()), "a vendored file must not live in ui/")

    def test_every_vendor_reference_is_mapped(self):
        mapped = {f["to"] for f in H.vendor_map()}
        refs = set()
        for p in ui_files(".html"):
            refs |= set(re.findall(r'(?:href|src)="(vendor/[^"]+)"', p.read_text(encoding="utf-8")))
        for p in ui_files(".css"):
            for r in re.findall(r'url\("?\.\./(vendor/[^")]+)', p.read_text(encoding="utf-8")):
                refs.add(r)
        for p in ui_files(".js"):
            refs |= set(re.findall(r'"(?:\./|\.\./)*(vendor/[^"]+)"', p.read_text(encoding="utf-8")))
        self.assertTrue(refs)
        self.assertEqual(sorted(refs - mapped), [])

    def test_no_vendor_folder_committed_in_ui(self):
        self.assertFalse((UI / "vendor").exists(), "ui/vendor/ is staged at build/test time, never committed")


class StringsStub(unittest.TestCase):
    def load(self) -> dict:
        src = (UI / "js" / "strings.js").read_text(encoding="utf-8")
        body = src.split("export default", 1)[1].strip()
        self.assertTrue(body.endswith(";"))
        return json.loads(body[:-1])

    def test_strict_json_en_ar_same_keys(self):
        d = self.load()
        self.assertTrue(d["_meta"]["stub"], "ET1-08 replaces this stub; it must say so")
        # plural forms (I.plural: key.one / key.two) may exist in one language only (the Arabic dual has .two, English
        # none); every other key is in both, and every form has its base key
        def base(keys):
            return sorted(k for k in keys if not re.search(r"\.(one|two)$", k))
        self.assertEqual(base(d["en"]), base(d["ar"]))
        for lang in ("en", "ar"):
            for k in d[lang]:
                m = re.match(r"(.*)\.(one|two)$", k)
                if m:
                    self.assertIn(m.group(1), d[lang], f"{lang}: {k} has no base key")
        for lang in ("en", "ar"):
            for k, v in d[lang].items():
                with self.subTest(lang=lang, k=k):
                    self.assertIsInstance(v, str)
                    self.assertTrue(v)

    def test_every_literal_key_in_code_exists(self):
        keys = set(self.load()["en"])
        used = set()
        for p in ui_files(".js"):
            used |= set(re.findall(r"""\b(?:T|Tos|raw|plural)\(\s*"([a-z0-9_]+(?:\.[a-z0-9_]+)*)\"""", p.read_text(encoding="utf-8")))
        self.assertTrue(used)
        self.assertEqual(sorted(used - keys), [])


class Icons(unittest.TestCase):
    def test_icon_subset_in_sync_with_source(self):
        r = subprocess.run([sys.executable, str(H.APP / "scripts" / "sync_icons.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
