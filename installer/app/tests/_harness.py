"""Shared helpers for the installer UI tests (ID-21): find a browser, stage the UI bundle, render it headless.

Why file:// and not a local HTTP server: on this PC Kaspersky's web filter rewrites pages served from
http://127.0.0.1 (it added its own host to the CSP meta and broke the 'none' keywords, probed 2026-10-16), so a CSP
test over HTTP would test Kaspersky. file:// is never filtered; Chrome needs --allow-file-access-from-files to load
ES modules there, and CSP 'self' then matches the bundle's own files.

The staged copy = installer/app/ui/** + the files listed in installer/app/ui/vendor.json (brand tokens, fonts, the
monogram; copied from their one source in the repo, never committed twice) + tests/fixtures/*.js (test-only bodies,
served at <stage>/fixtures/, never part of ui/). The Tauri build (ET1-17) stages the same way, without fixtures.

The browser is the Chrome or Edge already on the machine (read-only use), always with a throw-away
--user-data-dir under the test temp folder; only the process this harness started is ever stopped.
"""
from __future__ import annotations

import html.parser
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
REPO = APP.parent.parent
UI = APP / "ui"
FIXTURES = HERE / "fixtures"

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]

# the window: content 760 x 540 (minimum 640 x 480) under the drawn OS title bar (28 px macOS, 32 px Windows)
CONTENT_H = {760: 540, 640: 480}
CHROME_H = {"mac": 28, "win": 32}

CSP_TARGET = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; "
              "connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; "
              "require-trusted-types-for 'script'; trusted-types 'none'")
# the one CSP notice a <meta> policy always gets (the spec ignores frame-ancestors there; the app host sends it as a
# header, ET1-17): matched exactly, so a second problem on another line is never hidden
META_FRAME_ANCESTORS = "The Content Security Policy directive 'frame-ancestors' is ignored when delivered via a <meta> element."


def tmp_root() -> pathlib.Path:
    """<WHYNOT_TEST_TMP>/et1-07 (the system temp folder when the variable is not set)."""
    base = os.environ.get("WHYNOT_TEST_TMP") or tempfile.gettempdir()
    root = pathlib.Path(base) / "et1-07"
    root.mkdir(parents=True, exist_ok=True)
    return root


def browser() -> str:
    env = os.environ.get("WNC_BROWSER")
    if env and os.path.exists(env):
        return env
    found = next((b for b in BROWSERS if os.path.exists(b)), None) or shutil.which("google-chrome") \
        or shutil.which("chromium") or shutil.which("chrome")
    if not found:
        raise RuntimeError("no Chrome or Edge found (set WNC_BROWSER to its path)")
    return found


def vendor_map() -> list[dict]:
    return json.loads((UI / "vendor.json").read_text(encoding="utf-8"))["files"]


def strings() -> dict:
    """The UI string table (ui/js/strings.js: strict JSON in an ES module): {"en": {...}, "ar": {...}}."""
    src = (UI / "js" / "strings.js").read_text(encoding="utf-8")
    body = src.split("export default", 1)[1].strip()
    return json.loads(body[:-1])


def check_vendor_target(to: str) -> str:
    """A vendor.json target must be a relative POSIX path inside vendor/ (no .., no ., no drive, no backslash)."""
    p = pathlib.PurePosixPath(to)
    if ("\\" in to or re.match(r"^[A-Za-z]:", to) or p.is_absolute() or not p.parts or p.parts[0] != "vendor"
            or any(x in ("..", ".") for x in p.parts) or len(p.parts) < 2):
        raise ValueError(f"bad vendor target: {to!r}")
    return to


def stage(dest: pathlib.Path, *, skip_fonts: bool = False, fixtures: bool = True, production: bool = False) -> pathlib.Path:
    """Copy the UI bundle + its vendored files (+ the test fixtures) into dest; returns dest.
    production=True stages exactly what ships: the files listed in ui/stage.json + vendor.json, never the demo or the
    fixtures (the list ET1-17's build uses)."""
    if production:
        dest.mkdir(parents=True)
        for rel in json.loads((UI / "stage.json").read_text(encoding="utf-8"))["files"]:
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(UI / rel, out)
        fixtures = False
    else:
        shutil.copytree(UI, dest)
    for f in vendor_map():
        if skip_fonts and f["to"].startswith("vendor/fonts/"):
            continue
        out = dest / check_vendor_target(f["to"])
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / f["from"], out)
    if fixtures and FIXTURES.is_dir():
        shutil.copytree(FIXTURES, dest / "fixtures")
    return dest


class Render:
    """One headless page load: the dumped DOM, the browser log, the page self-check, and the console CSP lines."""

    def __init__(self, dom: str, log: str, query: dict, size: tuple[int, int]):
        self.dom, self.log, self.query, self.size = dom, log, query, size
        m = re.search(r'<meta name="mock-check" content="([^"]*)"', dom)
        self.raw_check = m.group(1) if m else None
        self.check = dict(kv.split("=", 1) for kv in (self.raw_check or "").split(";") if "=" in kv)
        lines = log.splitlines()
        # a violation ("... violates the following Content Security Policy directive ...", "Refused to ...")
        self.console_csp = [ln for ln in lines if ":CONSOLE" in ln and
                            ("violates the following Content Security Policy" in ln or "Refused to" in ln)]
        # any other CSP message: a policy the browser could not parse as written (e.g. a filter that rewrote it).
        # 'frame-ancestors' in a <meta> is ignored by every browser (spec) and says so; the app host must send it
        # as a header (ET1-17), so that one notice is expected here.
        self.console_csp_notes = [ln for ln in lines if ":CONSOLE" in ln and "Content Security Policy" in ln
                                  and ln not in self.console_csp and META_FRAME_ANCESTORS not in ln]
        self.console_errors = [ln for ln in log.splitlines() if ":CONSOLE" in ln and "Uncaught" in ln]

    def label(self) -> str:
        return urllib.parse.urlencode(self.query) + f" @{self.size[0]}x{self.size[1]}"


