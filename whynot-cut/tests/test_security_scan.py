# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 39 (L-T1): the local scan kit `tools/security/scan.py` (Addendum L §L3).

Case list: the lane's work folder `L-T1/cases.md` (written before the code). Planted samples are written into a temp
tree whose path has a space and Arabic letters, and are assembled from fragments here so that this very file holds no
secret-like or dangerous-looking text for the repo scan to find. Every planted line carries an `EXPECT: <rule ids>`
marker (`EXPECT-NEXT:` for the next line): the test compares the scanner's findings with those markers line by line,
so a rule that stops firing OR starts firing on a correct pattern fails here.
Tests that need an installed scanner skip with a clear reason when the tools home has none
(`python tools/security/install_tools.py` installs them); with WNC_REQUIRE_SCANNERS=1 (set at every gate) a missing
scanner FAILS the module instead of skipping. The missing-tool, wrong-version and altered-tool cases use a fake tools
home and always run.
Run:  tools/test.sh -p test_security_scan.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SEC = ROOT / "tools" / "security"
_sys.path.insert(0, str(SEC))

import fsutil  # noqa: E402
import install_tools as it  # noqa: E402
import scan  # noqa: E402

TOOLS_OK = not it.check_all()
NEEDS_TOOLS = unittest.skipUnless(TOOLS_OK, "scanners not installed: python tools/security/install_tools.py")


def setUpModule():
    if os.environ.get("WNC_REQUIRE_SCANNERS") == "1" and not TOOLS_OK:
        raise AssertionError("WNC_REQUIRE_SCANNERS=1 but the scanners are not installed/intact: %s" % it.check_all())


F = {  # fragments: keep dangerous-looking text out of this file
    "vf": "verify" + "=False",
    "ri": "Remove-" + "Item -Path x -" + "Recurse -Force",
    "rd": "r" + "d /s /q C:\\\\x",
    "rmrf": "r" + "m -" + "rf /tmp/x",
    "rm2": "r" + "m -f -" + "r /tmp/x",
    "rm3": "r" + "m --" + "recursive /tmp/x",
    "rd2": "r" + "d /q /" + "s C:\\\\x",
    "rd3": "d" + "el /f /" + "s C:\\\\x",
    "key": "AKIA" + "QYLPMN5HHHFPZAM2",
    "key2": "sk_live_" + "9f8e7d6c5b4a39281706f5e4d3c2b1a0",
    "pw": "hunter2" + "-Plant-Pw-98765",
    "inner": ".inner" + "HTML",
    "cn": "ssl.CERT" + "_NONE",
    "ins": "--" + "insecure",
    "wc": "WhyNot " + "Clients",
}

PY_PLANT = '''import os, ssl, subprocess, shutil, asyncio
from subprocess import Popen, call, check_call, check_output
from pathlib import Path
import requests, aiohttp, urllib3, httpx, truststore
from ssl import CERT_NONE  # EXPECT: wnc-tls-disabled


def tls(u, ctx):
    requests.get(u, %(vf)s)  # EXPECT: wnc-tls-disabled
    httpx.Client(verify=0)  # EXPECT: wnc-tls-disabled
    aiohttp.TCPConnector(ssl=False)  # EXPECT: wnc-tls-disabled
    urllib3.PoolManager(cert_reqs="CERT_NONE")  # EXPECT: wnc-tls-disabled
    ctx.check_hostname = False  # EXPECT: wnc-tls-disabled
    ctx.verify_mode = %(cn)s  # EXPECT: wnc-tls-disabled
    os.environ["PYTHONHTTPSVERIFY"] = "0"  # EXPECT: wnc-tls-disabled
    os.environ.update({"PYTHONHTTPSVERIFY": "0"})  # EXPECT: wnc-tls-disabled
    ssl._create_unverified_context()  # EXPECT: wnc-tls-disabled
    truststore.inject_into_ssl()  # EXPECT: wnc-tls-disabled
    subprocess.run(["/usr/bin/curl", "%(ins)s", u])  # EXPECT: wnc-tls-disabled
    os.system("curl %(ins)s https://x")  # EXPECT: wnc-tls-disabled wnc-shell-true
    s = requests.Session()
    s.verify = False  # EXPECT: wnc-tls-disabled


def shells(cmd):
    subprocess.run(cmd, shell=True)  # EXPECT: wnc-shell-true
    subprocess.run(cmd, shell=1)  # EXPECT: wnc-shell-true
    Popen(cmd, shell=True)  # EXPECT: wnc-shell-true
    subprocess.getoutput(cmd)  # EXPECT: wnc-shell-true
    os.system(cmd)  # EXPECT: wnc-shell-true
    os.popen(cmd)  # EXPECT: wnc-shell-true
    asyncio.create_subprocess_shell(cmd)  # EXPECT: wnc-shell-true


def deletes():
    return 'powershell -Command "%(ri)s"'  # EXPECT: wnc-remove-item-recurse


def deletes2():
    return "%(rd)s"  # EXPECT: wnc-recursive-delete-string


def deletes3():
    return "%(rmrf)s"  # EXPECT: wnc-recursive-delete-string


def deletes4():
    return ["%(rm2)s", "%(rm3)s", "%(rd2)s", "%(rd3)s"]  # EXPECT: wnc-recursive-delete-string


def clients(mode):
    with open(r"D:\\%(wc)s\\Acme\\assets\\a.txt", "w") as f:  # EXPECT: wnc-client-path-write
        f.write("x")
    open(r"D:\\%(wc)s\\Acme\\a.txt", mode)  # EXPECT: wnc-client-path-write
    Path("D:/%(wc)s/Acme/data/b.json").write_text("{}")  # EXPECT: wnc-client-path-write-nomode
    (Path("D:/%(wc)s/Acme") / "o.txt").write_text("x")  # EXPECT: wnc-client-path-write-nomode
    os.remove("D:/%(wc)s/Acme/c.txt")  # EXPECT: wnc-client-path-write-nomode
    shutil.copy("a", "D:/%(wc)s/Acme/c.txt")  # EXPECT: wnc-client-path-write-nomode
    shutil.rmtree(r"D:\\%(wc)s\\Acme")  # EXPECT: wnc-client-path-write-nomode
    Path("D:/%(wc)s/Acme").open("w")  # EXPECT: wnc-client-path-write
    open(file=r"D:\\%(wc)s\\Acme\\x", mode="w")  # EXPECT: wnc-client-path-write
    os.replace("tmp.json", "D:/%(wc)s/Acme/data/x.json")  # EXPECT: wnc-client-path-write-nomode
    Path("tmp.json").replace(Path("D:/%(wc)s/Acme/y.json"))  # EXPECT: wnc-client-path-write-nomode
    os.rename("a", "D:/%(wc)s/Acme/x")  # EXPECT: wnc-client-path-write-nomode
    shutil.move("a", "D:/%(wc)s/Acme/y")  # EXPECT: wnc-client-path-write-nomode
    Path("D:/%(wc)s/Acme/z").unlink()  # EXPECT: wnc-client-path-write-nomode
    Path("D:/%(wc)s/Acme/w").mkdir()  # EXPECT: wnc-client-path-write-nomode


def which_tools():
    shutil.which("icacls")  # EXPECT: wnc-which-system-tool
    shutil.which("whoami.exe")  # EXPECT: wnc-which-system-tool
    shutil.which("ping")  # EXPECT: wnc-which-system-tool


def exes(p):
    subprocess.run(["icacls", "x"], check=True)  # EXPECT: wnc-bare-executable
    subprocess.run(("whoami",), check=True)  # EXPECT: wnc-bare-executable
    subprocess.check_output(["ffprobe", "-i", "a"])  # EXPECT: wnc-bare-executable
    check_output(["ffprobe"])  # EXPECT: wnc-bare-executable
    subprocess.run("icacls x")  # EXPECT: wnc-bare-executable-string
    cmd = ["ffprobe", p]
    subprocess.run(cmd)  # EXPECT: wnc-bare-executable-var
    subprocess.run(["git"] + p)  # EXPECT: wnc-bare-executable
    cmd2 = ("git", p)
    subprocess.run(cmd2)  # EXPECT: wnc-bare-executable-var
    cmd3 = ["git", p]
    Popen(cmd3)  # EXPECT: wnc-bare-executable-var
    os.execvp("git", ["git"])  # EXPECT: wnc-bare-executable
    os.spawnlp(os.P_WAIT, "git", "git")  # EXPECT: wnc-bare-executable
    asyncio.create_subprocess_exec("git")  # EXPECT: wnc-bare-executable
    check_call(["git"])  # EXPECT: wnc-bare-executable
    call(["git"])  # EXPECT: wnc-bare-executable
    subprocess.run(args=["git"])  # EXPECT: wnc-bare-executable
    cmd4 = ["git"] + p
    subprocess.run(cmd4)  # EXPECT: wnc-bare-executable-var


def banditish(blob):
    import pickle, yaml
    eval(blob)
    pickle.loads(blob)
    yaml.load(blob)
    password = "%(pw)s"
    return password
''' % F

