"""Render the After Effects CEP screens (A-01 to A-04) at 280 px, the CEP panel's minimum width, and check them.

    python adobe/panel-ui/design/_build/render_280.py [--states normal,focus] [--jobs 8]

mockup.js knows the widths 300 / 360 / 480 only, so each page is loaded with w=300 (the 300 px rules: 12 px gutters,
pill names only on a pill that is not ok) plus w280=1, which js/tools-ae.js turns into a 280 px panel. Capture and
checks are the same as render_all.py (it is imported, not copied): sentinel crop, not blank, the page's own self-check
(panel width 280, direction, mirroring, no sideways overflow, fonts, no missing string or icon).
Writes design/renders/<screen>/<state>-<lang>-280.png and one sheet, renders/_sheets/A-ae-280-normal.png.
It never touches manifest.csv. Prints one summary line; exit 1 when any check fails.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
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
sys.path.insert(0, str(HERE))
import render_all as R  # noqa: E402  (same capture window, scale, sentinel, browser lookup and sheet script)

W = 280


def job(exe: str, work: pathlib.Path, screen: str, page: pathlib.Path, state: str, lang: str) -> dict:
    url = page.resolve().as_uri() + f"?lang={lang}&w=300&w280=1&state={state}&capture=1"
    tag = f"{screen}-{state}-{lang}-{W}"
    out = R.RENDERS / screen / f"{state}-{lang}-{W}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = work / f"{tag}.png"
    R.chrome(exe, work, tag + "-s", [f"--force-device-scale-factor={R.SCALE}", f"--screenshot={tmp}"], url)
    dom = R.chrome(exe, work, tag + "-d", ["--dump-dom"], url, out_dom=True)
    row = {"path": out.relative_to(R.DESIGN).as_posix(), "problems": []}
    img = cv2.imdecode(np.fromfile(str(tmp), np.uint8), cv2.IMREAD_COLOR) if tmp.exists() else None
    if img is None:
        row["problems"].append("no screenshot")
        return row
    img = img[:, : W * R.SCALE]
    not_bg = np.any(np.abs(img.astype(int) - R.SENTINEL) > 24, axis=2)
    rows = np.where(not_bg.any(axis=1))[0]
    if len(rows) == 0:
        row["problems"].append("blank (sentinel only)")
        return row
    img = img[: rows[-1] + 1]
    if img.shape[0] >= R.WINDOW_H * R.SCALE - 2:
        row["problems"].append("taller than the capture window")
    if np.any(np.all(np.abs(img.astype(int) - R.SENTINEL) <= 24, axis=2)):
        row["problems"].append("sentinel inside the panel box (panel narrower than 280?)")
    ok, buf = cv2.imencode(".png", img)
    data = buf.tobytes()
    out.write_bytes(data)
    row["sha1"] = hashlib.sha1(data).hexdigest()
    if float(img.std()) < 8:
        row["problems"].append("near blank")
    m = re.search(r'<meta name="mock-check" content="([^"]*)"', dom)
    if not m:
        row["problems"].append("no self-check in the DOM")
        return row
    chk = dict(kv.split("=", 1) for kv in m.group(1).split(";") if "=" in kv)
    side = "right" if lang == "ar" else "left"
    if chk.get("state") != state:
        row["problems"].append(f"state {chk.get('state')}")
    if chk.get("w") != str(W):
        row["problems"].append(f"panel width {chk.get('w')}")
    if chk.get("dir") != ("rtl" if lang == "ar" else "ltr"):
        row["problems"].append(f"dir {chk.get('dir')}")
    if chk.get("mono") != side:
        row["problems"].append(f"monogram on the {chk.get('mono')}")
    if chk.get("tab1") not in ("none", side):
        row["problems"].append(f"first tab on the {chk.get('tab1')}")
    if chk.get("overflow") != "0":
        row["problems"].append(f"{chk.get('overflow')} elements overflow sideways ({chk.get('worst')})")
    if chk.get("fonts") != "ok":
        row["problems"].append("brand fonts not loaded")
    if chk.get("missing"):
        row["problems"].append(f"missing: {chk.get('missing')}")
    row["problems"].extend(R.rule_checks(chk))  # R3: the same rule fields as render_all.py (header, keycaps, violet, ...)
    if img.shape[1] != W * R.SCALE:
        row["problems"].append(f"png width {img.shape[1]}")
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", default="normal")
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    exe = R.browser()
    pages = sorted(R.SCREENS.glob("A-0*.html"))
    want = [s.strip() for s in a.states.split(",") if s.strip()]
    tasks = []
    for page in pages:
        have = R.states_of(page)
        for state in want:
            if state in have:
                for lang in R.LANGS:
                    tasks.append((page.stem, page, state, lang))
    work = pathlib.Path(tempfile.mkdtemp(prefix="mock_280_"))
    rows = []
    try:
        with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for f in cf.as_completed([ex.submit(job, exe, work, *t) for t in tasks]):
                rows.append(f.result())
    finally:
        shutil.rmtree(work, ignore_errors=True)
    rows.sort(key=lambda r: r["path"])
    script = R.SKILL / "contact_sheet.py"
    sheet = R.SHEETS / "A-ae-280-normal.png"
    imgs = [str(R.DESIGN / r["path"]) for r in rows if "normal-" in r["path"] and (R.DESIGN / r["path"]).exists()]
    if script.exists() and imgs:
        R.SHEETS.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, str(script), str(sheet), *imgs, "--cols", str(min(8, len(imgs))), "--cell", "1100",
                        "--bg", "dark", "--overwrite"], capture_output=True, timeout=600)
    bad = [r for r in rows if r["problems"]]
    for r in bad:
        print(f"FAIL {r['path']}: {'; '.join(r['problems'])}")
    print(f"render_280: {len(pages)} screens, {len(rows)} renders at {W} px, {len(rows) - len(bad)} ok, {len(bad)} failed"
          f"{', sheet ' + sheet.name if sheet.exists() else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
