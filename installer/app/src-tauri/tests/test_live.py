"""ET1-17 live checks of the built app in WebView2 (Windows): the CSP header actually served, IPC under it, the
navigation lock, no new windows, no downloads, single instance (a session-local mutex).

    WNC_APP_EXE=<path to whynot-cut-setup.exe> python -I -m unittest discover -s installer/app/src-tauri/tests -p "test_live.py" -v

Without WNC_APP_EXE (or off Windows) the class is skipped and says so; the macOS twin is the ET1-22 selftest.
The gnullvm dev build needs llvm-mingw's bin (libunwind.dll) on PATH, as in SPIKE-S0.md.

Safety: only the process this test starts is touched (closed with CloseMainWindow, killed only if it ignores that).
Its WebView2 profile and every download destination live in a throw-away folder under TEMP (D:/ClaudeData on this
PC): never the user's real Downloads. The debug port is bound to 127.0.0.1 for that one process.
"""
from __future__ import annotations

import ctypes
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _cdp import INVOKE, WS, directives, http_json  # noqa: E402
from test_scaffold import CSP  # noqa: E402  (the one policy string the config must carry)

EXE = os.environ.get("WNC_APP_EXE", "")
PORT = 9361
IDENTIFIER = "ai.thewhynot.whynotcut.setup"
APP = "http://tauri.localhost/"