PY_OK = '''import os, shutil, ssl, subprocess, sys, tempfile
from pathlib import Path


def n1(exe_abs, f):
    subprocess.run([exe_abs, "-i", f], shell=False)
    subprocess.run([sys.executable, "-c", "pass"])
    subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32" / "icacls.exe"), "x"])
    subprocess.run(["/usr/bin/git", "status"], shell=False)
    subprocess.run(["C:\\\\Windows\\\\System32\\\\whoami.exe"], shell=0)


def n2(requests, u, ctx):
    ssl.create_default_context()
    requests.get(u, verify=True, timeout=5)
    requests.get(u, verify=ctx, timeout=5)


def n4():
    # a comment that names Remove-Item and its recurse flag is not code
    x = "Remove-Item -LiteralPath x"  # and a trailing comment about Remove-Item -Recurse is not code either
    return x


def n6():
    msg = "git rm -r --cached x"
    quoted = "D:/%(wc)s/Acme/x".replace("/", os.sep)
    flag = 1  # "%(ins)s" quoted in a trailing comment is not code
    return shutil.which("git"), shutil.which("ffmpeg"), msg, quoted, flag


def n5(client_dir, out_dir):
    with open(Path(client_dir) / "a.txt", "rb") as f:
        f.read()
    with open(Path(out_dir) / "output" / "b.txt", "w") as g:
        g.write("x")
    with open(r"D:\\%(wc)s\\Acme\\assets\\a.txt", "r") as h:
        h.read()
    with open(r"D:\\%(wc)s\\Acme\\assets\\a.txt", "rb") as h2:
        h2.read()
    with tempfile.TemporaryDirectory() as d:
        Path(d, "t").write_text("x")
    Path(r"D:\\ClaudeData\\Temp\\x.txt").write_text("x")
''' % F

JS_PLANT = '''const cp = require("child_process");
function p3(el, userText, u, parts, kit, range, iframe, agent) {
  el%(inner)s = userText;  // EXPECT: wnc-raw-innerhtml
  el.insertAdjacentHTML("beforeend", userText);  // EXPECT: wnc-raw-innerhtml
  el%(inner)s = "<b>" + userText + "</b>";  // EXPECT: wnc-raw-innerhtml
  el%(inner)s = `<b>${userText}</b>`;  // EXPECT: wnc-raw-innerhtml
  el%(inner)s = esc(userText) + u;  // EXPECT: wnc-raw-innerhtml
  el%(inner)s = parts.join("");  // EXPECT: wnc-raw-innerhtml
  el%(inner)s = kit.trusted(u);  // EXPECT: wnc-raw-innerhtml
  el%(inner)s = renderUnsafe(u);  // EXPECT: wnc-raw-innerhtml
  el%(inner)s += u;  // EXPECT: wnc-raw-innerhtml
  el["innerHTML"] = u;  // EXPECT: wnc-raw-innerhtml
  el.outerHTML += u;  // EXPECT: wnc-raw-innerhtml
  el.setAttribute("srcdoc", u);  // EXPECT: wnc-raw-innerhtml
  iframe.srcdoc = u;  // EXPECT: wnc-raw-innerhtml
  el.setHTMLUnsafe(u);  // EXPECT: wnc-raw-innerhtml
  range.createContextualFragment(u);  // EXPECT: wnc-raw-innerhtml
  Object.assign(el, { innerHTML: u });  // EXPECT: wnc-raw-innerhtml
}
function p5js(cmd, agent) {
  cp.exec(cmd);  // EXPECT: wnc-js-shell-exec-receiver
  this.cp.exec(cmd);  // EXPECT: wnc-js-shell-exec-receiver
  deps.childProcess.exec(cmd);  // EXPECT: wnc-js-shell-exec-receiver
  sh.exec(cmd);  // EXPECT: wnc-js-shell-exec-receiver
  cep_node.require("child_process").exec(cmd);  // EXPECT: wnc-js-shell-exec
  spawn("x", { env: { NODE_TLS_REJECT_UNAUTHORIZED: "0" } });  // EXPECT: wnc-js-tls-disabled
  cp.execSync(cmd);  // EXPECT: wnc-js-shell-exec-receiver
  require("child_process").exec(cmd);  // EXPECT: wnc-js-shell-exec
  execSync(cmd);  // EXPECT: wnc-js-shell-exec
  cp.spawn("x", [], { shell: true });  // EXPECT: wnc-js-shell-exec
  require("https").request({ rejectUnauthorized: false });  // EXPECT: wnc-js-tls-disabled
  agent.options.rejectUnauthorized = false;  // EXPECT: wnc-js-tls-disabled
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = 0;  // EXPECT: wnc-js-tls-disabled
  process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";  // EXPECT: wnc-js-tls-disabled
}
''' % F

JS_OK = '''function n3(el, x, kit) {
  el.textContent = x;
  el%(inner)s = "";
  el%(inner)s = "<b>fixed</b>";
  el%(inner)s = trusted("<b>x</b>");
  el%(inner)s = renderError(a, b);
  el%(inner)s = renderLoading(strings);
  el%(inner)s = render(view(s), strings(), ui);
  el%(inner)s = esc(x);
  el%(inner)s = Html.trusted("<i>x</i>");
  cp.execFile("/usr/bin/x", [x]);
  const m = /^a(b)/.exec(x);
  const k = this.re.exec(x);
  const n = LATIN.exec(x);
  while ((m2 = TOKEN.exec(x))) { x = x.slice(1); }
}
function exec(a) { return a; }
exec(1);
''' % F

JS_ESM = '''import { exec } from "child_process";
export function run(cmd) {
  exec(cmd);  // EXPECT: wnc-js-shell-exec-receiver
}
export function run2(cmd) {
  const { execSync: es } = require("child_process");
  es(cmd);  // EXPECT: wnc-js-shell-exec-receiver
}
'''

PS_PLANT = '''# %(ri)s in a comment must not fire
Remove-Item -LiteralPath $p
Remove-Item -Path $p -Recurse -Force  # EXPECT: wnc-ps-remove-item-recurse
Remove-Item $p -r  # EXPECT: wnc-ps-remove-item-recurse
Remove-Item $p -Rec  # EXPECT: wnc-ps-remove-item-recurse
# EXPECT-NEXT: wnc-ps-remove-item-recurse
Remove-Item $p `
   -Recurse
# EXPECT-NEXT: wnc-ps-remove-item-recurse
Remove-Item $p `
-Recurse
# EXPECT-NEXT: wnc-ps-remove-item-recurse
Remove-Item `
  -Path $p `
  -Recurse
git rm -r --cached x
$rd = $s -replace 'a','b'
Write-Host del.txt -Raw
rm -r $q  # EXPECT: wnc-ps-rm-rf-alias
ri $q -Recurse  # EXPECT: wnc-ps-rm-rf-alias
''' % F

SH_PLANT = '''#!/bin/sh
rm -rf /tmp/x  # EXPECT: wnc-sh-rm-rf
rm -R /tmp/x  # EXPECT: wnc-sh-rm-rf
rm -f -r /tmp/x  # EXPECT: wnc-sh-rm-rf
rm --recursive /tmp/x  # EXPECT: wnc-sh-rm-rf
rm --force --recursive /tmp/x  # EXPECT: wnc-sh-rm-rf
rm -f /tmp/x
# rm -rf in a comment
'''

SECRET_PLANT ='aws_access_key_id = "%(key)s"\nstripe = "%(key2)s"\n' % F

EXPECT_RE = re.compile(r"EXPECT(-NEXT)?:\s*([A-Za-z0-9_ -]+?)\s*$")


def write_tree(base: Path) -> Path:
    d = base / "مشروع تجريبي" / "a b"
    d.mkdir(parents=True)
    for name, text in (("plants.py", PY_PLANT), ("ok.py", PY_OK), ("plants.js", JS_PLANT), ("ok.js", JS_OK),
                       ("plants.ps1", PS_PLANT), ("plants_esm.mjs", JS_ESM), ("plants.sh", SH_PLANT), ("secret.py", SECRET_PLANT)):
        (d / name).write_text(text, encoding="utf-8", newline="\n")
    return base


def expectations(text):
    """{line number: set of rule ids} from the EXPECT markers of a planted file."""
    out, nxt = {}, None
    for n, ln in enumerate(text.splitlines(), 1):
        m = EXPECT_RE.search(ln)
        if nxt is not None:
            out.setdefault(n, set()).update(nxt)
            nxt = None
        if m:
            rules = set(m.group(2).split())
            if m.group(1):
                nxt = rules
            else:
                out.setdefault(n, set()).update(rules)
    return out


def ours(findings, fname):
    out = {}
    for f in findings:
        if f["file"].split("/")[-1] == fname and f["tool"] == "semgrep" and f["rule"].startswith("wnc-"):
            out.setdefault(f["line"], set()).add(f["rule"])
    return out


def by_file(results, tool=None):
    out = {}
    for r in results:
        if tool and r["tool"] != tool:
            continue
        for f in r["findings"]:
            out.setdefault(f["file"].split("/")[-1], []).append(f)
    return out


def tree_text(raw: Path):
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(raw.rglob("*.json")))


class PlantedSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.root = write_tree(Path(cls._td.name))
        cls.raw = Path(cls._td.name) / "raw"
        cls.raw.mkdir()
        cls.sg = cls.bd = cls.gl = None
        if TOOLS_OK:
            cls.sg = scan.scan_semgrep(cls.root, cls.raw, offline=True)
            cls.bd = scan.scan_bandit(cls.root, cls.raw)
            cls.gl = scan.scan_gitleaks(cls.root, cls.raw)
        cls.files = {n: (cls.root / "مشروع تجريبي" / "a b" / n).read_text(encoding="utf-8") for n in
                     ("plants.py", "ok.py", "plants.js", "ok.js", "plants.ps1", "plants_esm.mjs", "plants.sh")}

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    @NEEDS_TOOLS
    def test_semgrep_ran_in_degraded_rules_only_mode_and_said_so(self):
        self.assertEqual(self.sg["status"], "DEGRADED", self.sg["note"])
        self.assertIn("NOT run", self.sg["note"])
        self.assertIn("files scanned", self.sg["note"])

    def _compare(self, fname):
        want = expectations(self.files[fname])
        got = ours(self.sg["findings"], fname)
        missing = {n: r - got.get(n, set()) for n, r in want.items() if r - got.get(n, set())}
        extra = {n: r - want.get(n, set()) for n, r in got.items() if r - want.get(n, set())}
        lines = self.files[fname].splitlines()
        self.assertEqual(missing, {}, "planted lines NOT caught: " + "; ".join("%d %s: %s" % (n, sorted(r), lines[n - 1].strip()[:70]) for n, r in missing.items()))
        self.assertEqual(extra, {}, "unexpected findings on planted lines: " + "; ".join("%d %s: %s" % (n, sorted(r), lines[n - 1].strip()[:70]) for n, r in extra.items()))

    @NEEDS_TOOLS
    def test_every_python_plant_line_is_caught_by_the_expected_rule_and_nothing_else_fires(self):
        self._compare("plants.py")

    @NEEDS_TOOLS
    def test_every_js_plant_line_is_caught_by_the_expected_rule_and_nothing_else_fires(self):
        self._compare("plants.js")

    @NEEDS_TOOLS
    def test_an_exec_imported_from_child_process_is_caught_but_a_local_exec_function_is_not(self):
        self._compare("plants_esm.mjs")

    @NEEDS_TOOLS
    def test_shell_script_recursive_deletes_are_caught_but_not_a_comment(self):
        self._compare("plants.sh")

    @NEEDS_TOOLS
    def test_every_powershell_plant_line_is_caught_but_not_the_comment_or_literalpath(self):
        self._compare("plants.ps1")

    @NEEDS_TOOLS
    def test_our_correct_patterns_do_not_fire(self):
        fs = by_file([self.sg, self.bd])
        self.assertEqual([(f["tool"], f["rule"], f["line"]) for f in fs.get("ok.py", [])], [])
        self.assertEqual([(f["tool"], f["rule"], f["line"]) for f in fs.get("ok.js", [])], [])

    @NEEDS_TOOLS
    def test_bandit_catches_eval_pickle_yaml_and_the_hardcoded_password(self):
        got = {f["rule"] for f in by_file([self.bd])["plants.py"]}
        self.assertTrue({"B307", "B301", "B506", "B105"} <= got, got)

    @NEEDS_TOOLS
    def test_bandit_skips_subprocess_import_and_call_by_rule(self):
        got = {f["rule"] for f in by_file([self.bd])["plants.py"]}
        self.assertFalse({"B404", "B603"} & got, got)

    @NEEDS_TOOLS
    def test_gitleaks_catches_the_fake_keys_and_never_returns_the_values(self):
        fs = by_file([self.gl])["secret.py"]
        self.assertGreaterEqual(len(fs), 1)
        blob = json.dumps(self.gl) + (self.raw / "gitleaks-tree.json").read_text(encoding="utf-8")
        self.assertNotIn(F["key"], blob)
        self.assertNotIn(F["key2"], blob)
        self.assertNotIn("9f8e7d6c5b4a3928", blob)

    @NEEDS_TOOLS
    def test_no_planted_secret_or_source_text_is_kept_in_any_raw_json(self):
        text = tree_text(self.raw) + json.dumps([self.sg, self.bd, self.gl])
        for v in (F["key"], F["key2"], F["pw"], "9f8e7d6c5b4a3928"):
            self.assertNotIn(v, text)
        self.assertNotIn('"code"', (self.raw / "bandit.json").read_text(encoding="utf-8"))
        sj = json.loads((self.raw / "semgrep.json").read_text(encoding="utf-8"))
        for r in sj["results"]:
            self.assertNotIn("lines", r["extra"])
            self.assertNotIn("metavars", r["extra"])

    @NEEDS_TOOLS
    def test_paths_with_space_and_arabic_survive_in_findings(self):
        files = {f["file"] for r in (self.sg, self.bd, self.gl) for f in r["findings"]}
        self.assertTrue(any("مشروع تجريبي/a b/plants.py" in f for f in files), files)

    @NEEDS_TOOLS
    def test_two_identical_flagged_lines_get_different_stable_fingerprints(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "tree"
            root.mkdir()
            body = "import requests\n\n\ndef a(u):\n    requests.get(u, %s)\n\n\ndef b(u):\n    requests.get(u, %s)\n" % (F["vf"], F["vf"])
            (root / "x.py").write_text(body, encoding="utf-8")
            raw = Path(d) / "raw"
            raw.mkdir()
            r1 = scan.scan_semgrep(root, raw, offline=True)
            fp1 = [f["fingerprint"] for f in r1["findings"] if f["rule"] == "wnc-tls-disabled"]
            self.assertEqual(len(fp1), 2)
            self.assertEqual(len(set(fp1)), 2)
            (root / "x.py").write_text("# moved down\n\n\n" + body, encoding="utf-8")
            r2 = scan.scan_semgrep(root, raw, offline=True)
            fp2 = [f["fingerprint"] for f in r2["findings"] if f["rule"] == "wnc-tls-disabled"]
            self.assertEqual(fp1, fp2, "a line move changed the fingerprint")

    def test_nosec_without_a_reason_is_a_finding_with_a_reason_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "t"
            root.mkdir()
            (root / "n.py").write_text("a = 1  # nosec\nb = 2  # nosec B101\nc = 3  # nosec B101 - fixed list, no user input\n"
                                       "d = 4  # nosec: the value comes from our own constant\n", encoding="utf-8")
            fs = scan.check_nosec(root, [root])
            self.assertEqual(sorted(f["line"] for f in fs), [1, 2])


class ToolRobustness(unittest.TestCase):
    def setUp(self):
        scan._STATE_CACHE.clear()
        self.addCleanup(scan._STATE_CACHE.clear)

    def test_missing_tool_is_a_clear_message_not_a_pass(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"WNC_SEC_TOOLS": d}):
            for name in ("semgrep", "bandit", "gitleaks", "pip-audit", "osv-scanner"):
                r = scan.need(name)
                self.assertEqual(r["status"], "MISSING", name)
                self.assertIn("MISSING " + name, r["note"])
                self.assertIn("install_tools.py", r["note"])
            self.assertEqual(scan.exit_code([scan.need("gitleaks")], []), scan.EXIT_TOOL)

    def _fake_gitleaks(self, d, version_output):
        """A tools home with a gitleaks whose manifest matches its bytes, so only the version can be wrong."""
        home = Path(d)
        exe = scan.tool_exe("gitleaks")
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"fake gitleaks binary")
        (home / "manifest.json").write_text(json.dumps({"gitleaks": {
            "version": "x", "archive_sha256": "0", "exe": exe.name, "exe_sha256": hashlib.sha256(b"fake gitleaks binary").hexdigest()}}),
            encoding="utf-8")
        real_versions = it.versions

        def unpinned():  # the fake binary is not the official one: drop the pinned exe sha256 so only the version can be wrong
            v = real_versions()
            for spec in v["binaries"]["gitleaks"]["platforms"].values():
                spec.pop("exe_sha256", None)
            return v
        self.enterContext(mock.patch.object(it, "versions", side_effect=unpinned))
        return mock.patch.object(scan, "run", return_value=(0, version_output, ""))

    def test_wrong_version_is_a_mismatch_message(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"WNC_SEC_TOOLS": d}), self._fake_gitleaks(d, "1.0.0\n"):
            st, found, msg = scan.tool_state("gitleaks")
            self.assertEqual(st, "mismatch")
            self.assertEqual(found, "1.0.0")
            self.assertIn("pinned 8.30.1, found 1.0.0", msg)

    def test_unparseable_version_output_is_a_mismatch_not_a_pass(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"WNC_SEC_TOOLS": d}), self._fake_gitleaks(d, "garbage\n"):
            self.assertEqual(scan.tool_state("gitleaks")[0], "mismatch")

    def test_the_right_version_is_ok(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"WNC_SEC_TOOLS": d}), self._fake_gitleaks(d, "8.30.1\n"):
            self.assertEqual(scan.tool_state("gitleaks")[0], "ok")

    def test_a_binary_altered_after_install_is_refused_before_it_is_run(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"WNC_SEC_TOOLS": d}), self._fake_gitleaks(d, "8.30.1\n") as run_mock:
            scan.tool_exe("gitleaks").write_bytes(b"tampered")
            st, found, msg = scan.tool_state("gitleaks")
            self.assertEqual(st, "altered")
            self.assertIn("ALTERED gitleaks", msg)
            run_mock.assert_not_called()
            self.assertEqual(scan.exit_code([scan.need("gitleaks")], []), scan.EXIT_TOOL)

    def test_python_tool_integrity_checks_the_wheel_record(self):
        import base64
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "venv" / "Lib" / "site-packages"
            (sp / "demo-1.0.dist-info").mkdir(parents=True)
            (sp / "demo.py").write_bytes(b"print('hi')\n")
            dig = base64.urlsafe_b64encode(hashlib.sha256(b"print('hi')\n").digest()).rstrip(b"=").decode()
            (sp / "demo-1.0.dist-info" / "RECORD").write_text("demo.py,sha256=%s,12\ndemo-1.0.dist-info/RECORD,,\n" % dig, encoding="utf-8")
            self.assertIsNone(it.verify_python_tool("demo", d))
            (sp / "demo.py").write_bytes(b"print('evil')\n")
            self.assertIn("altered", it.verify_python_tool("demo", d))
            (sp / "demo.py").unlink()
            self.assertIn("missing", it.verify_python_tool("demo", d))

    def test_version_parse_of_every_tool_matches_the_pin_format(self):
        samples = {"semgrep": "1.179.0\n", "bandit": "bandit 1.9.4\n  python version = 3.13.2\n",
                   "pip-audit": "pip-audit 2.10.1\n", "gitleaks": "8.30.1\n",
                   "osv-scanner": "osv-scanner version: 2.6.0\nosv-scalibr version: 0.5.2\n"}
        for name, text in samples.items():
            m = re.search(scan.VERSION_RE[name], text, re.M)
            self.assertEqual(m.group(1), scan.pinned_version(name), name)

    def test_offline_flag_and_env(self):
        self.assertTrue(scan.is_offline(True))
        with mock.patch.dict(os.environ, {"WNC_SCAN_OFFLINE": "1"}):
            self.assertTrue(scan.is_offline(False))

    def test_offline_deps_is_a_stated_degraded_mode_with_exit_3_through_the_cli(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "tree"
            (root / "whynot-cut" / "setup" / "locks").mkdir(parents=True)
            (root / "whynot-cut" / "setup" / "locks" / "runtime-x.lock").write_text("a==1 \\\n    --hash=sha256:" + "a" * 64 + "\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = scan.main(["--deps", "--offline", "--root", str(root), "--out", str(Path(d) / "o"), "--raw", str(Path(d) / "r")])
            self.assertEqual(code, scan.EXIT_DEGRADED, buf.getvalue())
            for t in ("pip-audit", "osv-scanner", "npm-audit"):
                self.assertRegex(buf.getvalue(), r"%s\s+DEGRADED" % t)
            self.assertIn("NOT checked", buf.getvalue())

    def test_exit_code_priorities(self):
        ok = scan.result("a", "OK")
        self.assertEqual(scan.exit_code([ok], []), 0)
        self.assertEqual(scan.exit_code([ok, scan.result("b", "DEGRADED")], []), 3)
        for st in ("FAILED", "MISSING", "MISMATCH", "ALTERED"):
            self.assertEqual(scan.exit_code([ok, scan.result("b", st)], []), 4, st)
        self.assertEqual(scan.exit_code([ok, scan.result("b", "FAILED")], [{"severity": "HIGH"}]), 1)

    def test_commands_are_lists_absolute_no_shell_and_metrics_off(self):
        argv = scan.semgrep_argv(Path("x"), Path("r"), Path("o.json"), registry=True)
        self.assertIn("--metrics=off", argv)
        self.assertIn("--disable-version-check", argv)
        self.assertTrue(os.path.isabs(argv[0]))
        for pack in scan.REGISTRY_PACKS:
            self.assertIn(pack, argv)
        self.assertNotIn("--config=auto", argv)
        with self.assertRaises(ValueError):
            scan.run(["semgrep", "--version"])  # a bare name is refused (planted-binary class, L-G11), also under python -O
        g = scan.gitleaks_argv(Path("x"), Path("o"), history=True)
        self.assertIn("--redact", g)
        self.assertEqual(g[1], "git")
        t = scan.gitleaks_argv(Path("x"), Path("o"))
        self.assertEqual(t[1], "dir")
        self.assertIn("--max-archive-depth", t)

    def test_environment_is_cleaned_cached_on_the_tools_home_and_free_of_semgrep_credentials(self):
        with mock.patch.dict(os.environ, {"SEMGREP_" + "APP_TOKEN": "tok", "SEMGREP_RULES": "x"}):
            env = scan.clean_env()
        self.assertEqual(env["SEMGREP_SEND_METRICS"], "off")
        self.assertNotIn("SEMGREP_" + "APP_TOKEN", env)
        self.assertNotIn("SEMGREP_RULES", env)
        home = str(scan.tools_home())
        for k in ("PIP_CACHE_DIR", "XDG_CACHE_HOME", "SEMGREP_SETTINGS_FILE"):
            self.assertTrue(env[k].startswith(home), (k, env[k]))

    def test_no_upload_flags_anywhere(self):
        text = (SEC / "scan.py").read_text(encoding="utf-8")
        for bad in ("--upload", "semgrep ci", "--publish", "--pro"):
            self.assertNotIn(bad, text)

    def test_the_scan_never_resolves_a_program_from_the_current_folder(self):
        with tempfile.TemporaryDirectory() as d:
            planted = Path(d) / ("npm.cmd" if os.name == "nt" else "npm")
            planted.write_text("echo planted\n", encoding="utf-8")
            planted.chmod(0o755)
            old = os.getcwd()
            os.chdir(d)
            try:
                with mock.patch.dict(os.environ, {"PATH": os.pathsep.join([".", d, "relative" + os.sep + "bin"])}):
                    self.assertIsNone(fsutil.which_safe("npm"))
            finally:
                os.chdir(old)

    def test_main_turns_a_tool_timeout_or_odd_baseline_into_a_clear_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d) / "b.json"
            b.write_text("[1, 2]", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(scan.main(["--locks", "--baseline", str(b), "--root", d, "--raw", d, "--no-report"]), scan.EXIT_USAGE)
            self.assertIn("JSON object", err.getvalue())
            with mock.patch.object(scan, "run_scans", side_effect=subprocess.TimeoutExpired("x", 1)), \
                    contextlib.redirect_stderr(io.StringIO()) as err2:
                self.assertEqual(scan.main(["--locks", "--root", d, "--raw", d, "--no-report", "--baseline", str(Path(d) / "none.json")]), scan.EXIT_TOOL)
            self.assertIn("SCAN ERROR", err2.getvalue())

    def test_cli_output_with_arabic_paths_survives_a_cp1252_console(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "مشروع" / "x y"
            (root / "whynot-cut" / "setup" / "locks").mkdir(parents=True)
            (root / "whynot-cut" / "setup" / "locks" / "runtime-x.lock").write_text("bad==1.0\n", encoding="utf-8")
            env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0", PYTHONLEGACYWINDOWSSTDIO="1")
            p = subprocess.run([_sys.executable, str(SEC / "scan.py"), "--locks", "--root", str(root), "--out", str(Path(d) / "o"),
                                "--raw", str(Path(d) / "r"), "--baseline", str(Path(d) / "none.json")], capture_output=True, env=env)
            self.assertEqual(p.returncode, scan.EXIT_FINDINGS, p.stderr.decode("utf-8", "replace")[-400:])
            self.assertNotIn(b"Traceback", p.stderr)
            self.assertTrue(list((Path(d) / "o").glob("scan-*.md")), "the report must be written")


class Baseline(unittest.TestCase):
    def _f(self, sev="HIGH", rule="wnc-x", file="a.py", key="k"):
        return scan.finding("semgrep", rule, sev, file, 3, "msg", key)

    def _write(self, d, entries, gaps=None):
        p = Path(d) / "baseline.json"
        body = {"accepted": entries}
        if gaps is not None:
            body["known_gaps"] = gaps
        p.write_text(json.dumps(body), encoding="utf-8")
        return p

    def _entry(self, f, **kw):
        e = {"fingerprint": f["fingerprint"], "tool": f["tool"], "rule": f["rule"], "file": f["file"],
             "reason": "planted sample", "owner_task": "L-T1", "review_date": "2099-01-01"}
        e.update(kw)
        return e

    def test_new_high_blocks_and_baselined_high_does_not(self):
        f = self._f()
        with tempfile.TemporaryDirectory() as d:
            new, acc, exp = scan.split_by_baseline([f], scan.load_baseline(self._write(d, [])))
            self.assertEqual((len(new), len(acc)), (1, 0))
            new, acc, exp = scan.split_by_baseline([f], scan.load_baseline(self._write(d, [self._entry(f)])))
            self.assertEqual((len(new), len(acc)), (0, 1))

    def test_entry_without_reason_owner_or_date_is_refused(self):
        f = self._f()
        with tempfile.TemporaryDirectory() as d:
            for field in ("reason", "owner_task", "review_date"):
                with self.assertRaises(scan.BaselineError):
                    scan.load_baseline(self._write(d, [self._entry(f, **{field: "  "})]))
            with self.assertRaises(scan.BaselineError):
                scan.load_baseline(self._write(d, [self._entry(f, review_date="soon")]))

    def test_overdue_review_is_reported(self):
        f = self._f()
        with tempfile.TemporaryDirectory() as d:
            b = scan.load_baseline(self._write(d, [self._entry(f, review_date="2020-01-01")]))
            new, acc, exp = scan.split_by_baseline([f], b, today=datetime.date(2026, 10, 17))
            self.assertEqual(len(exp), 1)
            self.assertIn("REVIEW OVERDUE", scan.render_report([scan.result("semgrep", "OK", [f])], new, acc, exp, "t", ".",
                                                               datetime.date(2026, 10, 17)))

    def test_fingerprint_survives_a_line_move_but_not_a_code_change(self):
        a = scan.finding("semgrep", "r", "HIGH", "a.py", 10, "m", scan.norm_code("x = 1\n  y"))
        b = scan.finding("semgrep", "r", "HIGH", "a.py", 99, "m", scan.norm_code("x = 1 y"))
        c = scan.finding("semgrep", "r", "HIGH", "a.py", 10, "m", scan.norm_code("x = 2 y"))
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertNotEqual(a["fingerprint"], c["fingerprint"])

    def test_occurrence_numbers_separate_identical_lines(self):
        fs = scan.number_occurrences([(scan.finding("semgrep", "r", "HIGH", "a.py", n, "m", "k"), "same") for n in (1, 2, 3)])
        self.assertEqual(len({f["fingerprint"] for f in fs}), 3)

    def test_medium_and_below_never_block(self):
        f = self._f(sev="MEDIUM")
        new, _, _ = scan.split_by_baseline([f], {})
        self.assertEqual([x for x in new if x["severity"] in scan.BLOCKING], [])

    def test_severity_mapping(self):
        self.assertEqual(scan.cvss_to_sev("9.8"), "CRITICAL")
        self.assertEqual(scan.cvss_to_sev("7.5"), "HIGH")
        self.assertEqual(scan.cvss_to_sev("5.3"), "MEDIUM")
        self.assertEqual(scan.cvss_to_sev("2"), "LOW")
        self.assertEqual(scan.cvss_to_sev(None), "HIGH")  # unrated = High until triaged

    def test_cli_bad_baseline_exits_2_and_no_mode_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "b.json"
            p.write_text("{not json", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(scan.main(["--locks", "--baseline", str(p), "--root", d, "--raw", d, "--no-report"]), scan.EXIT_USAGE)
                self.assertEqual(scan.main(["--root", d]), scan.EXIT_USAGE)

    def test_a_degraded_scanner_passes_only_with_a_known_gap_entry_that_has_reason_owner_date(self):
        deg = [scan.result("eslint", "DEGRADED", note="plugins not installed", codes=["plugins-missing"])]
        self.assertEqual(scan.exit_code(deg, []), scan.EXIT_DEGRADED)
        gap = {"tool": "eslint", "code": "plugins-missing", "reason": "devDependencies patch pending", "owner_task": "Adobe track",
               "review_date": "2099-01-01"}
        with tempfile.TemporaryDirectory() as d:
            acc, gaps = scan.load_baseline_full(self._write(d, [], [gap]))
            scan.apply_known_gaps(deg, gaps)
            self.assertEqual(scan.exit_code(deg, []), scan.EXIT_OK)
            self.assertIn("accepted gap", scan.render_report(deg, [], [], [], "t", ".", datetime.date(2026, 10, 17)))
            for field in ("reason", "owner_task", "review_date", "code"):
                with self.assertRaises(scan.BaselineError):
                    scan.load_baseline_full(self._write(d, [], [dict(gap, **{field: ""})]))
            with self.assertRaises(scan.BaselineError):
                scan.load_baseline_full(self._write(d, [], [dict(gap, code="anything")]))  # only the known reason codes
        failed = [scan.result("eslint", "FAILED")]  # a gap never excuses a missing or failed tool
        scan.apply_known_gaps(failed, {("eslint", "plugins-missing"): gap})
        self.assertEqual(scan.exit_code(failed, []), scan.EXIT_TOOL)

    def test_a_gap_accepts_only_its_own_reason_code_not_the_whole_tool(self):
        gap = {"tool": "semgrep", "code": "offline", "reason": "no network on this PC", "owner_task": "executor", "review_date": "2099-01-01"}
        with tempfile.TemporaryDirectory() as d:
            _, gaps = scan.load_baseline_full(self._write(d, [], [gap]))
        offline = [scan.result("semgrep", "DEGRADED", codes=["offline"])]
        both = [scan.result("semgrep", "DEGRADED", codes=["offline", "scan-errors"])]
        none = [scan.result("semgrep", "DEGRADED")]  # a degraded result without a reason code is never accepted
        for r in (offline, both, none):
            scan.apply_known_gaps(r, gaps)
        self.assertEqual(scan.exit_code(offline, []), scan.EXIT_OK)
        self.assertEqual(scan.exit_code(both, []), scan.EXIT_DEGRADED)
        self.assertEqual(scan.exit_code(none, []), scan.EXIT_DEGRADED)

    def test_wrongly_typed_baseline_fields_are_a_baseline_error_not_a_traceback(self):
        f = self._f()
        with tempfile.TemporaryDirectory() as d:
            for body in ({"accepted": None}, {"accepted": "x"}, {"accepted": [], "known_gaps": {}}, {"accepted": [5]},
                         {"accepted": [dict(self._entry(f), review_date=20261001)]}, {"accepted": [dict(self._entry(f), reason=7)]}):
                p = Path(d) / "b.json"
                p.write_text(json.dumps(body), encoding="utf-8")
                with self.assertRaises(scan.BaselineError, msg=str(body)[:60]):
                    scan.load_baseline_full(p)
            with contextlib.redirect_stderr(io.StringIO()):
                (Path(d) / "b.json").write_text(json.dumps({"accepted": None}), encoding="utf-8")
                self.assertEqual(scan.main(["--locks", "--baseline", str(Path(d) / "b.json"), "--root", d, "--raw", d, "--no-report"]), scan.EXIT_USAGE)


class EmptyInputIsNotAPass(unittest.TestCase):
    def test_no_locks_is_a_failure_for_every_dependency_check(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(scan.check_locks(root)["status"], "FAILED")
            self.assertEqual(scan.scan_sbom(root, root)["status"], "FAILED")
            if TOOLS_OK:
                self.assertEqual(scan.scan_pip_audit(root, root, [])["status"], "FAILED")
                self.assertEqual(scan.scan_osv(root, root, [], [])["status"], "FAILED")

    @NEEDS_TOOLS
    def test_bandit_on_the_real_layout_fails_when_a_configured_folder_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "whynot-cut" / "engine").mkdir(parents=True)
            (root / "whynot-cut" / "engine" / "a.py").write_text("x = 1\n", encoding="utf-8")
            r = scan.scan_bandit(root, root)
            self.assertEqual(r["status"], "FAILED")
            self.assertIn("whynot-cut/installer/core", r["note"])

    def test_the_configured_bandit_folders_exist_in_the_real_repo(self):
        for d in scan.BANDIT_DIRS:
            self.assertTrue((ROOT / d).is_dir(), d)

    @NEEDS_TOOLS
    def test_semgrep_that_scans_no_file_is_a_failure(self):
        with tempfile.TemporaryDirectory() as d:
            r = scan.scan_semgrep(Path(d), Path(d), offline=True)
            self.assertEqual(r["status"], "FAILED")
            self.assertIn("0 files", r["note"])

    def test_pip_audit_skipped_requirements_degrade_the_status(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(scan, "need", return_value=None), \
                mock.patch.object(scan, "run") as run_mock:
            lock = Path(d) / "a.lock"
            lock.write_text("x\n", encoding="utf-8")

            def fake(argv, cwd=None, **kw):
                Path(argv[argv.index("-o") + 1]).write_text(json.dumps({"dependencies": [{"name": "x", "skip_reason": "could not deduce"}]}), encoding="utf-8")
                return 0, "", ""
            run_mock.side_effect = fake
            r = scan.scan_pip_audit(Path(d), Path(d), [lock])
            self.assertEqual(r["status"], "DEGRADED")
            self.assertIn("NOT audited", r["note"])


class LockHashes(unittest.TestCase):
    def test_real_locks_all_hashed(self):
        res = scan.check_locks(ROOT)
        self.assertEqual([f["message"] for f in res["findings"]], [])
        py, npm = scan.find_locks(ROOT)
        self.assertGreaterEqual(len(py), 4, py)  # three runtime locks + the dev lock(s)
        self.assertTrue(any(p.name == "dev.lock" for p in py))
        self.assertTrue(npm, "adobe/package-lock.json must be found")

    def test_every_file_of_the_runtime_lock_folder_is_scanned_whatever_its_spelling(self):
        found = {p.name for p in scan.find_locks(ROOT)[0] if p.parent.name == "locks"}
        on_disk = {p.name for p in (ROOT / "whynot-cut" / "setup" / "locks").iterdir() if p.is_file() and p.name.lower() != "readme.md"}
        self.assertEqual(on_disk - found, set(), "lock files the scan would silently skip: %s" % sorted(on_disk - found))

    def test_planted_unhashed_pip_lock_and_npm_entries_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "مشروع" / "x y"
            (root / "whynot-cut" / "setup" / "locks").mkdir(parents=True)
            (root / "adobe").mkdir()
            (root / "whynot-cut" / "setup" / "locks" / "runtime-test.lock").write_text(
                "good==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\nbad==2.0\nempty==3.0 \\\n    --hash=sha256:\nshort==4.0 \\\n    --hash=sha256:abc\n",
                encoding="utf-8")
            (root / "adobe" / "package-lock.json").write_text(json.dumps({"packages": {
                "": {"name": "w"}, "node_modules/a": {"version": "1.0.0", "resolved": "https://r/a.tgz", "integrity": "sha512-AAAA"},
                "node_modules/b": {"version": "1.0.0", "resolved": "https://r/b.tgz"},
                "node_modules/c": {"version": "1.0.0", "resolved": "https://r/c.tgz", "integrity": "sha1-AAAA"},
                "../panel": {"link": True}}}), encoding="utf-8")
            msgs = [f["message"] for f in scan.check_locks(root)["findings"]]
            self.assertEqual(len(msgs), 5, msgs)
            self.assertTrue(any("bad==2.0" in m for m in msgs))
            self.assertTrue(any("empty==3.0" in m for m in msgs))
            self.assertTrue(any("short==4.0" in m for m in msgs))
            self.assertTrue(any("node_modules/b has no integrity" in m for m in msgs))
            self.assertTrue(any("node_modules/c integrity is not sha256/384/512" in m for m in msgs))

    def test_every_package_lock_is_found_not_only_the_first_five(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(8):
                (root / ("p%d" % i)).mkdir()
                (root / ("p%d" % i) / "package-lock.json").write_text("{}", encoding="utf-8")
            (root / "node_modules" / "x").mkdir(parents=True)
            (root / "node_modules" / "x" / "package-lock.json").write_text("{}", encoding="utf-8")
            self.assertEqual(len(scan.find_locks(root)[1]), 8)


class Sbom(unittest.TestCase):
    def test_cyclonedx_from_real_locks_is_valid_and_has_purls(self):
        bom = scan.build_sbom(ROOT)
        self.assertEqual(bom["bomFormat"], "CycloneDX")
        self.assertEqual(bom["specVersion"], "1.5")
        self.assertGreater(len(bom["components"]), 20)
        for c in bom["components"]:
            self.assertTrue(c["purl"].startswith(("pkg:pypi/", "pkg:npm/")), c)
        json.dumps(bom)
        self.assertTrue(any(c["purl"].startswith("pkg:npm/") and c.get("hashes") for c in bom["components"]))

    def test_sbom_cli_writes_a_file(self):
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = scan.main(["--sbom", "--out", str(Path(d) / "o"), "--raw", str(Path(d) / "r"), "--no-report",
                                  "--baseline", str(Path(d) / "none.json")])
            self.assertEqual(code, scan.EXIT_OK, buf.getvalue())
            f = next((Path(d) / "r").rglob("sbom.cdx.json"))
            self.assertGreater(len(json.loads(f.read_text(encoding="utf-8"))["components"]), 20)


class VulnerableLock(unittest.TestCase):
    """P4: a vulnerable pin in a scratch lock is found by pip-audit and by OSV-Scanner (needs the network)."""

    @NEEDS_TOOLS
    def test_planted_vulnerable_pin_is_found_or_the_degraded_mode_is_stated(self):
        if scan.is_offline(False):
            self.skipTest("offline: the degraded mode itself is covered by test_offline_deps_is_a_stated_degraded_mode_with_exit_3_through_the_cli")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "مشروع" / "x y"
            lk = root / "whynot-cut" / "setup" / "locks"
            lk.mkdir(parents=True)
            (lk / "runtime-scratch.lock").write_text(
                "requests==2.19.0 \\\n    --hash=sha256:421cfc8d9dde7d6aff68196420afd86b88c65d77d8da9cf83f4ecad785d7b9d6\n",
                encoding="utf-8", newline="\n")
            raw = Path(d) / "raw"
            raw.mkdir()
            py, npm = scan.find_locks(root)
            pa = scan.scan_pip_audit(root, raw, py)
            osv = scan.scan_osv(root, raw, py, npm)
            self.assertEqual(pa["status"], "OK", pa["note"])
            self.assertEqual(osv["status"], "OK", osv["note"])
            self.assertGreaterEqual(len(pa["findings"]), 1)
            self.assertGreaterEqual(len(osv["findings"]), 1)
            self.assertTrue(any(f["severity"] in scan.BLOCKING for f in osv["findings"]))
            self.assertTrue(any("2.20.0" in f["message"] for f in pa["findings"]))


class CliEndToEnd(unittest.TestCase):
    @NEEDS_TOOLS
    def test_sast_secrets_cli_on_planted_tree_exits_1_and_writes_a_report_without_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            root = write_tree(Path(d) / "tree")
            out, raw = Path(d) / "out", Path(d) / "raw"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = scan.main(["--sast", "--secrets", "--no-registry", "--root", str(root), "--out", str(out),
                                  "--raw", str(raw), "--gate", "t", "--baseline", str(Path(d) / "none.json")])
            self.assertEqual(code, scan.EXIT_FINDINGS, buf.getvalue())
            self.assertIn("NEW HIGH", buf.getvalue())
            rep = next(out.glob("scan-*-t.md")).read_text(encoding="utf-8")
            self.assertIn("wnc-tls-disabled", rep)
            alltext = rep + buf.getvalue() + tree_text(raw)
            for v in (F["key"], F["key2"], F["pw"]):
                self.assertNotIn(v, alltext)
            self.assertTrue((raw / "security-last-run.json").exists())


class EslintParsing(unittest.TestCase):
    def test_severity_and_parse(self):
        self.assertEqual(scan.eslint_sev("no-unsanitized/property"), "HIGH")
        self.assertEqual(scan.eslint_sev("security/detect-child-process"), "HIGH")
        self.assertEqual(scan.eslint_sev("security/detect-object-injection"), "LOW")
        self.assertEqual(scan.eslint_sev("security/detect-possible-timing-attacks"), "MEDIUM")
        items = [{"filePath": str(ROOT / "adobe" / "a.js"), "messages": [
            {"ruleId": "no-unsanitized/property", "line": 4, "message": "m", "source": "x.y = z"},
            {"ruleId": None, "line": 1, "message": "parse error"}]}]
        fs = scan.parse_eslint(items, ROOT)
        self.assertEqual([(f["rule"], f["file"], f["line"]) for f in fs], [("no-unsanitized/property", "adobe/a.js", 4)])

    def test_missing_plugins_are_degraded_not_skipped_silently(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "adobe").mkdir()
            r = scan.scan_eslint(Path(d), Path(d))
            self.assertEqual(r["status"], "DEGRADED")
            self.assertIn("Adobe track", r["note"])
            self.assertEqual(scan.exit_code([r], []), scan.EXIT_DEGRADED)


class RoundTwoHardening(unittest.TestCase):
    """Independent review round 2: crash paths, junction-safe lock discovery, redaction, stale output, empty coverage."""

    def setUp(self):
        scan._STATE_CACHE.clear()
        self.addCleanup(scan._STATE_CACHE.clear)

    def _tools_home_with(self, d, manifest_text, exe_bytes=b"fake gitleaks binary"):
        exe = scan.tool_exe("gitleaks")
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(exe_bytes)
        (Path(d) / "manifest.json").write_text(manifest_text, encoding="utf-8")

    def test_a_malformed_or_rewritten_manifest_reads_as_altered_or_missing_never_as_a_traceback(self):
        for bad in ("[]", '"x"', '{"gitleaks": "x"}', '{"gitleaks": {"exe": 5, "exe_sha256": 7}}',
                    '{"gitleaks": {"exe": "../evil.exe", "exe_sha256": "a"}}', "{not json"):
            scan._STATE_CACHE.clear()
            with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"WNC_SEC_TOOLS": d}), \
                    mock.patch.object(scan, "run", side_effect=AssertionError("must not run")):
                self._tools_home_with(d, bad)
                st, _, msg = scan.tool_state("gitleaks")
                self.assertIn(st, ("missing", "altered"), (bad, st, msg))

    def test_a_manifest_that_agrees_with_a_swapped_binary_is_caught_by_the_pinned_sha256(self):
        pinned = scan.versions()["binaries"]["gitleaks"]["platforms"][scan.platform_key()]["exe_sha256"]
        self.assertRegex(pinned, r"^[0-9a-f]{64}$")
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"WNC_SEC_TOOLS": d}), \
                mock.patch.object(scan, "run", side_effect=AssertionError("must not run")):
            self._tools_home_with(d, json.dumps({"gitleaks": {"exe": scan.tool_exe("gitleaks").name,
                                                              "exe_sha256": hashlib.sha256(b"evil").hexdigest()}}), b"evil")
            st, _, msg = scan.tool_state("gitleaks")
            self.assertEqual(st, "altered", msg)
            self.assertIn("pinned sha256", msg)

    def test_python_tool_integrity_covers_dependencies_and_refuses_a_record_without_hashes(self):
        import base64
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "venv" / "Lib" / "site-packages"
            for name, body in (("tool", b"a = 1\n"), ("dep", b"b = 2\n")):
                (sp / ("%s-1.0.dist-info" % name)).mkdir(parents=True)
                (sp / (name + ".py")).write_bytes(body)
                dig = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode()
                (sp / ("%s-1.0.dist-info" % name) / "RECORD").write_text("%s.py,sha256=%s,5\n" % (name, dig), encoding="utf-8")
            self.assertIsNone(it.verify_python_tool("tool", d, everything=True))
            (sp / "dep.py").write_bytes(b"b = 666\n")
            self.assertIsNone(it.verify_python_tool("tool", d))  # the tool itself is intact
            self.assertIn("differ", it.verify_python_tool("tool", d, everything=True))  # its dependency is not
            (sp / "dep.py").write_bytes(b"b = 2\n")
            (sp / "dep-1.0.dist-info" / "RECORD").write_text("dep.py,,\n", encoding="utf-8")
            self.assertIn("no hashed files", it.verify_python_tool("tool", d, everything=True))

    def test_lock_discovery_never_walks_through_a_junction_or_into_node_modules(self):
        with tempfile.TemporaryDirectory() as d:
            outside = Path(d) / "outside"
            outside.mkdir()
            (outside / "package-lock.json").write_text("{}", encoding="utf-8")
            root = Path(d) / "tree"
            (root / "adobe").mkdir(parents=True)
            (root / "adobe" / "package-lock.json").write_text("{}", encoding="utf-8")
            (root / "node_modules" / "x").mkdir(parents=True)
            (root / "node_modules" / "x" / "package-lock.json").write_text("{}", encoding="utf-8")
            link = root / "linked"
            if os.name == "nt":
                subprocess.run([os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe"), "/c", "mklink", "/J", str(link), str(outside)],
                               check=True, capture_output=True)
            else:
                link.symlink_to(outside, target_is_directory=True)
            try:
                found = [p.relative_to(root).as_posix() for p in scan.find_locks(root)[1]]
            finally:
                if os.name == "nt":
                    os.rmdir(link)  # the link only, never its target
                else:
                    link.unlink()
            self.assertEqual(found, ["adobe/package-lock.json"])
            self.assertTrue((outside / "package-lock.json").exists())

    def test_password_redaction_hides_everything_after_the_colon_even_with_quotes_inside(self):
        r = {"test_id": "B105", "issue_text": "Possible hardcoded password: 'it" + "'" + 's-Secret9"x' + "'"}
        out = scan.clean_bandit_text(r)
        self.assertNotIn("Secret9", out)
        self.assertTrue(out.startswith("Possible hardcoded password"))
        self.assertEqual(scan.clean_bandit_text({"test_id": "B101", "issue_text": "Use of assert: x"}), "Use of assert: x")

    def test_a_registry_rules_message_and_semgrep_errors_are_not_kept(self):
        data = {"results": [{"check_id": "p.secrets.rule", "path": "a.py", "start": {"line": 1}, "end": {"line": 1},
                             "extra": {"message": "hardcoded credential " + F["pw"], "lines": "x",
                                       "metavars": {"$A": {"abstract_content": F["pw"]}}, "severity": "ERROR"}},
                            {"check_id": "x.wnc-tls-disabled", "path": "a.py", "start": {"line": 2}, "end": {"line": 2},
                             "extra": {"message": "static rule message", "severity": "ERROR"}}],
                "errors": [{"level": "warn", "type": "x", "message": "snippet " + F["pw"], "spans": [{"file": "a.py"}], "long_msg": F["pw"]}]}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
            fs = scan.parse_semgrep(data, d)
        self.assertNotIn(F["pw"], json.dumps(fs))
        scrubbed = scan.scrub_semgrep(data)
        self.assertNotIn(F["pw"], json.dumps(scrubbed))
        self.assertEqual(scrubbed["results"][1]["extra"]["message"], "static rule message")

    def test_pip_audit_never_reads_a_stale_output_file_and_checks_the_exit_code(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(scan, "need", return_value=None), mock.patch.object(scan, "run") as run_mock:
            lock = Path(d) / "a.lock"
            lock.write_text("x\n", encoding="utf-8")
            (Path(d) / "pip-audit-0.json").write_text(json.dumps({"dependencies": []}), encoding="utf-8")  # an earlier run's result
            run_mock.return_value = (3, "", "boom")  # pip-audit died and wrote nothing
            r = scan.scan_pip_audit(Path(d), Path(d), [lock])
            self.assertEqual(r["status"], "FAILED")
            self.assertIn("boom", r["note"])

    def test_eslint_that_lints_nothing_or_cannot_parse_a_file_is_not_ok(self):
        with tempfile.TemporaryDirectory() as d:
            adobe = Path(d) / "adobe"
            (adobe / "node_modules" / "eslint" / "bin").mkdir(parents=True)
            (adobe / "node_modules" / "eslint" / "bin" / "eslint.js").write_text("", encoding="utf-8")
            (adobe / "eslint.security.config.mjs").write_text("", encoding="utf-8")
            with mock.patch.object(scan, "which_safe", return_value=str(Path(d) / "node.exe")), mock.patch.object(scan, "run") as run_mock:
                run_mock.return_value = (0, "[]", "")
                self.assertEqual(scan.scan_eslint(Path(d), Path(d))["status"], "FAILED")
                items = [{"filePath": str(adobe / "a.js"), "messages": [{"ruleId": None, "fatal": True, "severity": 2, "message": "Parsing error"}]}]
                run_mock.return_value = (1, json.dumps(items), "")
                r = scan.scan_eslint(Path(d), Path(d))
                self.assertEqual(r["status"], "DEGRADED")
                self.assertEqual(r["codes"], ["parse-errors"])

    def test_an_empty_lock_or_a_lockfile_version_1_is_a_lock_hash_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "whynot-cut" / "setup" / "locks").mkdir(parents=True)
            (root / "whynot-cut" / "setup" / "locks" / "runtime-a.lock").write_text("", encoding="utf-8")
            (root / "adobe").mkdir()
            (root / "adobe" / "package-lock.json").write_text(
                json.dumps({"lockfileVersion": 1, "dependencies": {"a": {"version": "1.0.0"}}}), encoding="utf-8")
            msgs = [f["message"] for f in scan.check_locks(root)["findings"]]
            self.assertTrue(any("no pinned requirement" in m for m in msgs), msgs)
            self.assertTrue(any("no `packages` map" in m for m in msgs), msgs)

    def test_the_scanners_environment_drops_variables_that_redirect_code_or_weaken_tls(self):
        bad = {k: "x" for k in ("PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "NODE_TLS_REJECT_UNAUTHORIZED", "SSL_CERT_FILE",
                                "REQUESTS_CA_BUNDLE", "GITLEAKS_CONFIG", "PIP_INDEX_URL")}
        with mock.patch.dict(os.environ, dict(bad, HTTPS_PROXY="http://proxy.invalid:3128")):
            env = scan.clean_env()
            pip_env = it._pip_env(scan.tools_home())
        for k in bad:
            self.assertNotIn(k, env)
            self.assertNotIn(k, pip_env)
        self.assertEqual(env["HTTPS_PROXY"], "http://proxy.invalid:3128")  # proxies are kept


    def test_any_unexpected_exception_is_a_failed_scan_exit_4_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            for exc in (TypeError("boom"), AttributeError("boom"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "boom")):
                with mock.patch.object(scan, "run_scans", side_effect=exc), contextlib.redirect_stderr(io.StringIO()) as err:
                    code = scan.main(["--locks", "--root", d, "--raw", d, "--no-report", "--baseline", str(Path(d) / "none.json")])
                self.assertEqual(code, scan.EXIT_TOOL, repr(exc))
                self.assertIn("SCAN ERROR", err.getvalue())

    def test_a_stray_pth_or_sitecustomize_in_site_packages_is_refused(self):
        import base64
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "venv" / "Lib" / "site-packages"
            (sp / "tool-1.0.dist-info").mkdir(parents=True)
            (sp / "tool.py").write_bytes(b"a = 1\n")
            dig = base64.urlsafe_b64encode(hashlib.sha256(b"a = 1\n").digest()).rstrip(b"=").decode()
            (sp / "tool-1.0.dist-info" / "RECORD").write_text("tool.py,sha256=%s,5\n" % dig, encoding="utf-8")
            self.assertIsNone(it.verify_python_tool("tool", d, everything=True))
            for name in ("evil.pth", "sitecustomize.py"):
                (sp / name).write_text("import os\n", encoding="utf-8")
                self.assertIn("belongs to no installed package", it.verify_python_tool("tool", d, everything=True), name)
                (sp / name).unlink()
            (sp / "tool-1.0.dist-info" / "RECORD").write_bytes(b"\xff\xfe\x00bad,sha256=x,1\n")  # undecodable RECORD never raises
            self.assertIsNotNone(it.verify_python_tool("tool", d, everything=True))

    def _semgrep_with(self, errors):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(scan, "need", return_value=None), mock.patch.object(scan, "run") as run_mock:
            root = Path(d) / "tree"
            root.mkdir()
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")

            def fake(argv, cwd=None, **kw):
                out = Path(argv[argv.index("--output") + 1])
                out.write_text(json.dumps({"results": [], "errors": errors, "paths": {"scanned": [str(root / "a.py")], "skipped": []}}), encoding="utf-8")
                return 0, "", ""
            run_mock.side_effect = fake
            return scan.scan_semgrep(root, Path(d), offline=False)

    def test_semgrep_files_it_could_not_parse_degrade_the_scan_partial_parses_are_only_noted(self):
        r = self._semgrep_with([{"level": "warn", "type": "Syntax error", "message": "x"}])
        self.assertEqual((r["status"], r["codes"]), ("DEGRADED", ["scan-errors"]))
        r = self._semgrep_with([{"level": "error", "type": "Other", "message": "x"}])
        self.assertEqual(r["status"], "DEGRADED")
        r = self._semgrep_with([{"level": "warn", "type": ["PartialParsing", [{"path": "a.py"}]], "message": "x"}])
        self.assertEqual(r["status"], "OK")
        self.assertIn("partly parsed", r["note"])
        self.assertEqual(self._semgrep_with([])["status"], "OK")


class RunScansComposition(unittest.TestCase):
    """`--all` must run EVERY scanner: removing one from run_scans may never leave the suite green (acceptance follow-up 1)."""
    FUNCS = ("scan_semgrep", "scan_bandit", "scan_eslint", "scan_gitleaks", "scan_binary_secrets", "check_locks",
             "scan_pip_audit", "scan_osv", "scan_npm", "scan_sbom", "scan_commit_messages")

    def test_funcs_is_exactly_what_run_scans_calls(self):
        """A scanner added to (or dropped from) run_scans without this list is a clean failure here, never a real run."""
        called = {n for n in scan.run_scans.__code__.co_names if n.startswith(("scan_", "check_"))}
        self.assertEqual(called, set(self.FUNCS))

    def _run(self, modes, **kw):
        calls = []
        self.flags = []
        patches = []
        for name in self.FUNCS:
            def fake(*a, _n=name, **k):
                calls.append((_n, a[2:] if _n == "scan_gitleaks" else (), k))
                self.flags.append((_n, k.get("history", a[2] if _n == "scan_gitleaks" and len(a) > 2 else None)))
                return scan.result(_n, "OK")
            patches.append(mock.patch.object(scan, name, side_effect=fake))
        with contextlib.ExitStack() as st, tempfile.TemporaryDirectory() as d:
            for p in patches:
                st.enter_context(p)
            st.enter_context(mock.patch.object(scan, "find_locks", return_value=([Path(d) / "a.lock"], [Path(d) / "p.json"])))
            res = scan.run_scans(modes, Path(d), Path(d), **kw)
        return [c[0] for c in calls], [r["tool"] for r in res]

    def test_all_modes_run_exactly_the_full_tool_list(self):
        called, tools = self._run({"sast", "secrets", "locks", "deps", "sbom"})
        self.assertEqual(sorted(called), sorted(["scan_semgrep", "scan_bandit", "scan_eslint", "scan_gitleaks",
                                                 "scan_binary_secrets", "check_locks", "scan_pip_audit", "scan_osv",
                                                 "scan_npm", "scan_sbom"]))
        self.assertEqual(len(tools), 10)

    def test_history_adds_the_history_gitleaks_pass_and_the_commit_message_scan(self):
        called, _ = self._run({"secrets"}, history=True)
        self.assertEqual(sorted(called), sorted(["scan_gitleaks", "scan_gitleaks", "scan_binary_secrets", "scan_commit_messages"]))
        self.assertEqual([h for n, h in self.flags if n == "scan_gitleaks"], [False, True])  # tree pass, then the history pass
        self.assertEqual([h for n, h in self.flags if n == "scan_binary_secrets"], [True])

    def test_the_cli_all_flag_selects_every_mode(self):
        seen = {}
        def fake(modes, *a, **k):
            seen["modes"] = set(modes)
            return []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(scan, "run_scans", side_effect=fake), \
                mock.patch.object(scan, "is_offline", return_value=False), contextlib.redirect_stdout(io.StringIO()):
            scan.main(["--all", "--root", d, "--raw", d, "--out", d, "--baseline", str(Path(d) / "none.json")])
        self.assertEqual(seen["modes"], {"sast", "secrets", "deps", "sbom", "locks"})


class PipAuditGapIsPinnedByName(unittest.TestCase):
    """A pip-audit `skipped-requirements` gap names its packages (torch, torchaudio): a NEW skipped package is not accepted."""
    GAP = {"tool": "pip-audit", "code": "skipped-requirements", "reason": "local +cu128 builds", "owner_task": "executor",
           "review_date": "2099-01-01", "packages": ["torch==2.8.0+cu128", "torchaudio==2.8.0+cu128"]}
    LOCK = ("torch==2.8.0+cu128 \\\n    --hash=sha256:aa\n"
            "torchaudio==2.8.0+cu128 \\\n    --hash=sha256:bb\n"
            "Some_Pkg==1.2 \\\n    --hash=sha256:cc\n")

    def _audit(self, names, lock_text=None):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(scan, "need", return_value=None), \
                mock.patch.object(scan, "run") as run_mock:
            lock = Path(d) / "a.lock"
            lock.write_text(self.LOCK if lock_text is None else lock_text, encoding="utf-8")

            def fake(argv, cwd=None, **kw):
                Path(argv[argv.index("-o") + 1]).write_text(
                    json.dumps({"dependencies": [{"name": n, "skip_reason": "no PyPI match"} for n in names]}), encoding="utf-8")
                return 0, "", ""
            run_mock.side_effect = fake
            return scan.scan_pip_audit(Path(d), Path(d), [lock])

    def _accepted(self, names, gap=None, lock_text=None):
        r = [self._audit(names, lock_text)]
        scan.apply_known_gaps(r, {("pip-audit", "skipped-requirements"): gap or self.GAP})
        return scan.exit_code(r, []) == scan.EXIT_OK

    def test_the_result_carries_the_skipped_package_names(self):
        self.assertEqual(sorted(self._audit(["torch", "torchaudio"])["skipped"]), ["torch==2.8.0+cu128", "torchaudio==2.8.0+cu128"])
        self.assertEqual(self._audit(["unpinned"])["skipped"], ["unpinned"])  # no pin in the lock: the bare name, never accepted

    def test_torch_and_torchaudio_alone_are_accepted(self):
        self.assertTrue(self._accepted(["torch", "torchaudio"]))
        self.assertTrue(self._accepted(["TorchAudio"]))  # package names compare case-insensitively (PEP 503 spelling)

    def test_a_new_version_of_an_accepted_package_is_not_hidden(self):
        self.assertFalse(self._accepted(["torch"], lock_text="torch==2.9.0+cu128 \\\n"))
        self.assertFalse(self._accepted(["torch"], lock_text="torch==2.8.0 \\\n"))  # the CPU build is another artifact
        self.assertTrue(self._accepted(["torch"], lock_text="Torch==2.8.0+cu128\n"))

    def test_two_different_pins_of_one_package_are_never_accepted(self):
        two = 'torch==2.8.0+cu128 ; sys_platform == "linux"\ntorch==9.9 ; sys_platform == "win32"\n'
        self.assertFalse(self._accepted(["torch"], lock_text=two))

    def test_any_other_skipped_package_is_not_hidden(self):
        self.assertFalse(self._accepted(["torch", "requests"]))
        self.assertFalse(self._accepted(["somepkg"]))

    def test_a_gap_without_a_package_list_accepts_no_skipped_package(self):
        gap = {k: v for k, v in self.GAP.items() if k != "packages"}
        self.assertFalse(self._accepted(["torch"], gap))

    def test_the_real_baseline_pins_the_packages(self):
        _, gaps = scan.load_baseline_full(ROOT / "docs" / "security" / "baseline.json")
        g = gaps[("pip-audit", "skipped-requirements")]
        self.assertEqual(sorted(g["packages"]), ["torch==2.8.0+cu128", "torchaudio==2.8.0+cu128"])

    def test_a_bad_packages_field_is_a_baseline_error(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ("torch", [], [""], [1], ["torch"], ["torch=="], ["torch>=2.8"]):
                p = Path(d) / "b.json"
                p.write_text(json.dumps({"accepted": [], "known_gaps": [dict(self.GAP, packages=bad)]}), encoding="utf-8")
                with self.assertRaises(scan.BaselineError, msg=repr(bad)):
                    scan.load_baseline_full(p)


class BaselineTriage(unittest.TestCase):
    def test_qc_py_et_parse_is_accepted_risk_not_false_positive(self):
        data = json.loads((ROOT / "docs" / "security" / "baseline.json").read_text(encoding="utf-8"))
        qc = [e for e in data["accepted"] if e["file"].endswith("lib/qc.py") and "defused-xml" in e["rule"]]
        self.assertTrue(qc, "the qc.py ET.parse entry is missing")
        for e in qc:
            self.assertEqual(e["verdict"], "accepted_risk", e["reason"])


class RuleIdsDoNotDependOnThePath(unittest.TestCase):
    """ADOBE-G4 2026-10-19 (work\\secscan-env\\FINDING.md): Semgrep prefixes our rule ids with the rules folder's path in
    dots; a checkout under a folder named wnc-<x> turned wnc-raw-innerhtml into "wnc-p4.t45..semgrep.wnc-raw-innerhtml",
    so every planted sample read "not caught", and a registry rule under such a path would have kept its message."""

    def test_only_the_last_segment_is_our_id(self):
        for cid in ("wnc-raw-innerhtml", ".semgrep.wnc-raw-innerhtml",
                    "D.ClaudeData.Temp.wnc-p4.t45ab-055404..semgrep.wnc-raw-innerhtml",
                    "home.u.wnc-dev.wnc-x.repo..semgrep.wnc-raw-innerhtml"):
            self.assertEqual(scan.own_rule(cid), "wnc-raw-innerhtml", cid)
        for cid in ("python.lang.security.audit.eval-detected", "D.Temp.wnc-p4.snap.python.lang.eval-detected",
                    "wnc-p4.x.javascript.browser.security.insecure-innerhtml", "", None):
            self.assertIsNone(scan.own_rule(cid), cid)

    def _result(self, cid, msg="matched SECRETVALUE"):
        return {"check_id": cid, "path": "a.js", "start": {"line": 1}, "end": {"line": 1},
                "extra": {"message": msg, "severity": "WARNING", "lines": "SECRETVALUE"}}

    def test_parse_keeps_our_id_and_withholds_a_registry_message_under_a_wnc_path(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "a.js").write_text("x\n", encoding="utf-8")
            got = scan.parse_semgrep({"results": [
                self._result("D.Temp.wnc-p4.snap..semgrep.wnc-raw-innerhtml", "our fixed message"),
                self._result("D.Temp.wnc-p4.snap.javascript.browser.security.insecure-innerhtml")]}, td)
        rules = sorted(f["rule"] for f in got)
        self.assertEqual(rules, ["D.Temp.wnc-p4.snap.javascript.browser.security.insecure-innerhtml",
                                 "wnc-raw-innerhtml"])
        by = {f["rule"]: f for f in got}
        self.assertEqual(by["wnc-raw-innerhtml"]["message"], "our fixed message")
        self.assertNotIn("SECRETVALUE", json.dumps(got))

    def test_scrub_drops_a_registry_message_under_a_wnc_path(self):
        data = scan.scrub_semgrep({"results": [
            self._result("D.Temp.wnc-p4.snap.javascript.browser.security.insecure-innerhtml"),
            self._result("D.Temp.wnc-p4.snap..semgrep.wnc-raw-innerhtml", "our fixed message")]})
        self.assertNotIn("message", data["results"][0]["extra"])
        self.assertEqual(data["results"][1]["extra"]["message"], "our fixed message")
        self.assertNotIn("SECRETVALUE", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
