# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N3-kalam - WhyNot Kalam panel pure JS port (adobe/tools/kalam/src/js/{range,mogrt,platform}.js).

* KalamPortShape: the port differs from the owner's upstream only by the licence header, the provenance line, the UMD
  tail (`})(window);` -> the UMD form + module.exports) and the listed hunks (A0): mogrt.js loses `G.scan` (Node fs /
  zlib / crypto, cannot run in UXP; the engine takes it over), platform.js gets the A6b paths, safeName and fileUrl.
  require() returns the same object as the global; SPDX, no "hoka", README lists the differences, the R3 copy of
  test_platform.js lists its own.
* KalamPortParity: range and mogrt pure functions, and platform's childEnv / revealCmd / openCmd / templatesDir, fed
  identical inputs on both roots (the upstream fixture tiny.mogrt is read from _upstream, never copied) give identical
  JSON; one node run per root and phase.
* KalamPlatformPort: P.paths under the engine home (no `py`), safeName (Windows reserved device names, trailing dots and
  spaces, empty), fileUrl for drive / POSIX / UNC paths.
Each class skips with a reason when node or adobe/tools is absent (the plugin zip ships the tests without adobe/).
Run:  bash tools/test.sh -p test_kalam_port.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import zipfile  # noqa: E402
from pathlib import Path  # noqa: E402

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
ADOBE_TOOLS = REPO / "adobe" / "tools"
RUNNER = ADOBE_TOOLS / "_harness" / "js_runner.js"
PORT = ADOBE_TOOLS / "kalam" / "src"
UPSTREAM = ADOBE_TOOLS / "kalam" / "_upstream"
FIXTURE = UPSTREAM / "tests" / "panel" / "fixtures" / "tiny.mogrt"
NODE = shutil.which("node")
TOOLS_PRESENT = RUNNER.is_file() and (UPSTREAM / "js").is_dir()
NO_TOOLS = "adobe/tools is not in this checkout (the plugin zip ships the tests but not adobe/)"

FILES = ["range", "mogrt", "platform"]
GLOBALS = {"range": "KalamRange", "mogrt": "KalamMogrt", "platform": "KalamPlatform"}
LETTER = {"range": "R", "mogrt": "G", "platform": "P"}