def _chrome_cmd(exe: str, prof: pathlib.Path, size: tuple[int, int], url: str, budget: int = 5000) -> list[str]:
    return [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--allow-file-access-from-files", f"--user-data-dir={prof}",
            f"--window-size={size[0]},{size[1]}", f"--virtual-time-budget={budget}",
            "--blink-settings=preferredColorScheme=0", "--host-resolver-rules=MAP * ~NOTFOUND",
            "--enable-logging=stderr", "--v=0", "--dump-dom", url]


def viewport_delta(exe: str, work: pathlib.Path) -> tuple[int, int]:
    """--window-size is the OUTER size; headless Chrome on Windows gives the page 18 x 96 px less (probed 2026-10-16:
    760 x 568 -> 742 x 472). Measure the difference once with a blank probe page so the page gets the exact size."""
    probe = work / "probe"
    probe.mkdir(parents=True, exist_ok=True)
    (probe / "vw.html").write_text('<!doctype html><html><head><meta charset="utf-8"><script src="vw.js"></script>'
                                   "</head><body></body></html>", encoding="utf-8")
    (probe / "vw.js").write_text('addEventListener("load", function () { var m = document.createElement("meta");'
                                 ' m.name = "vw"; m.content = innerWidth + "x" + innerHeight;'
                                 " document.head.appendChild(m); });", encoding="utf-8")
    prof = work / "profile-probe"
    try:
        r = subprocess.run(_chrome_cmd(exe, prof, (800, 600), (probe / "vw.html").resolve().as_uri()),
                           capture_output=True, timeout=120)
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    m = re.search(r'<meta name="vw" content="(\d+)x(\d+)"', r.stdout.decode("utf-8", "replace"))
    if not m:
        raise RuntimeError("could not measure the headless viewport")
    return 800 - int(m.group(1)), 600 - int(m.group(2))


# The page writes its self-check once its fonts are in (fonts.ready + 50 ms). --dump-dom fires when the virtual-time
# budget runs out; on a cold start under load (4 Chromes at once) the first pages have been dumped BEFORE the fonts
# settled (fix round 1: 2 of 51 pages in one run had no self-check and no error). A dump without the self-check is a harness timing miss, not a
# page result, so it is retried with a longer budget; every attempt is kept on the Render (attempts) and a page that
# never writes its check still fails.
BUDGETS = (10000, 20000, 40000)


def render(exe: str, stage_dir: pathlib.Path, work: pathlib.Path, query: dict, width: int, os_kind: str = "mac",
           tag: str = "r", chrome: bool = True, delta: tuple[int, int] = (0, 0)) -> Render:
    height = CONTENT_H[width] + (CHROME_H[os_kind] if chrome else 0)
    url = (stage_dir / "index.html").resolve().as_uri() + "?" + urllib.parse.urlencode(query)
    attempts = []
    for i, budget in enumerate(BUDGETS):
        prof = work / f"profile-{tag}-{i}"
        cmd = _chrome_cmd(exe, prof, (width + delta[0], height + delta[1]), url, budget)
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=180)
            dom, log = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
        except subprocess.TimeoutExpired as e:
            dom = (e.stdout or b"").decode("utf-8", "replace")
            log = (e.stderr or b"").decode("utf-8", "replace") + "\n[harness] timeout"
        finally:
            shutil.rmtree(prof, ignore_errors=True)
        out = Render(dom, log, query, (width, height))
        attempts.append(budget)
        out.attempts = attempts
        if out.raw_check is not None:
            break
    return out


class DomScan(html.parser.HTMLParser):
    """The dumped DOM as data: every tag with its attributes, and the text under each element class of interest."""

    def __init__(self, watch_classes: tuple[str, ...] = ()):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []
        self.watch = watch_classes
        self.stack: list[tuple[str, str | None]] = []
        self.text_in: dict[str, list[str]] = {c: [] for c in watch_classes}
        self.body_text: list[str] = []
        self.in_body = False

    VOID = {"meta", "link", "img", "br", "wbr", "input", "hr", "source", "path"}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if tag == "body":
            self.in_body = True
        if tag in self.VOID:
            return
        cls = (a.get("class") or "").split()
        hit = next((c for c in self.watch if c in cls), None)
        self.stack.append((tag, hit))

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.in_body:
            self.body_text.append(data)
        for _, hit in self.stack:
            if hit:
                self.text_in[hit].append(data)


def scan_dom(dom: str, watch_classes: tuple[str, ...] = ()) -> DomScan:
    p = DomScan(watch_classes)
    p.feed(dom)
    return p
