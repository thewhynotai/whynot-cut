# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N3-tidy - WhyNot Tidy pure JS port (adobe/tools/tidy/src/js/{media,classify,plan,sync}.js).

* TidyPortShape: the port differs from the owner's upstream only by the licence header, the provenance line, the
  CommonJS line and (plan.js) the listed hunks (A0). require() returns the same object as the global; SPDX header,
  no "hoka", README lists the differences.
* TidyPortParity: `build` and the helpers of the unchanged modules, fed identical inputs on both roots (no platform,
  "darwin", "linux": the path key is the path itself), give identical JSON, one node run per root.
* TidyPathKey: plan.js path key (audit 3.3) - Windows paths are case-insensitive and may use either separator, so on
  win32 `C:\\M\\Clip.MP4` and `c:/m/clip.mp4` are ONE duplicate group; on darwin / no platform they are two files.
* TidyBackupNames: P.BACKUP accepts the legacy "(Hush backup|cut ...)" and the new "(WhyNot Hush backup|cut ...)" (A6b).
* TidyNameHelpers: A3 #7 pure helpers P.syncedName, P.TEMP_SYNC, P.TIDY_BACKUP.
* JscShimContract: the jsc shim's globals and exit codes; it ends through process.exitCode, never process.exit.
Each class skips with a reason when node or adobe/tools is absent (the plugin zip ships the tests without adobe/).
Run:  bash tools/test.sh -p test_tidy_port.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
ADOBE_TOOLS = REPO / "adobe" / "tools"
RUNNER = ADOBE_TOOLS / "_harness" / "js_runner.js"
SHIM = ADOBE_TOOLS / "_harness" / "jsc_shim.js"
PORT = ADOBE_TOOLS / "tidy" / "src"
UPSTREAM = ADOBE_TOOLS / "tidy" / "_upstream"
NODE = shutil.which("node")
TOOLS_PRESENT = RUNNER.is_file() and (UPSTREAM / "js").is_dir()
NO_TOOLS = "adobe/tools is not in this checkout (the plugin zip ships the tests but not adobe/)"

FILES = ["media", "classify", "plan", "sync"]
GLOBALS = {"media": "TidyMedia", "classify": "TidyClassify", "plan": "TidyPlan", "sync": "TidySync"}
LETTER = {"media": "M", "classify": "C", "plan": "P", "sync": "Y"}
LOAD_PLAN = ["js/classify.js", "js/plan.js"]


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


def item(nid, name, path, **extra):
    it = {"nodeId": nid, "name": name, "path": path, "isSequence": False, "duration": 10, "bin": "", "exists": True,
          "offline": False, "size": 1000, "color": 0}
    it.update(extra)
    return it


def seq(nid, name, **extra):
    return item(nid, name, "", isSequence=True, size=0, **extra)


def text(path):
    data = path.read_bytes()
    assert b"\r" not in data, path
    return data.decode("utf-8")


