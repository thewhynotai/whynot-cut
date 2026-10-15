"""Render every mockup screen x state x language x width to PNG, check each render, write manifest.csv, make sheets.

    python adobe/panel-ui/design/_build/render_all.py [--only P-03] [--jobs 8] [--no-sheets]

- Screens: adobe/panel-ui/design/screens/*.html; the states come from each file's <meta name="mock-states">. A page may
  declare its own widths with <meta name="mock-widths" content="760,640"> (default 300,360,480): the browser window
  follows the widths, the width check uses them, and its sheets use the page's first width as the reference width
  (default 360).
- Output: design/renders/<screen>/<state>-<lang>-<w>.png at 2x device scale, full height (the page is captured on a
  sentinel background with capture=1 and cropped to the panel's own box), dark colour scheme, throw-away profile.
- Checks per render: not blank (pixel variance), and the page's own self-check read with --dump-dom
  (<meta name="mock-check">): panel width, direction, AR mirrored (monogram and first tab on the right), no element
  wider than the panel (sideways overflow), brand fonts loaded, no missing string or icon.
- Writes design/manifest.csv (path, screen, state, lang, width, sha1, ...) and one contact sheet per screen and language
  into design/renders/_sheets/ with the brand-identity-pipeline skill's contact_sheet.py.
Only files under design/renders/ and design/manifest.csv are (re)written: they are this job's own output.
Prints one summary line; exit 1 when any check fails.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).resolve().parent
DESIGN = HERE.parent
SCREENS = DESIGN / "screens"
RENDERS = DESIGN / "renders"
SHEETS = RENDERS / "_sheets"
MANIFEST = DESIGN / "manifest.csv"
SKILL = pathlib.Path(os.path.expanduser("~")) / ".claude" / "skills" / "brand-identity-pipeline" / "scripts"
LANGS = ["en", "ar"]
WIDTHS = [300, 360, 480]
SCALE = 2
WINDOW_W, WINDOW_H = 520, 2600  # CSS px; the panel is drawn at its own width (JS), so the window only needs to be wider
SENTINEL = np.array([255, 0, 255])  # BGR of #FF00FF

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def browser() -> str:
    b = next((x for x in BROWSERS if os.path.exists(x)), None) or shutil.which("chrome") or shutil.which("chromium")
    if not b:
        sys.exit("no Chrome or Edge found")
    return b


def states_of(page: pathlib.Path) -> list[str]:
    m = re.search(r'<meta name="mock-states" content="([^"]+)"', page.read_text(encoding="utf-8"))
    if not m:
        sys.exit(f"{page.name}: no <meta name=\"mock-states\">")
    return [s.strip() for s in m.group(1).split(",") if s.strip()]


def widths_of(page: pathlib.Path) -> tuple[list[int], int]:
    """(widths, sheet reference width): the page's <meta name="mock-widths">, else (WIDTHS, 360)."""
    m = re.search(r'<meta name="mock-widths" content="([^"]+)"', page.read_text(encoding="utf-8"))
    if not m:
        return WIDTHS, 360
    ws = [int(x) for x in m.group(1).split(",") if x.strip()]
    return ws, ws[0]


