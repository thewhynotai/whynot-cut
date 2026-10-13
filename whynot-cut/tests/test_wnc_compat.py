"""3.0 T6.3 Task 2 (D18) - the ExtendScript libraries are wnc_*.jsx with WNC* namespaces, and the live 3.1.1 bridge
still works with them.

The 3.1.1 bridge (adobe/cep-bridge/js/bridge.js, VERSION '3.1.1', live on Yunus's PC) runs every job as
    $.evalFile(new File("<scripts>/<lib>")); NHPP.run("<data file>");      (NHAE.run in After Effects)
so for 3.0 the renamed libraries end with `var NHPP = WNCPP;` / `var NHAE = WNCAE;` (removed in 3.1). These tests run
that exact tail in node against the synced libraries with a fake host, scan the templates and the engine for the old
names, check the scripts the engine generates (After Effects graphics, MOGRTs, the motion fallback, Photoshop), and
check that the ASCII-escaped Arabic MOGRT samples decode to the original text.
Run:  bash tools/test.sh -p test_wnc_compat.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ast
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys = _sys
SK = Path(__file__).resolve().parents[1]
ROOT = SK.parent
sys.path.insert(0, str(SK / "engine" / "reel"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import common  # noqa: E402
from lib.common import Paths, write_json  # noqa: E402
from test_pipeline import assert_js_syntax  # noqa: E402  (functions only: importing classes would run them twice)

NODE = shutil.which("node")
TPL = SK / "templates"
LIBS = {"wnc_ppro_lib.jsx": TPL / "premiere", "wnc_ae_bridge.jsx": TPL / "after_effects",
        "wnc_ae_lib.jsx": TPL / "after_effects", "wnc_motion_lib.jsx": TPL / "after_effects",
        "wnc_ps_lib.jsx": TPL / "photoshop"}

# every pre-D18 name of a library file, namespace or generated global (the AE project content names NH_BRAND,
# NH_COMPS, NH_CAPTIONS, NH_MOGRT, NH_PERSISTENT, NH_SCENES, NH_MOGRT_TEMPLATES.aep and the result markers stay in 3.0)
OLD = re.compile(r"\bnh_(ppro_lib|ae_bridge|ae_lib|motion_lib|ps_lib)\b|\bNH(PP|AE|M|PS)\b|\bNHAE_HERE\b"
                 r"|\bNH_(DATA|JOB|INFO|PS)\b|\bNH\.")
ALIASES = {"wnc_ppro_lib.jsx": "var NHPP = WNCPP;", "wnc_ae_bridge.jsx": "var NHAE = WNCAE;"}


def old_names(text: str) -> list:
    """The pre-D18 names in source text. A `\\n` / `\\r` / `\\t` escape in a string literal ("...\\nNH.build()") would hide
    the name from `\\b`, so escapes count as a separator."""
    return [m.group(0) for m in OLD.finditer(re.sub(r"\\[nrt]", " ", text))]

# The fake ExtendScript host: $.evalFile evaluates at global scope (like ExtendScript), File reads UTF-8.
HOST_JS = r"""
var fs = require('fs'), path = require('path');
function File(p) {
    if (!(this instanceof File)) { return new File(p); }
    this.fsName = String(p); this.name = path.basename(this.fsName); this.encoding = 'BINARY';
    this.exists = fs.existsSync(this.fsName);
}
Object.defineProperty(File.prototype, 'parent', {get: function () { return new File(path.dirname(this.fsName)); }});
File.prototype.open = function () { this._t = fs.readFileSync(this.fsName, 'utf8'); return true; };
File.prototype.read = function () { return this._t; };
File.prototype.close = function () { return true; };
globalThis.File = File;
globalThis.$ = {fileName: '', evalFile: function (f) {
    var prev = $.fileName; $.fileName = f.fsName;
    try { return (0, eval)(fs.readFileSync(f.fsName, 'utf8')); } finally { $.fileName = prev; }
}};
"""
PPRO_APP = {"version": "26.5.2", "build": "7", "project": {"path": "C:\\p\\a.prproj"}, "projects": {"numProjects": 1}}
AE_APP_JS = ("{version: '26.5x89', project: {file: null, dirty: false, numItems: 0},"
             " fonts: {getFontsByPostScriptName: function () { return []; }},"
             " beginSuppressDialogs: function () {}, endSuppressDialogs: function () {}}")


def tail_311(script: Path, entry: str, data_file: Path) -> str:
    """The job code the 3.1.1 bridge.js evaluates (bridge.js line 137, `CFG.entry` = NHPP / NHAE)."""
    return ("$.evalFile(new File(" + json.dumps(str(script)) + ")); " + entry + ".run(" + json.dumps(str(data_file))
            + ");")


def node_run(tc, js: str) -> str:
    d = Path(tempfile.mkdtemp(prefix="wnc_node_"))
    tc.addCleanup(shutil.rmtree, d, True)
    f = d / "run.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run([NODE, str(f)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    tc.assertEqual(r.returncode, 0, r.stderr[-2000:])
    return r.stdout.strip()


@unittest.skipUnless(NODE, "needs node to run the ExtendScript libraries with a fake host")
class TestLegacyEvalTail(unittest.TestCase):
    """The live 3.1.1 bridge evaluates `NHPP.run(...)` / `NHAE.run(...)` after the synced library."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wnc_compat_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = self.tmp / "job.json"
        self.data.write_text(json.dumps({"action": "ping", "id": "r-1"}), encoding="ascii")

    def run_tail(self, app_js: str, script: Path, entry: str) -> dict:
        js = HOST_JS + "globalThis.app = " + app_js + ";\n" + \
             "console.log((0, eval)(" + json.dumps(tail_311(script, entry, self.data)) + "));\n"
        return json.loads(node_run(self, js))

    def test_premiere_ping_through_the_311_tail(self):
        from lib import ppro_bridge
        with mock.patch.object(ppro_bridge, "scripts_dir", lambda: self.tmp / "ppro-scripts"):
            ppro_bridge.sync_scripts()
            lib = ppro_bridge.lib_path()
        self.assertEqual(lib.name, "wnc_ppro_lib.jsx")
        for entry in ("NHPP", "WNCPP"):            # the 3.1.1 entry, and the 3.0 one
            with self.subTest(entry):
                out = self.run_tail(json.dumps(PPRO_APP), lib, entry)
                self.assertEqual(out, {"ok": True, "action": "ping", "result": {
                    "version": "26.5.2", "build": "7", "project": "C:\\p\\a.prproj", "projects_open": 1}})

    def test_after_effects_ping_loads_the_libraries(self):
        from lib import ae_bridge
        scripts = self.tmp / "ae-scripts"
        with mock.patch.object(ae_bridge, "scripts_dir", lambda: scripts):
            ae_bridge.sync_scripts()
            entry_path = ae_bridge.entry_path()
        self.assertEqual(entry_path.name, "wnc_ae_bridge.jsx")
        self.assertEqual(sorted(p.name for p in scripts.iterdir()),
                         ["wnc_ae_bridge.jsx", "wnc_ae_lib.jsx", "wnc_motion_lib.jsx"])
        for entry in ("NHAE", "WNCAE"):
            with self.subTest(entry):
                out = self.run_tail(AE_APP_JS, entry_path, entry)
                self.assertTrue(out["ok"], out)
                self.assertEqual(out["action"], "ping")
                res = out["result"]
                self.assertTrue(res["libs_loaded"], res)          # WNC and WNCM defined at top level
                self.assertTrue(res["fonts_api"], res)
                self.assertEqual(res["ae_version"], "26.5x89")
                self.assertEqual(Path(res["scripts_dir"]), scripts)
                self.assertEqual((res["dirty"], res["num_items"], res["project"]), (False, 0, None))

    def test_an_unknown_action_still_answers_in_json(self):
        from lib import ppro_bridge
        self.data.write_text(json.dumps({"action": "no_such_action"}), encoding="ascii")
        with mock.patch.object(ppro_bridge, "scripts_dir", lambda: self.tmp / "ppro-scripts"):
            ppro_bridge.sync_scripts()
            lib = ppro_bridge.lib_path()
        out = self.run_tail(json.dumps(PPRO_APP), lib, "NHPP")
        self.assertEqual(out, {"ok": False, "error": "unknown action no_such_action"})