def run_js(tc, root, load, calls):
    """Run `calls` through js_runner.js with `load` (files relative to root) in ONE node process; return the results."""
    with tempfile.TemporaryDirectory() as td:
        req = Path(td) / "request.json"
        req.write_text(json.dumps({"load": load, "calls": calls}), encoding="utf-8")
        p = subprocess.run([NODE, str(RUNNER), str(root), str(req)], capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
    tc.assertEqual(p.returncode, 0, p.stderr)
    lines = p.stdout.strip().splitlines()
    tc.assertTrue(lines, "runner printed nothing: " + p.stderr)
    out = json.loads(lines[-1])["results"]
    tc.assertEqual(len(out), len(calls))
    return out


def call(fn, *args):
    return {"fn": fn, "args": list(args)}


def text(path):
    data = path.read_bytes()
    assert b"\r" not in data, path
    return data.decode("utf-8")


def between(s, start, end):
    """(index of start, index of end) in s; both markers must occur exactly once."""
    assert s.count(start) == 1 and s.count(end) == 1, (start, end)
    return s.index(start), s.index(end)


# what replaces the upstream G.scan block in mogrt.js
MOGRT_SCAN_NOTE = (
    "    /* The folder scan (every .mogrt under Premiere's Local Templates, thumbnails cached by path + modification time)\n"
    "       needs Node fs, zlib and crypto and cannot run in a UXP panel: the engine service takes it over (Task 11) and\n"
    "       returns [{path, name, folder, textFields, thumb}] built with the pure functions above. */\n"
)
PLATFORM_PATHS = (
    "    /* data folders under the engine home (~/.whynot-cut): <engineHome>/tools/kalam. No Python path: the engine\n"
    "       runtime runs Kalam, a UXP panel cannot spawn it. */\n"
    "    P.paths = function (platform, engineHome, sep) {\n"
    "        var home = join(sep, [engineHome, 'tools', 'kalam']);\n"
    "        return { home: home, logs: join(sep, [home, 'logs']), cache: join(sep, [home, 'cache']),\n"
    "                 models: join(sep, [home, 'models']), hf: join(sep, [home, 'hf']) };\n"
    "    };\n\n"
)
PLATFORM_NAMES = (
    "    /* a file name every OS accepts: Windows forbids \\ / : * ? \" < > |, trailing dots and spaces and the device names\n"
    "       (CON, PRN, AUX, NUL, COM1-9, LPT1-9, also with an extension: nul.srt); an empty result is \"_\" */\n"
    "    P.safeName = function (s) {\n"
    "        var n = String(s).replace(/[\\\\\\/:*?\"<>|]/g, '-').replace(/[. ]+$/, ''), dot = n.indexOf('.');\n"
    "        var base = dot < 0 ? n : n.slice(0, dot);\n"
    "        if (/^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i.test(base.replace(/ +$/, ''))) { n = base + '_' + n.slice(base.length); }\n"
    "        return n || '_';\n"
    "    };\n\n"
    "    /* a file:// URL for a local path: file:///C:/... for a drive path, file:///... for POSIX, file://server/... for UNC */\n"
    "    P.fileUrl = function (p) {\n"
    "        var s = String(p).replace(/\\\\/g, '/'), enc = encodeURI(s).replace(/#/g, '%23').replace(/\\?/g, '%3F');\n"
    "        if (/^[A-Za-z]:\\//.test(s)) { return 'file:///' + enc; }\n"
    "        if (s.slice(0, 2) === '//') { return 'file:' + enc; }\n"
    "        return 'file://' + enc;\n"
    "    };\n\n"
)


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class KalamPortShape(unittest.TestCase):
    SPDX = ["// SPDX-License-Identifier: GPL-3.0-or-later", "// © 2026 The Why Not AI (thewhynot.ai)"]
    UMD = "    if (typeof module === 'object' && module.exports) { module.exports = %s; }"
    TAIL_UP = "})(window);\n"
    TAIL_PORT = "})(typeof window !== 'undefined' ? window : this);\n"

    def expected_body(self, f):
        up = text(UPSTREAM / "js" / (f + ".js"))
        if f == "mogrt":
            a, b = between(up, "    /* Node side: every .mogrt under base", "    root.KalamMogrt = G;\n")
            up = up[:a] + MOGRT_SCAN_NOTE + "\n" + up[b:]
        if f == "platform":
            a, b = between(up, "    /* data folders and the engine's Python for this OS */\n", "    /* environment for the engine")
            up = up[:a] + PLATFORM_PATHS + up[b:]
            a, b = between(up, "    /* a file name every OS accepts", "    /* Premiere's Local Templates folder")
            up = up[:a] + PLATFORM_NAMES + up[b:]
        if up.endswith(self.TAIL_UP):
            up = up[:-len(self.TAIL_UP)] + self.TAIL_PORT
        return up

    def test_files_readme_and_r3_copy_exist(self):
        for f in FILES:
            self.assertTrue((PORT / "js" / (f + ".js")).is_file(), f)
        readme = text(PORT / "README.md")
        for needle in ("_upstream", "module.exports", "scan", "safeName", "fileUrl", "paths", "test_platform.js"):
            self.assertIn(needle, readme)
        self.assertTrue((PORT / "tests" / "panel" / "test_platform.js").is_file())

    def test_spdx_header_provenance_line_and_no_hoka_or_real_names(self):
        for path in [PORT / "js" / (f + ".js") for f in FILES] + [PORT / "README.md", PORT / "tests" / "panel" / "test_platform.js"]:
            body = text(path)
            self.assertNotIn("hoka", body.lower(), path.name)
            self.assertNotIn("rog 2", body.lower(), path.name)
            self.assertNotIn("sherif", body.lower(), path.name)
        for f in FILES:
            lines = text(PORT / "js" / (f + ".js")).split("\n")
            self.assertEqual(lines[:2], self.SPDX, f)
            self.assertTrue(lines[2].startswith("// Ported from the owner's Kalam " + f + ".js"), f)
            self.assertIn("adobe/tools/kalam/src/README.md", lines[2], f)

    def test_modules_differ_from_upstream_only_by_header_umd_tail_and_the_listed_hunks(self):
        for f in FILES:
            port_lines = text(PORT / "js" / (f + ".js")).split("\n")
            umd = self.UMD % LETTER[f]
            self.assertEqual(port_lines.count(umd), 1, f)
            idx = port_lines.index(umd)
            self.assertEqual(port_lines[idx - 1], "    root.%s = %s;" % (GLOBALS[f], LETTER[f]), f)
            body = "\n".join(l for l in port_lines[3:] if l != umd)
            self.assertEqual(body, self.expected_body(f), f)
            self.assertTrue(body.endswith(self.TAIL_PORT), f)

    def test_the_r3_copy_header_lists_its_differences_and_keeps_the_owner_checks(self):
        copy = text(PORT / "tests" / "panel" / "test_platform.js")
        up = text(UPSTREAM / "tests" / "panel" / "test_platform.js")
        lines = copy.split("\n")
        self.assertEqual(lines[:2], KalamPortShape.SPDX)
        header = "\n".join(l for l in lines if l.startswith("//"))
        self.assertIn("R3 copy of kalam/_upstream/tests/panel/test_platform.js", header)
        for needle in ("paths", "py", "cleanPath", "cep.js", "safeName", "fileUrl"):
            self.assertIn(needle, header)
        # the owner's checks that need no change are still there, byte for byte
        for line in up.split("\n"):
            if line.startswith(("var e = P.childEnv", "ok(e.PYTHONUTF8", "var r = P.revealCmd", "ok(r[0] ===", "var o = P.openCmd",
                                "ok(o[0] ===", "ok(P.revealCmd('darwin'", "ok(P.templatesDir")):
                self.assertIn(line, copy.split("\n"), line)

    def test_require_returns_the_global_object_and_scan_is_gone(self):
        script = (
            "globalThis.window = globalThis;\n"
            "var out = {};\n"
            "[%s].forEach(function (p) {\n"
            "  var m = require(p[1]);\n"
            "  out[p[0]] = (m === globalThis[p[0]]) && typeof m === 'object';\n"
            "});\n"
            "out.scan = typeof globalThis.KalamMogrt.scan;\n"
            "console.log(JSON.stringify(out));\n"
        ) % ", ".join("[%s, %s]" % (json.dumps(GLOBALS[f]), json.dumps(str(PORT / "js" / (f + ".js")))) for f in FILES)
        p = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        want = {v: True for v in GLOBALS.values()}
        want["scan"] = "undefined"
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]), want)

    def test_require_works_without_window(self):
        script = (
            "var R = require(%s), G = require(%s), P = require(%s);\n"
            "console.log(JSON.stringify({r: typeof R.rangeFor, g: typeof G.zipEntries, p: typeof P.fileUrl,"
            " win: typeof window, fs: typeof G.scan}));\n"
        ) % tuple(json.dumps(str(PORT / "js" / (f + ".js"))) for f in FILES)
        p = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]),
                         {"r": "function", "g": "function", "p": "function", "win": "undefined", "fs": "undefined"})


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class KalamPortParity(unittest.TestCase):
    def both(self, load, calls):
        up = run_js(self, UPSTREAM, load, calls)
        port = run_js(self, PORT, load, calls)
        for c, a, b in zip(calls, up, port):
            self.assertEqual(a, b, "upstream and port differ for %s" % json.dumps(c)[:200])
        self.assertFalse([r for r in port if isinstance(r, dict) and set(r) == {"error"}], port)
        return port

    def test_range_functions(self):
        seq = {"end": 88.6, "inPoint": 10, "outPoint": 60, "playhead": 25.5,
               "selection": [{"name": "a", "start": 12, "end": 20}, {"name": "b", "start": 18, "end": 30},
                             {"name": "a", "start": 12, "end": 20}]}
        calls = [call("KalamRange.rangeFor", seq, m) for m in ("inout", "sequence", "playhead", "selection", "other")]
        calls += [call("KalamRange.rangeFor", {"end": 50, "inPoint": -400000, "outPoint": -400000, "playhead": 0, "selection": []}, m)
                  for m in ("inout", "selection")]
        calls += [call("KalamRange.rangeFor", {"end": 50, "playhead": 49.95}, "playhead")]
        srt = "1\n00:00:00,500 --> 00:00:02,000\n\u0648\u0627\u062d\u062f\n\n2\n00:59:59,900 --> 01:00:00,100\nx\n"
        calls += [call("KalamRange.shiftSrt", srt, off) for off in (0, 125.5, 0.2, -0.25, 3599.9)]
        calls += [call("KalamRange.MODES")]
        port = self.both(["js/range.js"], calls)
        self.assertEqual(port[0], {"ok": True, "start": 10, "end": 60, "label": "inOut"})
        self.assertEqual(port[3]["count"], 2)

    def test_mogrt_functions_on_the_upstream_fixture(self):
        fx = {"$file": str(FIXTURE)}
        entries = self.both(["js/mogrt.js"], [call("KalamMogrt.zipEntries", fx)])[0]
        self.assertEqual([e["name"] for e in entries], ["definition.json", "project.aegraphic", "thumb.png"])
        with zipfile.ZipFile(str(FIXTURE)) as z:
            definition = json.loads(z.read("definition.json").decode("utf-8"))
        loc = {"strDB": [{"localeString": "de_DE", "str": "Feld"}, {"localeString": "en_US", "str": "Field"}]}
        calls = [call("KalamMogrt.dataStart", fx, e) for e in entries]
        calls += [call("KalamMogrt.definitionInfo", d) for d in (
            definition, {"capsuleName": "Basic", "clientControls": []}, {}, None,
            {"capsuleNameLocalized": loc, "clientControls": [{"type": 6, "uiName": loc}, {"type": 6}, {"type": 2}]})]
        lst = [{"name": "9\u202216 Comic Subtitles", "folder": "Captioneer/Portrait"}, {"name": "Basic Title", "folder": ""},
               {"name": "Bold Web Caption", "folder": "Captions and Subtitles"}]
        calls += [call("KalamMogrt.folderOf", "/T/Captioneer/Portrait/a.mogrt", "/T"), call("KalamMogrt.folderOf", "/T/Basic.mogrt", "/T"),
                  call("KalamMogrt.folderOf", "C:\\T\\Cap\\Por\\a.mogrt", "C:\\T"), call("KalamMogrt.folderOf", "C:\\T\\a.mogrt", "C:\\T")]
        calls += [call("KalamMogrt.filter", lst, q, top) for q, top in (("comic", ""), ("", "Captioneer"), ("CAPTION", ""), ("", ""), ("zzz", ""))]
        calls += [call("KalamMogrt.topFolders", lst), call("KalamMogrt.topFolders", [])]
        port = self.both(["js/mogrt.js"], calls)
        self.assertEqual(port[len(entries)]["textFields"], ["Text", "Speaker"])

    def test_unchanged_platform_functions(self):
        calls = [call("KalamPlatform.childEnv", p, {"PATH": "C:\\Windows", "PYTHONUTF8": "0", "X": "y"}) for p in ("win32", "darwin")]
        calls += [call("KalamPlatform.revealCmd", p, path) for p in ("win32", "darwin") for path in ("C:\\a b\\c.srt", "/a b/c.srt")]
        calls += [call("KalamPlatform.openCmd", p, path) for p in ("win32", "darwin") for path in ("C:\\x", "/x")]
        calls += [call("KalamPlatform.templatesDir", "win32", {"APPDATA": "C:\\Users\\x\\AppData\\Roaming"}, "C:\\Users\\x", "\\"),
                  call("KalamPlatform.templatesDir", "win32", {}, "C:\\Users\\x", "\\"),
                  call("KalamPlatform.templatesDir", "darwin", {}, "/Users/x", "/")]
        calls += [call("KalamPlatform.safeName", n) for n in (
            "Weekly Show", "Episode 2: \"final\" <v2>?|*\\x/y", "\u062d\u0644\u0642\u0629 \u0661", "a.b.c", "console", "nullable.srt", "COM10", "x" * 80)]
        self.both(["js/platform.js"], calls)


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class KalamPlatformPort(unittest.TestCase):
    def run_platform(self, calls):
        return run_js(self, PORT, ["js/platform.js"], calls)

    def test_paths_are_under_the_engine_home_and_have_no_python(self):
        win, mac, arabic = self.run_platform([
            call("KalamPlatform.paths", "win32", "C:\\Users\\x\\.whynot-cut", "\\"),
            call("KalamPlatform.paths", "darwin", "/Users/x/.whynot-cut", "/"),
            call("KalamPlatform.paths", "win32", "D:\\\u0645\u062d\u0645\u062f \u0639\u0644\u064a\\.whynot-cut", "\\")])
        h = "C:\\Users\\x\\.whynot-cut\\tools\\kalam"
        self.assertEqual(win, {"home": h, "logs": h + "\\logs", "cache": h + "\\cache", "models": h + "\\models", "hf": h + "\\hf"})
        h = "/Users/x/.whynot-cut/tools/kalam"
        self.assertEqual(mac, {"home": h, "logs": h + "/logs", "cache": h + "/cache", "models": h + "/models", "hf": h + "/hf"})
        self.assertEqual(arabic["home"], "D:\\\u0645\u062d\u0645\u062f \u0639\u0644\u064a\\.whynot-cut\\tools\\kalam")
        for p in (win, mac, arabic):
            self.assertNotIn("py", p)

    def test_safe_name(self):
        cases = [
            ("Episode 2: \"final\" <v2>?|*\\x/y", "Episode 2- -final- -v2-----x-y"),
            ("Weekly Show", "Weekly Show"), ("\u062d\u0644\u0642\u0629 \u0661", "\u062d\u0644\u0642\u0629 \u0661"),
            ("nul", "nul_"), ("NUL.srt", "NUL_.srt"), ("Com1", "Com1_"), ("lpt9.tar.gz", "lpt9_.tar.gz"), ("PRN", "PRN_"),
            ("aux ", "aux_"), ("con.", "con_"), ("prn .txt", "prn _.txt"), ("CON:", "CON-"), ("COM0", "COM0"),
            ("COM10", "COM10"), ("console", "console"), ("nullable.srt", "nullable.srt"), ("my.nul", "my.nul"),
            ("name. . ", "name"), ("a.b.", "a.b"), ("", "_"), ("...", "_"), ("   ", "_"), (".", "_"), ("a b", "a b"),
        ]
        out = self.run_platform([call("KalamPlatform.safeName", s) for s, _ in cases])
        self.assertEqual(out, [want for _, want in cases])

    def test_file_url(self):
        cases = [
            ("C:\\Users\\x\\a b\\t#1?.png", "file:///C:/Users/x/a%20b/t%231%3F.png"),
            ("c:/x/y.png", "file:///c:/x/y.png"),
            ("D:\\\u0645\u062d\\a.png", "file:///D:/%D9%85%D8%AD/a.png"),
            ("/Users/x/a b.png", "file:///Users/x/a%20b.png"),
            ("/Users/\u0645/a%b.png", "file:///Users/%D9%85/a%25b.png"),
            ("/t/a#b?c.png", "file:///t/a%23b%3Fc.png"),
            ("\\\\srv\\share\\a b.png", "file://srv/share/a%20b.png"),
        ]
        out = self.run_platform([call("KalamPlatform.fileUrl", p) for p, _ in cases])
        self.assertEqual(out, [want for _, want in cases])


if __name__ == "__main__":
    unittest.main()