def chrome(exe: str, work: pathlib.Path, tag: str, extra: list[str], url: str, out_dom: bool = False,
           win_w: int = WINDOW_W) -> str:
    prof = work / f"p-{tag}"
    cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
           "--allow-file-access-from-files", f"--user-data-dir={prof}", f"--window-size={win_w},{WINDOW_H}",
           "--virtual-time-budget=4000", "--blink-settings=preferredColorScheme=0", *extra, url]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        return r.stdout.decode("utf-8", "replace") if out_dom else ""
    except subprocess.TimeoutExpired:
        return ""
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def job(exe: str, work: pathlib.Path, screen: str, page: pathlib.Path, state: str, lang: str, w: int) -> dict:
    url = page.resolve().as_uri() + f"?lang={lang}&w={w}&state={state}&capture=1"
    tag = f"{screen}-{state}-{lang}-{w}"
    out = RENDERS / screen / f"{state}-{lang}-{w}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = work / f"{tag}.png"
    win_w = max(WINDOW_W, w + 40)  # wider pages (mock-widths) get a wider window; panels keep 520
    chrome(exe, work, tag + "-s", [f"--force-device-scale-factor={SCALE}", f"--screenshot={tmp}"], url, win_w=win_w)
    dom = chrome(exe, work, tag + "-d", ["--dump-dom"], url, out_dom=True, win_w=win_w)
    row = {"path": out.relative_to(DESIGN).as_posix(), "screen": screen, "state": state, "lang": lang, "width": w,
           "sha1": "", "px_w": 0, "px_h": 0, "std": 0.0, "check": "", "problems": []}
    img = cv2.imdecode(np.fromfile(str(tmp), np.uint8), cv2.IMREAD_COLOR) if tmp.exists() else None
    if img is None:
        row["problems"].append("no screenshot")
        return row
    img = img[:, : w * SCALE]
    not_bg = np.any(np.abs(img.astype(int) - SENTINEL) > 24, axis=2)
    rows = np.where(not_bg.any(axis=1))[0]
    if len(rows) == 0:
        row["problems"].append("blank (sentinel only)")
        return row
    img = img[: rows[-1] + 1]
    if img.shape[0] >= WINDOW_H * SCALE - 2:
        row["problems"].append("taller than the capture window")
    if np.any(np.all(np.abs(img.astype(int) - SENTINEL) <= 24, axis=2)):
        row["problems"].append("sentinel inside the panel box")
    ok, buf = cv2.imencode(".png", img)
    data = buf.tobytes()
    out.write_bytes(data)
    row.update(sha1=hashlib.sha1(data).hexdigest(), px_w=img.shape[1], px_h=img.shape[0], std=float(img.std()))
    if row["std"] < 8 or len(data) < 15000:
        row["problems"].append(f"near blank (std {row['std']:.1f}, {len(data)} B)")
    m = re.search(r'<meta name="mock-check" content="([^"]*)"', dom)
    if not m:
        row["problems"].append("no self-check in the DOM")
        return row
    chk = dict(kv.split("=", 1) for kv in m.group(1).split(";") if "=" in kv)
    row["check"] = m.group(1)
    want_side = "right" if lang == "ar" else "left"
    if chk.get("state") != state:
        row["problems"].append(f"state {chk.get('state')}")
    if chk.get("w") != str(w):
        row["problems"].append(f"panel width {chk.get('w')}")
    if chk.get("dir") != ("rtl" if lang == "ar" else "ltr"):
        row["problems"].append(f"dir {chk.get('dir')}")
    if chk.get("mono") != want_side:
        row["problems"].append(f"monogram on the {chk.get('mono')}")
    if chk.get("tab1") not in ("none", want_side):
        row["problems"].append(f"first tab on the {chk.get('tab1')}")
    if chk.get("overflow") != "0":
        row["problems"].append(f"{chk.get('overflow')} elements overflow sideways ({chk.get('worst')})")
    if chk.get("fonts") != "ok":
        row["problems"].append("brand fonts not loaded")
    if chk.get("missing"):
        row["problems"].append(f"missing: {chk.get('missing')}")
    # R2 page self-checks: the header status never says "All set" over an open card or a Needs-you badge; a danger or
    # destructive action never carries a keycap; one live violet fill per screen
    if chk.get("statuslie", "0") != "0":
        row["problems"].append("header says All set over an open card or a Needs-you badge")
    if chk.get("dangerkbd", "0") != "0":
        row["problems"].append(f"{chk.get('dangerkbd')} keycap(s) on a danger or destructive button")
    if chk.get("violet", "0").isdigit() and int(chk.get("violet", "0")) > 1:
        row["problems"].append(f"{chk.get('violet')} live violet fills (one per screen)")
    if row["px_w"] != w * SCALE:
        row["problems"].append(f"png width {row['px_w']}")
    return row