class TestD18Scan(unittest.TestCase):
    """No pre-D18 library name, namespace or generated global is left in the templates or the engine."""

    def test_the_five_libraries_are_renamed(self):
        for name, folder in LIBS.items():
            self.assertTrue((folder / name).is_file(), name)
        self.assertEqual(sorted(p.name for p in TPL.rglob("nh_*")), [])

    def test_templates_are_clean_except_the_two_aliases(self):
        for name, folder in LIBS.items():
            lines = (folder / name).read_text(encoding="utf-8").split("\n")
            hits = [(n, ln) for n, ln in enumerate(lines, 1) if old_names(ln)]
            with self.subTest(name):
                if name in ALIASES:
                    self.assertEqual(len(hits), 1, hits)
                    self.assertTrue(hits[0][1].startswith(ALIASES[name] + " //"), hits)
                    self.assertEqual(hits[0][0], max(n for n, ln in enumerate(lines, 1) if ln.strip()), hits)
                else:
                    self.assertEqual(hits, [])

    def test_engine_string_literals_are_clean(self):
        bad = []
        for f in sorted((SK / "engine" / "reel").rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and OLD.search(node.value):
                    bad.append(f"{f.relative_to(SK).as_posix()}:{node.lineno} {OLD.search(node.value).group(0)}")
        self.assertEqual(bad, [])

    def test_engine_comments_name_no_old_library_file(self):
        """Review T6.3 1-4: comments count too for the library FILE names (preview_video.py still said nh_ppro_lib)."""
        files = re.compile(r"\bnh_(ppro_lib|ae_bridge|ae_lib|motion_lib|ps_lib)\b")
        bad = [f"{f.relative_to(SK).as_posix()}:{n}" for f in sorted((SK / "engine" / "reel").rglob("*.py"))
               if "__pycache__" not in f.parts
               for n, ln in enumerate(f.read_text(encoding="utf-8").split("\n"), 1) if files.search(ln)]
        self.assertEqual(bad, [])

    def test_contract_texts_are_clean(self):
        files = sorted((SK / "engine" / "reel" / "contract").glob("*.json"))
        files += [SK / "tests" / "fixtures" / "contract" / "index.json", SK / "tests" / "fixtures" / "contract" / "README.md"]
        gen = ROOT / "adobe" / "premiere-uxp" / "src" / "ops" / "validators.gen.js"
        if gen.is_file():
            files.append(gen)
        self.assertGreater(len(files), 10)
        bad = [f"{f.name}: {n}" for f in files for n in old_names(f.read_text(encoding="utf-8"))]
        self.assertEqual(bad, [])

    def test_protocol_names_the_wnc_action_tables(self):
        desc = json.loads((SK / "engine" / "reel" / "contract" / "protocol.json").read_text(encoding="utf-8"))["description"]
        self.assertIn("WNCPP.actions", desc)
        self.assertIn("WNCAE.actions", desc)

    def test_engine_points_at_the_wnc_files(self):
        from lib import ae_bridge, ppro_bridge
        self.assertEqual(ppro_bridge.LIB_SRC, TPL / "premiere" / "wnc_ppro_lib.jsx")
        self.assertEqual(ae_bridge.LIBS, ("wnc_ae_lib.jsx", "wnc_motion_lib.jsx", "wnc_ae_bridge.jsx"))
        self.assertEqual(ae_bridge.ENTRY_NAME, "wnc_ae_bridge.jsx")
        for name in ae_bridge.LIBS:
            self.assertTrue((ae_bridge.SRC / name).is_file(), name)
        self.assertTrue(ppro_bridge.LIB_SRC.is_file())


class TestGeneratedScripts(unittest.TestCase):
    """The standalone scripts the engine writes embed the renamed libraries and call the WNC* entry points."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wnc_gen_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        root = self.tmp / "Client"
        for d in ("assets", "data"):
            (root / d).mkdir(parents=True, exist_ok=True)
        write_json(root / common.CLIENT_PROFILE_REL / "sequence-settings.json", {"general": {"timebase": 25, "ntsc": False}})
        self.p = Paths(root, "V1")
        self.p.ensure_project()
        write_json(self.p.p("01_analysis/timeline-spec.json"),
                   {"fps": 25.0, "duration_frames": 240, "events": [], "main_segments": []})

    def check(self, script: Path, must: tuple):
        src = script.read_text(encoding="utf-8")
        for s in must:
            self.assertIn(s, src, (script.name, s))
        scan = "\n".join(ln for ln in src.split("\n") if not ln.startswith(tuple(ALIASES.values())))
        self.assertEqual(old_names(scan), [], script.name)
        code = "\n".join(ln for ln in src.split("\n") if not ln.startswith("//"))     # the generated header comments
        self.assertTrue(all(ord(c) < 128 for c in code), script.name)                  # data and libraries: ASCII
        assert_js_syntax(self, script)
        return src

    def test_after_effects_graphics_script(self):
        from lib import ae_builder
        with common.use_context(common.Context(self.p.root)):
            res = ae_builder.generate(self.p)
        src = self.check(Path(res["jsx"]), ("var WNC_DATA = ", "var WNC = WNC || {};"))
        self.assertTrue(src.rstrip().endswith("WNC.build();"), src[-200:])

    def test_mogrt_script(self):
        from lib import mogrt_builder
        with common.use_context(common.Context(self.p.root)):
            jsx = mogrt_builder.generate(self.p)
        src = self.check(jsx, ("var WNC_DATA = ", "NH_MOGRT_TEMPLATES.aep"))   # the AE project name stays in 3.0
        self.assertTrue(src.rstrip().endswith("WNC.buildMogrts();"), src[-200:])

    def test_motion_fallback_script(self):
        from lib import motion_build
        job = {"plan": {"brand": {"teal": [0, 0.5, 0.5]}, "scenes": []}, "caps": {}, "aep_path": "a.aep",
               "render_path": "a.mov", "generated": "now"}
        with common.use_context(common.Context(self.p.root)), mock.patch.object(motion_build, "job_data", lambda p, **kw: job):
            script = motion_build.write_fallback_script(self.p)
        self.check(script, ("var WNC_JOB = ", "var WNC_DATA = {brand: WNC_JOB.plan.brand};", "var WNC_INFO = WNCM.projectInfo();",
                            "if (!WNCM.mayDiscard(WNC_INFO))", "WNCM.build(WNC_JOB);", "var WNCM = WNCM || {};",
                            "var WNC = WNC || {};"))

    def test_photoshop_script(self):
        from lib import ps_builder
        with common.use_context(common.Context(self.p.root)):
            res = ps_builder.generate(self.p)
        src = self.check(Path(res["jsx"]), ("#target photoshop\nvar WNC_PS = ", "var WNCPS = {};"))
        self.assertTrue(src.rstrip().endswith("WNCPS.build();"), src[-200:])


# The pre-3.0 samples, as written in nh_ae_lib.jsx before the ASCII escape (T6.3 Task 2).
ORIGINAL_SPECS = {
    "hook_title": {"text": "سؤال الحلقة\rهنا"},
    "term_callout": {"text": "Medical Term", "latin": True},
    "glass_card": {"text": "جملة مهمة من كلامها\rفي سطرين"},
    "name_card": {"name": "الاسم هنا", "lines": ["السطر الأول", "السطر الثاني"]},
    "cta": {"text": "اكتبولي في الكومنتس"},
}


class TestEscapedArabic(unittest.TestCase):
    """The lint made the libraries ASCII: the Arabic samples are \\uXXXX escapes that must decode to the same text."""

    @unittest.skipUnless(NODE, "needs node to evaluate the library")
    def test_mogrt_specs_decode_to_the_originals(self):
        js = ("var fs = require('fs');\n(0, eval)(fs.readFileSync(" + json.dumps(str(TPL / "after_effects" / "wnc_ae_lib.jsx"))
              + ", 'utf8'));\nvar o = {}; for (var k in WNC.MOGRT_SPECS) { o[k] = WNC.MOGRT_SPECS[k].sample; }\n"
              "console.log(JSON.stringify(o));\n")
        self.assertEqual(json.loads(node_run(self, js)), ORIGINAL_SPECS)

    def test_the_other_escaped_strings(self):
        lib = (TPL / "after_effects" / "wnc_ae_lib.jsx").read_text(encoding="utf-8")
        dec = lambda s: json.loads('"' + s + '"')
        self.assertEqual(dec(re.search(r'WNC\.text\(c, "Title", "([^"]+)"', lib).group(1)), "عنوان القائمة")
        self.assertEqual(dec(re.search(r'\("([^"]+)" \+ i\)', lib).group(1)), "بند رقم ")
        motion = (TPL / "after_effects" / "wnc_motion_lib.jsx").read_text(encoding="utf-8")
        self.assertEqual(dec(re.search(r'WNCM\.jsq\("(\\u0660[^"]*)"\)', motion).group(1)), "٠١٢٣٤٥٦٧٨٩")
        ps = (TPL / "photoshop" / "wnc_ps_lib.jsx").read_text(encoding="utf-8")
        self.assertIn('"Client photo \\u2014 "', ps)
        ppro = (TPL / "premiere" / "wnc_ppro_lib.jsx").read_text(encoding="utf-8")
        self.assertIn("/[\\u0000-\\u001f\\u007f-\\uffff]/g", ppro)         # was a raw U+FFFF (a real bug)
        for name, folder in LIBS.items():
            self.assertTrue(all(b < 128 for b in (folder / name).read_bytes()), name)

    @unittest.skipUnless(NODE, "needs node to run the escaper")
    def test_premiere_escaper_is_ascii_under_any_decoding(self):
        raw = (TPL / "premiere" / "wnc_ppro_lib.jsx").read_bytes()
        s = chr(0x628) + chr(0x627) + chr(1) + chr(0xFFFF) + 'x"'
        for enc in ("utf-8", "latin-1"):
            src = raw.decode(enc)
            a = src.index("WNCPP.q = function")
            b = src.index("\n};", a) + 3
            js = ("var WNCPP = {};\n" + src[a:b] + "\nvar s = " + json.dumps(s) + ", out = WNCPP.q(s);\n"
                  "console.log(JSON.stringify({ascii: out.split('').every(function (c) { return c.charCodeAt(0) < 128; }),"
                  " back: JSON.parse(out) === s}));\n")
            self.assertEqual(json.loads(node_run(self, js)), {"ascii": True, "back": True}, enc)


if __name__ == "__main__":
    unittest.main()