# a scan with duplicates (used and unused), backups with the legacy names, an offline file, captions, a nest
SCAN_A = {
    "items": [
        item("c1", "clip.mp4", "/m/clip.mp4", size=5000, kind="camera", camId="DJI OsmoPocket3", duration=600),
        item("c2", "clip.mp4", "/m/clip.mp4", size=5000, kind="camera", camId="DJI OsmoPocket3"),
        item("v1", "voice.wav", "/m/voice.wav", duration=200),
        item("x1", "onlyInBackup.mp4", "/m/onlyInBackup.mp4"),
        item("l1", "logo.png", "/m/logo.png"),
        item("d1", "both.mp4", "/m/both.mp4", kind="camera", camId="iPhone 16 Pro Max", duration=100),
        item("d2", "both.mp4", "/m/both.mp4", kind="camera", camId="iPhone 16 Pro Max", duration=100),
        item("o1", "gone.mp4", "/m/gone.mp4", exists=False),
        item("t1", "subs.srt", "/m/subs.srt", bin="Kalam Captions"),
        seq("q1", "Main"), seq("q2", "Logo Nest"),
        seq("q3", "Main (Hush backup 10:00:00)"), seq("q5", "Main (Hush cut 10:05:00)"),
        seq("q4", "Old Edit"),
    ],
    "bins": [{"nodeId": "b1", "path": "Empty Bin"}, {"nodeId": "b2", "path": "Kalam Captions"},
             {"nodeId": "b3", "path": "03 Audio"}, {"nodeId": "b5", "path": "Assets"},
             {"nodeId": "b6", "path": "Assets/Assets"}],
    "usage": {"q1": ["c1", "q2", "d1", "o1"], "q2": ["l1"], "q3": ["c1", "x1"], "q5": ["x1"], "q4": ["d2"]},
}
SCAN_B = {   # podcast footage, mics, nests named after their content
    "items": [item("k1", "C0001.MP4", "/r/C0001.MP4", kind="camera", camId="A", duration=3000),
              item("m1", "ZOOM0001.WAV", "/r/ZOOM0001.WAV", duration=3600),
              item("u1", "stock.mp4", "/r/stock.mp4", kind="render"),
              seq("main", "Main"), seq("n1", "Nested Sequence 01"), seq("n2", "Nested Sequence 02"),
              item("img", "Corporate Success.png", "/a/Corporate Success.png")],
    "bins": [], "usage": {"main": ["n1", "n2"], "n1": ["img"], "n2": []},
    "texts": {"n2": ["  \u0647\u064a\u0631\u0642\u064a\u0643   \u0644\u0648  "]},
}


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyPortShape(unittest.TestCase):
    SPDX = ["// SPDX-License-Identifier: GPL-3.0-or-later", "// © 2026 The Why Not AI (thewhynot.ai)"]
    UMD = "    if (typeof module === 'object' && module.exports) { module.exports = %s; }"
    # plan.js: every difference from upstream, as (upstream text, port text); nothing else may differ (A0)
    PLAN_EDITS = [
        ("    var C = root.TidyClassify, P = {};\n    P.BACKUP = /\\((Hush backup|Hush cut) /;\n",
         "    var C = root.TidyClassify || (typeof require === 'function' ? require('./classify.js') : undefined), P = {};\n"
         "    P.BACKUP = /\\((?:WhyNot )?Hush (?:backup|cut) /;\n"
         "    P.TEMP_SYNC = /^(?:WhyNot )?Tidy sync temp$/;\n"
         "    P.TIDY_BACKUP = /\\((?:WhyNot )?Tidy backup /;\n"
         "    /* the key under which two media paths are the same file: Windows paths are case-insensitive and may use\n"
         "       either separator; anywhere else the path is its own key */\n"
         "    P.pathKey = function (path, platform) {\n"
         "        return platform === 'win32' ? String(path).replace(/\\\\/g, '/').toLowerCase() : path;\n"
         "    };\n"),
        ("            (byPath[it.path] = byPath[it.path] || []).push(it);\n",
         "            var pkey = P.pathKey(it.path, opts.platform);\n"
         "            (byPath[pkey] = byPath[pkey] || []).push(it);\n"),
        ("                duplicates.push({ path: path, name: group[0].name,",
         "                duplicates.push({ path: group[0].path, name: group[0].name,"),
        ("    root.TidyPlan = P;\n",
         "    /* the sequence the synced podcast is built into: \"<project> - Synced\", else \"... - Synced 2\", \"... - Synced 3\" */\n"
         "    P.syncedName = function (projectName, existingNames) {\n"
         "        var base = (projectName || 'Podcast').replace(/\\.prproj$/, '') + ' - Synced', name = base, n = 2, taken = existingNames || [];\n"
         "        function has(s) { var i; for (i = 0; i < taken.length; i++) { if (taken[i] === s) { return true; } } return false; }\n"
         "        while (has(name)) { name = base + ' ' + n++; }\n"
         "        return name;\n"
         "    };\n\n"
         "    root.TidyPlan = P;\n"),
    ]

    def test_files_and_readme_exist(self):
        for f in FILES:
            self.assertTrue((PORT / "js" / (f + ".js")).is_file(), f)
        readme = text(PORT / "README.md")
        for needle in ("_upstream", "module.exports", "pathKey", "BACKUP", "syncedName", "TEMP_SYNC", "TIDY_BACKUP"):
            self.assertIn(needle, readme)

    def test_spdx_header_provenance_line_and_no_hoka(self):
        for f in FILES:
            body = text(PORT / "js" / (f + ".js"))
            lines = body.split("\n")
            self.assertEqual(lines[:2], self.SPDX, f)
            self.assertTrue(lines[2].startswith("// Ported from the owner's Tidy " + f + ".js"), f)
            self.assertIn("adobe/tools/tidy/src/README.md", lines[2], f)
            self.assertNotIn("hoka", body.lower(), f)
        self.assertNotIn("hoka", text(PORT / "README.md").lower())

    def test_modules_differ_from_upstream_only_by_header_umd_line_and_the_listed_plan_hunks(self):
        for f in FILES:
            up = text(UPSTREAM / "js" / (f + ".js"))
            port_lines = text(PORT / "js" / (f + ".js")).split("\n")
            umd = self.UMD % LETTER[f]
            self.assertEqual(port_lines.count(umd), 1, f)
            idx = port_lines.index(umd)
            self.assertEqual(port_lines[idx - 1], "    root.%s = %s;" % (GLOBALS[f], LETTER[f]), f)
            body = "\n".join(l for l in port_lines[3:] if l != umd)
            if f == "plan":
                for old, new in self.PLAN_EDITS:
                    self.assertEqual(up.count(old), 1, old)
                    up = up.replace(old, new)
            self.assertEqual(body, up, f)

    def test_require_returns_the_global_object(self):
        script = (
            "globalThis.window = globalThis;\n"
            "var out = {};\n"
            "[%s].forEach(function (p) {\n"
            "  var m = require(p[1]);\n"
            "  out[p[0]] = (m === globalThis[p[0]]) && typeof m === 'object';\n"
            "});\n"
            "console.log(JSON.stringify(out));\n"
        ) % ", ".join("[%s, %s]" % (json.dumps(GLOBALS[f]), json.dumps(str(PORT / "js" / (f + ".js")))) for f in FILES)
        p = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]), {v: True for v in GLOBALS.values()})

    def test_require_works_without_window_and_plan_finds_classify(self):
        script = (
            "var P = require(%s), M = require(%s), Y = require(%s);\n"
            "var plan = P.build({items: [], bins: [], usage: {}}, {});\n"
            "console.log(JSON.stringify({b: typeof P.build, m: typeof M.describe, y: typeof Y.plan, stats: plan.stats,"
            " win: typeof window}));\n"
        ) % tuple(json.dumps(str(PORT / "js" / (f + ".js"))) for f in ("plan", "media", "sync"))
        p = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual((out["b"], out["m"], out["y"], out["win"]), ("function", "function", "function", "undefined"))
        self.assertEqual(out["stats"], {"removeCount": 0, "removeSize": 0, "totalSize": 0, "byType": {}})


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyPortParity(unittest.TestCase):
    def both(self, load, calls):
        up = run_js(self, UPSTREAM, load, calls)
        port = run_js(self, PORT, load, calls)
        for c, a, b in zip(calls, up, port):
            self.assertEqual(a, b, "upstream and port differ for %s" % json.dumps(c)[:200])
        return port

    def test_build_is_identical_without_a_platform_and_on_darwin(self):
        calls = []
        for scan in (SCAN_A, SCAN_B):
            for opts in ({}, {"platform": "darwin"}, {"platform": "linux"}, {"mode": "podcast"},
                         {"mode": "podcast", "platform": "darwin", "checked": {"k1": True}},
                         {"unchecked": {"v1": True}}, {"checked": {"t1": True}}, {"noRename": {"n1": True}}):
                calls.append(call("TidyPlan.build", scan, opts))
        calls.append(call("TidyPlan.build", SCAN_A))
        port = self.both(LOAD_PLAN, calls)
        self.assertFalse([r for r in port if isinstance(r, dict) and "error" in r], port)
        self.assertEqual(len(port[0]["duplicates"]), 1)
        self.assertEqual(port[0]["duplicates"][0]["path"], "/m/both.mp4")

    def test_helpers_of_the_unchanged_functions_are_identical(self):
        names = ["clip.mp4", "Main (Hush backup 10:00:00)", "C0001.MP4", "subs.srt", "logo.png", "ZOOM0001.WAV"]
        calls = [call("TidyPlan.nestName", seq("n", "Nested"), ["  hello   world "], [], {}),
                 call("TidyClassify.category", item("a", "x.mp4", "/m/x.mp4", kind="camera", duration=700),
                      {"nestIds": {}, "mode": "reels", "camNumbers": {}}),
                 call("TidyClassify.cameraNumbers", [item("a", n, "/m/" + n, kind="camera", camId=n) for n in names])]
        calls += [call("TidyPlan.BACKUP.test", n) for n in names if "WhyNot" not in n]
        port = self.both(LOAD_PLAN, calls)
        self.assertFalse([r for r in port if isinstance(r, dict) and "error" in r], port)


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyPathKey(unittest.TestCase):
    A, B = "C:\\M\\Clip.MP4", "c:/m/clip.mp4"

    def scan(self):
        return {"items": [item("k1", "Clip.MP4", self.A, kind="camera", camId="X"),
                          item("k2", "Clip.MP4", self.B, kind="camera", camId="X"),
                          item("k3", "other.mp4", "/m/other.mp4"), seq("s", "Main")],
                "bins": [], "usage": {"s": ["k1", "k2", "k3"]}}

    def test_path_key_function(self):
        out = run_js(self, PORT, LOAD_PLAN, [
            call("TidyPlan.pathKey", self.A, "win32"), call("TidyPlan.pathKey", self.B, "win32"),
            call("TidyPlan.pathKey", self.A, "darwin"), call("TidyPlan.pathKey", self.A),
            call("TidyPlan.pathKey", "/Users/Me/Clip.MP4", "darwin"), call("TidyPlan.pathKey", "/Users/Me/Clip.MP4", "win32"),
            call("TidyPlan.pathKey", "\\\\NAS\\Share\\A.mov", "win32"), call("TidyPlan.pathKey", "", "win32")])
        self.assertEqual(out, ["c:/m/clip.mp4", "c:/m/clip.mp4", self.A, self.A, "/Users/Me/Clip.MP4",
                               "/users/me/clip.mp4", "//nas/share/a.mov", ""])

    def test_one_duplicate_group_on_windows_two_files_elsewhere(self):
        win, mac, none = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.build", self.scan(), {"platform": "win32"}),
                                                        call("TidyPlan.build", self.scan(), {"platform": "darwin"}),
                                                        call("TidyPlan.build", self.scan(), {})])
        self.assertEqual(win["duplicates"], [{"path": self.A, "name": "Clip.MP4", "copies": 2, "used": 2}])
        self.assertEqual(mac["duplicates"], [])
        self.assertEqual(none, mac)

    def test_unused_copy_with_another_spelling_is_a_duplicate_on_windows_only(self):
        scan = self.scan()
        scan["usage"] = {"s": ["k1", "k3"]}      # k2 (same file, other spelling) is not used
        win, mac = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.build", scan, {"platform": "win32"}),
                                                  call("TidyPlan.build", scan, {"platform": "darwin"})])

        def reasons(plan):
            return {r["nodeId"]: r["reason"] for r in plan["removals"]}
        self.assertEqual(reasons(win), {"k2": "duplicate"})
        self.assertEqual(reasons(mac), {"k2": "unused"})

    def test_reported_path_is_the_first_items_original_path(self):
        scan = self.scan()
        scan["items"][0], scan["items"][1] = scan["items"][1], scan["items"][0]
        win = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.build", scan, {"platform": "win32"})])[0]
        self.assertEqual(win["duplicates"][0]["path"], self.B)

    def test_same_spelling_groups_the_same_on_every_platform(self):
        scan = self.scan()
        scan["items"][1]["path"] = self.A
        out = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.build", scan, {"platform": p}) for p in ("win32", "darwin", None)])
        self.assertEqual(out[0], out[1])
        self.assertEqual(out[1], out[2])
        self.assertEqual(out[0]["duplicates"][0]["path"], self.A)


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyBackupNames(unittest.TestCase):
    YES = ["Main (Hush backup 10:00:00)", "Main (Hush cut 10:00:00)", "Main (WhyNot Hush backup 10:00:00)",
           "Main (WhyNot Hush cut 10:00:00)", "(Hush backup 1)"]
    NO = ["Main Hush backup 10:00:00", "Main (Hush backup)", "Main (Hush backup", "Main (WhyNot Tidy backup 10:00:00)",
          "Main (hush backup 10:00:00)", "Main (Hush cutting 10:00:00)", "Main (WhyNot  Hush cut 10:00:00)"]

    def test_regex(self):
        out = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.BACKUP.test", n) for n in self.YES + self.NO])
        self.assertEqual(out, [True] * len(self.YES) + [False] * len(self.NO))

    def test_all_four_names_are_backups_in_a_plan(self):
        names = ["Main (Hush backup 10:00:00)", "Main (Hush cut 10:05:00)", "Main (WhyNot Hush backup 10:10:00)",
                 "Main (WhyNot Hush cut 10:11:00)", "Main Hush backup 10:12:00"]
        scan = {"items": [seq("s%d" % i, n) for i, n in enumerate(names)], "bins": [], "usage": {}}
        plan = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.build", scan, {})])[0]
        self.assertEqual({r["nodeId"]: r["reason"] for r in plan["removals"]},
                         {"s0": "backup", "s1": "backup", "s2": "backup", "s3": "backup"})

    def test_media_used_only_inside_a_new_named_backup_is_unused(self):
        scan = {"items": [item("x1", "legacy.mp4", "/m/legacy.mp4"), item("x2", "new.mp4", "/m/new.mp4"),
                          item("x3", "kept.mp4", "/m/kept.mp4"),
                          seq("q1", "Main"), seq("q3", "Main (Hush backup 10:00:00)"), seq("q5", "Main (Hush cut 10:05:00)"),
                          seq("q6", "Main (WhyNot Hush backup 10:10:00)"), seq("q7", "Main (WhyNot Hush cut 10:11:00)")],
                "bins": [], "usage": {"q1": ["x3"], "q3": ["x1"], "q5": ["x1"], "q6": ["x2"], "q7": ["x2"]}}
        plan = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.build", scan, {})])[0]
        removed = {r["nodeId"]: r for r in plan["removals"]}
        self.assertNotIn("x3", removed)
        for nid in ("x1", "x2"):
            self.assertTrue(removed[nid]["checked"], nid)
            self.assertEqual(removed[nid]["reason"], "unused", nid)
        for nid in ("q3", "q5", "q6", "q7"):
            self.assertEqual(removed[nid]["reason"], "backup", nid)


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyNameHelpers(unittest.TestCase):
    def test_synced_name(self):
        pairs = [("Episode 12.prproj", []), ("Episode 12", []), ("Episode 12.prproj", ["Other"]),
                 ("Episode 12.prproj", ["Episode 12 - Synced"]),
                 ("Episode 12.prproj", ["Episode 12 - Synced", "Episode 12 - Synced 2"]),
                 ("Episode 12.prproj", ["Episode 12 - Synced", "Episode 12 - Synced 3"]),
                 ("", []), (None, ["Podcast - Synced"]), ("Episode 12.prproj", None), ("a.PRPROJ", []),
                 ("My.prproj.prproj", []), ("Cut v1.2.prproj", ["Cut v1.2 - Synced"])]
        out = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.syncedName", *p) for p in pairs])
        self.assertEqual(out, ["Episode 12 - Synced", "Episode 12 - Synced", "Episode 12 - Synced",
                               "Episode 12 - Synced 2", "Episode 12 - Synced 3", "Episode 12 - Synced 2",
                               "Podcast - Synced", "Podcast - Synced 2", "Episode 12 - Synced", "a.PRPROJ - Synced",
                               "My.prproj - Synced", "Cut v1.2 - Synced 2"])

    def test_temp_sync_and_tidy_backup_regexes(self):
        yes_temp = ["Tidy sync temp", "WhyNot Tidy sync temp"]
        no_temp = ["Tidy sync temp 2", "My Tidy sync temp", "tidy sync temp", "WhyNot  Tidy sync temp", "Tidy sync"]
        yes_bk = ["Main (Tidy backup 2026-10-12 1542).prproj", "Main (WhyNot Tidy backup 2026-10-12 1542).prproj"]
        no_bk = ["Main Tidy backup 2026", "Main (Hush backup 10:00:00)", "Main (tidy backup 1)", "Main (WhyNot Tidy backups)"]
        calls = [call("TidyPlan.TEMP_SYNC.test", n) for n in yes_temp + no_temp] + \
                [call("TidyPlan.TIDY_BACKUP.test", n) for n in yes_bk + no_bk]
        out = run_js(self, PORT, LOAD_PLAN, calls)
        self.assertEqual(out, [True] * len(yes_temp) + [False] * len(no_temp) + [True] * len(yes_bk) + [False] * len(no_bk))

    def test_tidy_backup_names_are_not_hush_backups(self):
        out = run_js(self, PORT, LOAD_PLAN, [call("TidyPlan.BACKUP.test", "Main (WhyNot Tidy backup 1)")])
        self.assertEqual(out, [False])


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class JscShimContract(unittest.TestCase):
    """adobe/tools/_harness/jsc_shim.js: jsc globals, exit codes, and a throwing test still delivers its output."""

    def shim(self, root, test_file):
        p = subprocess.run([NODE, str(SHIM), str(root), test_file], capture_output=True, text=True, encoding="utf-8",
                           timeout=120, cwd=str(root))
        return p.returncode, p.stdout, p.stderr

    def test_no_process_exit_call(self):
        # a pipe write is not synchronous everywhere: end through process.exitCode so stdout is never cut
        self.assertNotIn("process.exit(", text(SHIM))

    def test_a_throwing_test_keeps_its_output_and_exits_1(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "t.js").write_text(
                "for (var i = 0; i < 2000; i++) { print('PASS line ' + i); }\nthrow new Error('boom');\n", encoding="utf-8")
            rc, out, err = self.shim(td, "t.js")
        self.assertEqual(rc, 1)
        lines = out.split("\n")
        self.assertEqual((len(lines), lines[1999], lines[2000]), (2001, "PASS line 1999", ""))
        self.assertIn("boom", err)

    def test_unreadable_inputs_exit_2(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self.shim(td, "missing.js")[0], 2)
            p = subprocess.run([NODE, str(SHIM)], capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(p.returncode, 2)
            p = subprocess.run([NODE, str(SHIM), str(Path(td) / "nope"), "t.js"], capture_output=True, text=True,
                               encoding="utf-8", timeout=120)
            self.assertEqual(p.returncode, 2)

    def test_globals_of_jsc(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "d.txt").write_bytes("h\u00e9llo".encode("utf-8"))
            (Path(td) / "l.js").write_text("var LOADED = 7;\n", encoding="utf-8")
            (Path(td) / "t.js").write_text(
                "var window = this;\nload('l.js');\nvar b = readFile('d.txt', 'binary');\n"
                "print(window === this, typeof window.LOADED, LOADED, readFile('d.txt'), b.length, b[1], "
                "typeof b.slice, typeof require, typeof module);\n", encoding="utf-8")
            rc, out, err = self.shim(td, "t.js")
        self.assertEqual((rc, err), (0, ""))
        self.assertEqual(out, "true number 7 h\u00e9llo 6 195 function undefined undefined\n")


if __name__ == "__main__":
    unittest.main()