def sheets(rows: list[dict], widths: dict) -> list[pathlib.Path]:
    script = SKILL / "contact_sheet.py"
    if not script.exists():
        print(f"skip sheets: {script} not found")
        return []
    SHEETS.mkdir(parents=True, exist_ok=True)
    made = []

    def sheet(out: pathlib.Path, imgs: list[str], cols: int) -> None:
        if not imgs:
            return
        subprocess.run([sys.executable, str(script), str(out), *imgs, "--cols", str(cols), "--cell", "1100", "--bg", "dark",
                        "--overwrite"], capture_output=True, timeout=600)
        if out.exists():
            made.append(out)

    # panels are tall, so a sheet holds one width: every state at the 360 reference width, per language,
    # plus one sheet per screen with the normal state at all three widths in both languages
    for screen in sorted({r["screen"] for r in rows}):
        mine = [r for r in rows if r["screen"] == screen and r["sha1"]]
        ws, ref = widths.get(screen, (WIDTHS, 360))
        for lang in LANGS:
            imgs = [str(DESIGN / r["path"]) for r in mine if r["lang"] == lang and r["width"] == ref]
            sheet(SHEETS / f"{screen}-states-{lang}-{ref}.png", imgs, min(6, len(imgs)))
        imgs = [str(DESIGN / r["path"]) for lang in LANGS for w in ws for r in mine
                if r["state"] == "normal" and r["lang"] == lang and r["width"] == w]
        sheet(SHEETS / f"{screen}-widths-normal.png", imgs, 6)
    return made


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one screen id prefix, e.g. P-03")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--no-sheets", action="store_true")
    a = ap.parse_args()
    exe = browser()
    pages = sorted(SCREENS.glob("*.html"))
    if a.only:
        pages = [p for p in pages if p.stem.startswith(a.only)]
    work = pathlib.Path(tempfile.mkdtemp(prefix="mock_render_"))
    tasks = []
    widths = {page.stem: widths_of(page) for page in pages}
    for page in pages:
        screen = page.stem
        for state in states_of(page):
            for lang in LANGS:
                for w in widths[screen][0]:
                    tasks.append((screen, page, state, lang, w))
    rows: list[dict] = []
    try:
        with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = [ex.submit(job, exe, work, *t) for t in tasks]
            for f in cf.as_completed(futs):
                rows.append(f.result())
    finally:
        shutil.rmtree(work, ignore_errors=True)
    rows.sort(key=lambda r: (r["screen"], r["state"], r["lang"], r["width"]))
    if not a.only:
        # drop this job's own renders of states that no longer exist (renders/ is generated output only)
        current = {(DESIGN / r["path"]).resolve() for r in rows}
        for page in pages:
            for old in (RENDERS / page.stem).glob("*.png"):
                if old.resolve() not in current:
                    old.unlink()
        with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
            wr = csv.writer(fh)
            wr.writerow(["path", "screen", "state", "lang", "width", "sha1", "png_w", "png_h", "pixel_std", "ok", "problems"])
            for r in rows:
                wr.writerow([r["path"], r["screen"], r["state"], r["lang"], r["width"], r["sha1"], r["px_w"], r["px_h"],
                             f"{r['std']:.1f}", "yes" if not r["problems"] else "no", " | ".join(r["problems"])])
    made = [] if a.no_sheets else sheets(rows, widths)
    bad = [r for r in rows if r["problems"]]
    for r in bad:
        print(f"FAIL {r['path']}: {'; '.join(r['problems'])}")
    n_states = len({(r['screen'], r['state']) for r in rows})
    print(f"render_all: {len(pages)} screens, {n_states} states, {len(rows)} renders, {len(rows) - len(bad)} ok, "
          f"{len(bad)} failed, {len(made)} sheets -> {RENDERS}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
