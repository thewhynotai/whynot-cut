"""3.0 T6.11 prep: the ExtendScript lint for `wnc_*.jsx` (Addendum A2, last paragraph; the three tool PRDs).

Rules: ASCII-only source, ES3 only, namespaced globals, every nested conditional parenthesised. Strings, regex literals
and comments are stripped before the code rules run (false-positive cases below). The repo-wide test enforces the five
core libraries (T6.3 Task 2, D18: nh_*.jsx became wnc_*.jsx) and every later `wnc_*.jsx`.
Run:  tools/test.sh -p test_jsx_lint.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import io
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import jsx_lint  # noqa: E402

HEAD = "var WNC_HUSH = WNC_HUSH || {};\n"


def lint(src, ns="WNC_HUSH", **kw):
    return jsx_lint.lint_source(src, ns, **kw)


def rules(findings):
    return [f.rule for f in findings]


class AsciiRule(unittest.TestCase):
    def test_non_ascii_in_code_string_and_comment_is_flagged(self):
        for src in ("var x = 1; é\n", 'WNC_HUSH.a = "café";\n', "// café\n", "/* ا */\n"):
            with self.subTest(src=src):
                self.assertEqual(rules(lint(HEAD + src)).count("ascii"), 1)

    def test_line_number_and_one_finding_per_line(self):
        f = lint(HEAD + "\n// éèê\n")
        self.assertEqual([(x.line, x.rule) for x in f], [(3, "ascii")])
        self.assertIn("U+00E9", f[0].message)

    def test_escapes_and_plain_ascii_are_clean(self):
        self.assertEqual(lint(HEAD + 'WNC_HUSH.a = "caf\\u00e9"; // plain\n'), [])


class Es3Rule(unittest.TestCase):
    BAD = {
        "map": "var a = [1].map(function (x) { return x; });",
        "forEach": "[1].forEach(function (x) {});",
        "filter": "var a = [1].filter(function (x) { return x; });",
        "reduce": "var a = [1].reduce(function (s, x) { return s + x; }, 0);",
        "arrow": "var f = (x) => x;",
        "arrow-bare": "var f = x => x;",
        "let": "let a = 1;",
        "const": "const a = 1;",
        "template": "var s = `a ${b} c`;",
        "class": "class A {}",
        "some": "[1].some(function (x) { return x; });",
        "every": "[1].every(function (x) { return x; });",
        "trim": "var s = ' a '.trim();",
    }

    def test_each_es3_violation_is_flagged(self):
        for name, src in self.BAD.items():
            with self.subTest(name):
                self.assertIn("es3", rules(lint("function WNC_HUSH_t() {" + src + "\n}\n")))

    def test_es3_code_is_clean(self):
        src = (
            HEAD +
            "WNC_HUSH.f = function (a, b) {\n"
            "    var letter = 1, constant = 2, klass = 3, i;\n"
            "    for (i = 0; i < a.length; i++) { if (a[i] >= b) { continue; } }\n"
            "    var mapper = a.length, filterBy = b.length; mapper = filterBy;\n"
            "    return classify(a) + obj.class + obj.map_x + a.mapping;\n"
            "};\n")
        self.assertEqual(lint(src), [])

    def test_gte_is_not_an_arrow(self):
        self.assertEqual(lint(HEAD + "WNC_HUSH.a = function (a, b) { return a >= b || a <= b; };\n"), [])

    def test_strings_comments_and_regex_do_not_trigger(self):
        src = (
            HEAD +
            "WNC_HUSH.s = 'use .map( or .forEach( here => let const class `x`';\n"
            'WNC_HUSH.t = "a.filter(b) => c";\n'
            "// const x = a.map(b); => let\n"
            "/* class A {} \n  [].reduce( \n  `tpl` */\n"
            "WNC_HUSH.r = /=>|\\.map\\(|`/g;\n"
            "WNC_HUSH.u = '\\'' + ' .forEach( ';\n")
        self.assertEqual(lint(src), [])

    def test_line_numbers(self):
        f = lint(HEAD + "\nWNC_HUSH.a = [].map(function (x) { return x; });\n")
        self.assertEqual([(x.line, x.rule) for x in f], [(3, "es3")])


class NamespaceRule(unittest.TestCase):
    def test_bare_top_level_var_function_and_assignment_are_flagged(self):
        for src in ("var helper = 1;\n", "function helper() {}\n", "helper = 1;\n", "var a = 1, helper = 2;\n"):
            with self.subTest(src=src):
                f = lint(src + HEAD)
                self.assertTrue(f and set(rules(f)) == {"namespace"}, f)

    def test_bridge_pattern_and_prefixed_names_are_clean(self):
        src = (
            HEAD +
            "WNC_HUSH.TICKS = 254016000000;\n"
            "WNC_HUSH.run = function (p) { var local = 1; function inner() { return local; } return inner(); };\n"
            "var WNC_HUSH_HERE = File($.fileName).parent.fsName;\n"
            "function WNC_HUSH_hush_scan() {}\n"
            "WNC_HUSH.x.y = 2;\n")
        self.assertEqual(lint(src), [])

    def test_locals_in_function_bodies_are_not_globals(self):
        src = (HEAD +
               "WNC_HUSH.f = function () { var a = 1; b = 2; for (var i = 0; i < 2; i++) { var c = i; } };\n"
               "function WNC_HUSH_g() { var d = 1; if (d) { var e = 2; } }\n")
        self.assertEqual(lint(src), [])

    def test_for_header_and_block_vars_at_top_level_are_globals(self):
        f = lint(HEAD + "for (var i = 0; i < 2; i++) { var j = i; }\nif (true) { var k = 1; }\n")
        self.assertEqual(sorted(x.message.split("'")[1] for x in f), ["i", "j", "k"])

    def test_other_namespace_is_flagged(self):
        self.assertEqual(rules(lint("var NHPP = NHPP || {};\n")), ["namespace"])
        self.assertEqual(rules(lint("var WNC_HUSHER = 1;\n")), ["namespace"])   # same letters, not NS or NS_...

    def test_allow_list_and_extra_allowed(self):
        self.assertEqual(lint("var WNCAE_HERE = 1;\n", "WNCAE"), [])      # the bridge's folder is in its namespace
        self.assertEqual(rules(lint("var NHAE_HERE = 1;\n", "WNCAE")), ["namespace"])   # D18: no longer allowed
        self.assertEqual(lint("var helper = 1;\n", "WNC_HUSH", allowed={"helper"}), [])
        self.assertNotIn("NHAE_HERE", jsx_lint.ALLOWED_GLOBALS)

    def test_legacy_aliases_only_in_their_own_file(self):
        self.assertEqual(jsx_lint.LEGACY_ALIASES, {"wnc_ppro_lib.jsx": {"NHPP"}, "wnc_ae_bridge.jsx": {"NHAE"}})
        cases = (("wnc_ppro_lib.jsx", "var WNCPP = WNCPP || {};\nvar NHPP = WNCPP;\n", []),
                 ("wnc_ae_bridge.jsx", "var WNCAE = WNCAE || {};\nvar NHAE = WNCAE;\n", []),
                 ("wnc_ppro_lib.jsx", "var WNCPP = WNCPP || {};\nvar NHAE = WNCPP;\n", [(2, "namespace")]),
                 ("wnc_ae_lib.jsx", "var WNC = WNC || {};\nvar NHPP = WNC;\n", [(2, "namespace")]),
                 ("wnc_tidy.jsx", "var WNC_TIDY = WNC_TIDY || {};\nvar NHPP = WNC_TIDY;\n", [(2, "namespace")]))
        with tempfile.TemporaryDirectory() as d:
            for name, src, want in cases:
                with self.subTest(name=name, src=src):
                    p = Path(d) / name
                    p.write_text(src, encoding="utf-8")
                    self.assertEqual([(x.line, x.rule) for x in jsx_lint.lint_file(p)], want)

    def test_names_inside_strings_and_comments_are_ignored(self):
        self.assertEqual(lint("// var helper = 1;\nWNC_HUSH.s = 'var helper = 1;';\n/* function x() {} */\n"), [])

    def test_directives_are_not_code(self):
        self.assertEqual(lint("#target premierepro\n#include 'x.jsx'\n" + HEAD), [])

    def test_namespace_derivation_and_core_map(self):
        ns = jsx_lint.namespace_for
        self.assertEqual(ns("wnc_hush.jsx"), "WNC_HUSH")
        self.assertEqual(ns("a/b/wnc_tidy.jsx"), "WNC_TIDY")
        self.assertEqual(ns("wnc_kalam.jsx"), "WNC_KALAM")
        self.assertEqual(ns("wnc_audio.jsx"), "WNC_AUDIO")
        self.assertEqual(ns("wnc_ppro_lib.jsx"), "WNCPP")
        self.assertEqual(ns("wnc_ae_bridge.jsx"), "WNCAE")
        self.assertEqual(ns("wnc_ae_lib.jsx"), "WNC")
        self.assertEqual(ns("wnc_motion_lib.jsx"), "WNCM")
        self.assertEqual(ns("wnc_ps_lib.jsx"), "WNCPS")
        self.assertEqual(ns("nh_ppro_lib.jsx"), "NH_PPRO_LIB")   # D18: the pre-3.0 names are no longer special
        self.assertEqual(ns("wnc_hush.jsx", {"wnc_hush.jsx": "HUSHX"}), "HUSHX")

    def test_lint_file_uses_the_file_name_namespace(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wnc_tidy.jsx"
            p.write_text("var WNC_TIDY = WNC_TIDY || {};\nvar WNC_HUSH = 1;\n", encoding="utf-8")
            f = jsx_lint.lint_file(p)
            self.assertEqual([(x.line, x.rule) for x in f], [(2, "namespace")])


class TernaryRule(unittest.TestCase):
    def wrap(self, expr):
        return HEAD + "WNC_HUSH.f = function (a, b, c) {\n    return " + expr + ";\n};\n"

    def test_unparenthesised_nested_conditionals_are_flagged(self):
        for expr in ("a ? 1 : b ? 2 : 3", "a ? b ? 1 : 2 : 3", "a ? 1 :\n        b ? 2 :\n        c ? 3 : 4",
                     "a ? 1 : b ? (c ? 2 : 3) : 4", "x(a ? 1 : b ? 2 : 3)"):
            with self.subTest(expr=expr):
                f = lint(self.wrap(expr))
                self.assertEqual(set(rules(f)), {"ternary"})

    def test_parenthesised_and_separate_conditionals_are_clean(self):
        for expr in ("a ? 1 : (b ? 2 : 3)", "a ? (b ? 1 : 2) : 3", "(a ? 1 : 2) ? 3 : 4",
                     "a ? (b ? 1 : (c ? 2 : 3)) : 4", "[a ? 1 : 2, b ? 3 : 4]",
                     "{ k: a ? 1 : 2, j: b ? 3 : 4 }", "a ? { x: 1 } : { y: 2 }",
                     "a ? function () { return b ? 1 : 2; } : null", "a ? [b ? 1 : 2][0] : 3", "f(a ? 1 : 2, b ? 3 : 4)"):
            with self.subTest(expr=expr):
                self.assertEqual(lint(self.wrap(expr)), [])

    def test_sequential_statements_do_not_count_as_nested(self):
        src = (HEAD + "WNC_HUSH.f = function (a) {\n    var p = a ? 1 : 2;\n"
               "    var q = a ? 3 : 4;\n    switch (a) { case 1: p = a ? 5 : 6; break; default: q = 0; }\n    return p + q;\n};\n")
        self.assertEqual(lint(src), [])

    def test_line_number_is_the_inner_question_mark(self):
        f = lint(self.wrap("a ? 1 :\n        b ? 2 : 3"))
        self.assertEqual([(x.line, x.rule) for x in f], [(4, "ternary")])

    def test_strings_regex_and_comments_do_not_trigger(self):
        src = (HEAD +
               "WNC_HUSH.a = 'x ? y : z ? w : v';\nWNC_HUSH.b = \"a ? b : c ? d : e\";\n"
               "WNC_HUSH.c = /a?b:c?d/.test('x') ? 1 : 2;\n// a ? b : c ? d : e\n/* a ? b ? c : d : e */\n"
               "WNC_HUSH.d = '\\'' ? 1 : 2;\n")
        self.assertEqual(lint(src), [])


class StripperEdgeCases(unittest.TestCase):
    def test_division_is_not_a_regex(self):
        src = HEAD + "WNC_HUSH.f = function (a, b) { var r = a / b; var s = a / b + b / 2; return (a) / b; };\n"
        self.assertEqual(lint(src), [])

    def test_regex_with_slash_in_class_and_after_return(self):
        src = (HEAD +
               "WNC_HUSH.f = function (s) { if (/[/]=>/.test(s)) { return /'\\/\"/; } return s.replace(/\\/+$/, ''); };\n")
        self.assertEqual(lint(src), [])

    def test_unterminated_string_does_not_hang_or_crash(self):
        lint("var WNC_HUSH = 'abc\nWNC_HUSH.a = 1;\n")
        lint("/* never closed")
        lint("var x = `never closed")


class Cli(unittest.TestCase):
    def run_main(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = jsx_lint.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_findings_exit_nonzero_with_file_line_rule_message(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wnc_hush.jsx"
            p.write_text(HEAD + "WNC_HUSH.a = [].map(function (x) { return x; });\n", encoding="utf-8")
            code, out, err = self.run_main([str(p)])
            self.assertEqual(code, 1)
            self.assertIn("%s:2 es3 " % p, out + err)

    def test_clean_file_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wnc_kalam.jsx"
            p.write_text("var WNC_KALAM = WNC_KALAM || {};\nWNC_KALAM.a = 1;\n", encoding="utf-8")
            self.assertEqual(self.run_main([str(p)])[0], 0)

    def test_namespace_override_flag(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wnc_hush.jsx"
            p.write_text("var FOO = FOO || {};\n", encoding="utf-8")
            self.assertEqual(self.run_main([str(p)])[0], 1)
            self.assertEqual(self.run_main(["--namespace", "wnc_hush.jsx=FOO", str(p)])[0], 0)

    def test_report_only_prints_a_summary_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "wnc_hush.jsx"
            p.write_text("var x = [].map(function (a) { return a; });\n", encoding="utf-8")
            code, out, err = self.run_main(["--report-only", str(p)])
            self.assertEqual(code, 0)
            self.assertIn("es3", out)
            self.assertIn("namespace", out)

    def test_missing_file_is_a_usage_error(self):
        self.assertEqual(self.run_main(["no-such-file.jsx"])[0], 2)

    def test_runs_as_a_script_with_no_args(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "jsx_lint.py")], capture_output=True, text=True,
                           cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_default_files_are_only_wnc_jsx_under_templates_and_adobe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ("whynot-cut/templates/premiere/wnc_ppro_lib.jsx", "whynot-cut/templates/premiere/nh_ppro_lib.jsx",
                        "adobe/premiere-uxp/host/wnc_hush.jsx", "adobe/node_modules/x/wnc_bad.jsx", "docs/wnc_doc.jsx"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("", encoding="utf-8")
            got = sorted(p.relative_to(root).as_posix() for p in jsx_lint.default_files(root))
            self.assertEqual(got, ["adobe/premiere-uxp/host/wnc_hush.jsx", "whynot-cut/templates/premiere/wnc_ppro_lib.jsx"])


CORE_LIBS = ("whynot-cut/templates/premiere/wnc_ppro_lib.jsx", "whynot-cut/templates/after_effects/wnc_ae_bridge.jsx",
             "whynot-cut/templates/after_effects/wnc_ae_lib.jsx", "whynot-cut/templates/after_effects/wnc_motion_lib.jsx",
             "whynot-cut/templates/photoshop/wnc_ps_lib.jsx")


class RepoWide(unittest.TestCase):
    def test_every_wnc_jsx_in_the_repo_is_clean(self):
        """Enforced since T6.3 Task 2: the five core libraries (and every later wnc_*.jsx) lint clean."""
        files = jsx_lint.default_files(ROOT)
        shown = {p.relative_to(ROOT).as_posix() for p in files}
        self.assertTrue(set(CORE_LIBS) <= shown, sorted(set(CORE_LIBS) - shown))
        bad = []
        for p in files:
            bad += [str(f) for f in jsx_lint.lint_file(p)]
        self.assertEqual(bad, [])

    def test_the_lint_command_exits_zero_over_the_repo(self):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = jsx_lint.main([])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertNotIn("nothing to lint", out.getvalue())

    def test_no_nh_jsx_is_left(self):
        """D18: every nh_*.jsx became wnc_*.jsx (node_modules excluded)."""
        left = []
        for sub in ("whynot-cut", "adobe", "tools"):
            left += [p.relative_to(ROOT).as_posix() for p in (ROOT / sub).rglob("nh_*.jsx")
                     if "node_modules" not in p.parts]
        self.assertEqual(left, [])

    def test_nhpp_and_nhae_exist_only_as_the_legacy_aliases(self):
        """In code (comments and strings blanked) NHPP / NHAE appear only as `var NHPP = WNCPP;` /
        `var NHAE = WNCAE;`, the last code line of their own library (the 3.1.1 bridge's eval tail needs them)."""
        want = {"wnc_ppro_lib.jsx": "var NHPP = WNCPP;", "wnc_ae_bridge.jsx": "var NHAE = WNCAE;"}
        for p in jsx_lint.default_files(ROOT):
            code, _ = jsx_lint.strip(p.read_text(encoding="utf-8"))
            lines = [ln.strip() for ln in code.split("\n") if ln.strip()]
            hits = [ln for ln in lines if re.search(r"\bNH(PP|AE)\b", ln)]
            with self.subTest(p.name):
                if p.name in want:
                    self.assertEqual(hits, [want[p.name]])
                    self.assertEqual(lines[-1], want[p.name])
                else:
                    self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