@unittest.skipUnless(sys.platform == "win32" and EXE, "set WNC_APP_EXE to a built app (Windows; macOS = ET1-22)")
class LiveAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="wnc-et1-17-live-"))
        cls.dl = cls.tmp / "downloads"
        cls.dl.mkdir()
        # Downloads land in OUR folder if anything ever downloads: the test profile's Chromium preference, written
        # before WebView2 starts. (Not CDP Browser.setDownloadBehavior: that overrides WebView2's DownloadStarting
        # event, so the app's own refusal would never run; probed in fix round 1.)
        prefs = cls.tmp / "wv2" / "EBWebView" / "Default" / "Preferences"
        prefs.parent.mkdir(parents=True)
        prefs.write_text(json.dumps({"download": {"default_directory": str(cls.dl), "prompt_for_download": False},
                                     "savefile": {"default_directory": str(cls.dl)}}), encoding="utf-8")
        cls.user_downloads = pathlib.Path(os.environ["USERPROFILE"]) / "Downloads"
        cls.user_downloads_before = cls.snapshot(cls.user_downloads)
        env = dict(os.environ, WEBVIEW2_USER_DATA_FOLDER=str(cls.tmp / "wv2"),
                   WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=f"--remote-debugging-port={PORT}")
        cls.env = env
        cls.proc = subprocess.Popen([EXE], env=env, cwd=str(cls.tmp))
        page = None
        for _ in range(200):
            try:
                page = next((t for t in http_json(PORT, "/json") if t.get("type") == "page"
                             and t.get("url", "").startswith(APP)), None)
                if page:
                    break
            except OSError:
                pass
            time.sleep(0.1)
        if not page:
            cls.tearDownClass()
            raise RuntimeError("the app did not show its page on the debug port")
        cls.ws = WS(page["webSocketDebuggerUrl"])
        for m in ("Runtime.enable", "Page.enable", "Network.enable"):
            cls.ws.call(m)
        # reload once with Network on, so the document response (and its CSP header) is observed
        cls.ws.events.clear()
        cls.ws.call("Page.navigate", url=APP + "index.html?live=1")
        cls.ws.drain(3)
        cls.doc_events = list(cls.ws.events)

    @classmethod
    def tearDownClass(cls):
        for s in ("ws",):
            if getattr(cls, s, None):
                getattr(cls, s).close()
        p = getattr(cls, "proc", None)
        if p and p.poll() is None:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"(Get-Process -Id {p.pid}).CloseMainWindow() | Out-Null"], check=False)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()  # our own process only
        time.sleep(1.5)
        shutil.rmtree(cls.tmp, ignore_errors=True)  # our temp tree: no links in it

    @staticmethod
    def snapshot(folder: pathlib.Path) -> set:
        """Names + mtimes of the top level only (read-only; nothing in it is opened)."""
        try:
            return {(e.name, e.stat().st_mtime_ns) for e in os.scandir(folder)}
        except OSError:
            return set()

    def pages(self) -> list[str]:
        return [t.get("url", "") for t in http_json(PORT, "/json") if t.get("type") == "page"]

    def back_home(self):
        if not self.ws.eval("location.href").startswith(APP):
            self.ws.call("Page.navigate", url=APP)
            time.sleep(2)

    # --- L4: the header actually served ------------------------------------------------------------------------

    def test_served_csp_header_is_our_policy_plus_only_taurus_isolation_origin_and_script_hashes(self):
        docs = [e["params"]["response"] for e in self.doc_events
                if e.get("method") == "Network.responseReceived" and e["params"].get("type") == "Document"]
        app_docs = [d for d in docs if d["url"].startswith(APP)]
        self.assertTrue(app_docs, f"no app document response observed: {[d['url'] for d in docs]}")
        headers = {k.lower(): v for k, v in app_docs[-1].get("headers", {}).items()}
        # The isolation iframe's document carries Tauri's own fixed policy, not ours (report: fix round 1, L4).
        iso = [d for d in docs if re.match(r"http://isolation-[0-9a-f-]{36}\.localhost/", d["url"])]
        if iso:
            iso_csp = {k.lower(): v for k, v in iso[-1].get("headers", {}).items()}.get("content-security-policy", "")
            self.assertEqual(sorted(directives(iso_csp)), ["default-src", "frame-src", "script-src", "style-src"])
            self.assertEqual(directives(iso_csp)["default-src"], ["'none'"])
            print("\n[isolation iframe CSP] " + iso_csp, file=sys.stderr)
        served, ours = directives(headers["content-security-policy"]), directives(CSP)
        self.assertEqual(sorted(served), sorted(ours), "same directives, none added or dropped")
        for name, sources in ours.items():
            extra = [s for s in served[name] if s not in sources]
            self.assertEqual([s for s in sources if s not in served[name]], [], f"{name} lost a source")
            if name == "default-src":
                self.assertTrue(all(re.fullmatch(r"http://isolation-[0-9a-f-]{36}\.localhost/", s) for s in extra),
                                f"default-src extras: {extra}")
                self.assertEqual(len(extra), 1, extra)
            elif name == "script-src":
                self.assertTrue(all(re.fullmatch(r"'(sha256-[A-Za-z0-9+/=]+|nonce-\d+)'", s) for s in extra),
                                f"script-src extras: {extra}")
            else:
                self.assertEqual(extra, [], f"{name} widened by {extra}")

    # --- IPC ----------------------------------------------------------------------------------------------------

    def test_app_info_works_and_other_commands_are_refused(self):
        self.back_home()
        got = self.ws.eval(INVOKE + "('app_info')")
        self.assertEqual(got, {"ok": {"version": "3.0.0", "signed": False, "internal_build": True}})
        for cmd in ("plugin:event|listen", "plugin:window|close", "secret_command"):
            err = self.ws.eval(INVOKE + f"({json.dumps(cmd)})").get("err", "")
            self.assertIn("not allowed by ACL", err, cmd)

    def test_trusted_types_are_enforced_and_the_ui_reports_no_violation(self):
        self.back_home()
        self.assertTrue(str(self.ws.eval(
            "(()=>{try{document.createElement('div').innerHTML='x';return 'allowed'}catch(e){return 'blocked'}})()"))
            .startswith("blocked"))
        check = self.ws.eval("(document.querySelector('meta[name=mock-check]')||{}).content || ''")
        self.assertIn("csp=0", check)
        self.assertIn("jserr=0", check)

    # --- L1: navigation, new windows, I2: downloads -------------------------------------------------------------

    def test_navigation_outside_the_bundle_is_blocked_and_inside_is_allowed(self):
        for target in ["https://example.com/", "http://127.0.0.1:9/probe", "file:///C:/Windows/win.ini",
                       "http://ipc.localhost/app_info", "https://tauri.localhost/"]:
            self.back_home()
            self.ws.eval(f"setTimeout(()=>{{location.href={json.dumps(target)}}},0);1")
            time.sleep(2)
            self.assertTrue(self.ws.eval("location.href").startswith(APP), target)
        self.ws.eval("setTimeout(()=>{location.href='/index.html?nav=1'},0);1")
        time.sleep(2)
        self.assertEqual(self.ws.eval("location.href"), APP + "index.html?nav=1")

    def test_no_new_window_ever_opens(self):
        self.back_home()
        before = len(self.pages())
        self.assertEqual(self.ws.eval("String(window.open('https://example.com/'))"), "null")
        self.assertEqual(self.ws.eval("String(window.open('/index.html'))"), "null")
        self.ws.eval("(()=>{const a=document.createElement('a');a.href='https://example.com/';a.target='_blank';"
                     "document.body.append(a);a.click();a.remove();return 1})()")
        time.sleep(2)
        self.assertEqual(len(self.pages()), before)

    def test_downloads_are_refused(self):
        self.back_home()
        before = len(self.pages())
        for href in ["URL.createObjectURL(new Blob(['probe'],{type:'text/plain'}))", "'/index.html'"]:
            self.ws.eval("(()=>{const a=document.createElement('a');a.href=" + href + ";a.download='wnc-probe.txt';"
                         "document.body.append(a);a.click();a.remove();return 1})()")
            time.sleep(2)
        self.assertEqual(sorted(p.name for p in self.dl.iterdir()), [], "a download was written")
        self.assertEqual(len(self.pages()), before, "a downloads page opened")
        new = self.snapshot(self.user_downloads) - self.user_downloads_before
        self.assertEqual(sorted(n for n, _ in new if "wnc-probe" in n), [], "a download reached the user's Downloads")

    def test_web_permission_requests_are_denied_without_a_prompt(self):
        self.back_home()
        before = len(self.pages())
        got = self.ws.eval("Promise.race([Notification.requestPermission(),"
                           "new Promise(r=>setTimeout(()=>r('TIMEOUT'),5000))])")
        self.assertEqual(got, "denied")
        got = self.ws.eval("new Promise(r=>{navigator.geolocation.getCurrentPosition(()=>r('granted'),"
                           "e=>r('error '+e.code));setTimeout(()=>r('TIMEOUT'),5000)})")
        self.assertEqual(got, "error 1")  # PERMISSION_DENIED
        self.assertEqual(len(self.pages()), before, "a permission prompt opened")

    # --- M1: single instance -----------------------------------------------------------------------------------

    def test_the_instance_mutex_is_session_local_and_a_second_launch_exits(self):
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenMutexW.restype = ctypes.c_void_p
        SYNCHRONIZE = 0x00100000
        local = k32.OpenMutexW(SYNCHRONIZE, False, f"Local\\{IDENTIFIER}-sim")
        self.assertTrue(local, "the plugin's mutex should exist in the session-local namespace")
        k32.CloseHandle(ctypes.c_void_p(local))
        self.assertFalse(k32.OpenMutexW(SYNCHRONIZE, False, f"Global\\{IDENTIFIER}-sim"), "no Global\\ mutex")
        env = {k: v for k, v in self.env.items() if k != "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"}
        second = subprocess.run([EXE, "--uninstall", "--home", "C:/x"], env=env, cwd=str(self.tmp), timeout=30)
        self.assertEqual(second.returncode, 0)
        self.assertIsNone(self.proc.poll(), "the first instance must keep running")


if __name__ == "__main__":
    unittest.main()
