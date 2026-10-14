"""Mockup icons: outline the vendored Lucide icons (stroke) into fill-only paths, per size.

    python adobe/panel-ui/design/_build/build_icons.py

Source: whynot-cut/templates/motion/icons/lucide/ (lucide-static, pinned, ISC), read-only.
Direction §9: UXP colours an SVG only through CSS `fill`, so every icon becomes one fill path. The absolute stroke is
1.5 px at 16 and 20 px and 1.25 px at 12 px, so each size gets its own outline:
    12 px -> 2.5 units, 16 px -> 2.25 units, 20 px -> 1.8 units (in Lucide's 24-unit box).
Method (no vector library on this PC): headless Chrome rasterises each stroked icon at 40 px per unit with round caps
and joins, OpenCV traces the outline (outer contours and holes), and the polygon is simplified to within 0.02 units.
Outer outlines and holes are written in opposite directions, so the paths fill correctly under nonzero; the
mockups also set fill-rule="evenodd" on every path (belt and braces for UXP). Good to well under a pixel at 12-20 px; a production
build may swap this for a true stroke-to-path step.
Writes adobe/panel-ui/design/icons.js (window.MOCK_ICONS = {name: {"12": d, "16": d, "20": d}}).
"""
from __future__ import annotations

import concurrent.futures as cf
import json
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
REPO = DESIGN.parents[2]
LUCIDE = REPO / "whynot-cut" / "templates" / "motion" / "icons" / "lucide"
OUT = DESIGN / "icons.js"

NAMES = [
    # status (direction §9)
    "circle-check", "triangle-alert", "circle-x", "info", "circle-dashed", "loader-circle",
    # verbs and tools
    "folder-input", "clapperboard", "circle-check-big", "folder-tree", "audio-waveform", "captions",
    # navigation and actions
    "chevron-right", "chevron-left", "chevron-down", "chevron-up", "check", "x", "settings", "package", "play", "message-square",
    "copy", "folder-open", "refresh-cw", "external-link", "power", "stethoscope", "book-open",
]
# fan-out: each screen group adds its own names in _build/icons-<group>.txt (one per line, # comments)
for _extra in sorted(HERE.glob("icons-*.txt")):
    for _line in _extra.read_text(encoding="utf-8").splitlines():
        _name = _line.split("#", 1)[0].strip()
        if _name and _name not in NAMES:
            NAMES.append(_name)
STROKE = {12: 2.5, 16: 2.25, 20: 1.8}
PPU = 40  # pixels per Lucide unit
CELL = 24 * PPU

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def browser() -> str:
    b = next((x for x in BROWSERS if os.path.exists(x)), None) or shutil.which("chrome")
    if not b:
        sys.exit("no Chrome or Edge found")
    return b


def stroked_svg(name: str, width: float) -> str:
    src = (LUCIDE / f"{name}.svg").read_text(encoding="utf-8")
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = src.replace('stroke="currentColor"', 'stroke="#000"')
    src = re.sub(r'stroke-width="[^"]*"', f'stroke-width="{width}"', src)
    src = re.sub(r'width="24"', f'width="{CELL}"', src, count=1)
    src = re.sub(r'height="24"', f'height="{CELL}"', src, count=1)
    return src


def raster(name: str, size: int, work: pathlib.Path, exe: str) -> np.ndarray:
    page = work / f"{name}-{size}.html"
    png = work / f"{name}-{size}.png"
    page.write_text(
        "<!doctype html><meta charset='utf-8'><style>html,body{margin:0;background:#fff}svg{display:block}</style>"
        + stroked_svg(name, STROKE[size]), encoding="utf-8")
    prof = work / f"prof-{name}-{size}"
    cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           f"--user-data-dir={prof}", f"--window-size={CELL},{CELL}", "--force-device-scale-factor=1",
           "--virtual-time-budget=500", "--blink-settings=preferredColorScheme=1",
           f"--screenshot={png}", page.as_uri()]
    for attempt in range(3):  # a headless Chrome can hang when the machine is busy: retry with a fresh profile
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            if png.exists():
                break
        except subprocess.TimeoutExpired:
            pass
        shutil.rmtree(prof, ignore_errors=True)
    img = cv2.imdecode(np.fromfile(str(png), np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"raster failed: {name} {size}")
    return img[:CELL, :CELL]


def trace(img: np.ndarray) -> str:
    mask = (img < 128).astype(np.uint8) * 255
    contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    for i, c in enumerate(contours):
        if cv2.contourArea(c) < 4:
            continue
        poly = cv2.approxPolyDP(c, 0.8, True).reshape(-1, 2)
        if len(poly) < 3:
            continue
        # Path direction: outer outlines clockwise on screen (positive signed area in y-down image space), holes
        # counter-clockwise, so the icon fills correctly under the default nonzero rule as well as under evenodd.
        is_hole = hier[0][i][3] != -1
        area = cv2.contourArea(poly.reshape(-1, 1, 2).astype(np.float32), oriented=True)
        if (area > 0) == is_hole:
            poly = poly[::-1]
        pts = [((x + 0.5) / PPU, (y + 0.5) / PPU) for x, y in poly]
        d = "M" + " ".join(f"{x:.2f} {y:.2f}".replace(".00", "") for x, y in pts) + "Z"
        parts.append(d)
    return "".join(parts)


def main() -> int:
    missing = [n for n in NAMES if not (LUCIDE / f"{n}.svg").exists()]
    if missing:
        sys.exit(f"not in the vendored Lucide set: {missing}")
    version = "unknown"
    try:
        version = json.loads((LUCIDE / "icons.json").read_text(encoding="utf-8")).get("version", version)
    except Exception:
        pass
    exe = browser()
    work = pathlib.Path(tempfile.mkdtemp(prefix="mock_icons_"))
    jobs = [(n, s) for n in NAMES for s in STROKE]
    out: dict[str, dict[str, str]] = {n: {} for n in NAMES}
    try:
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(raster, n, s, work, exe): (n, s) for n, s in jobs}
            for f in cf.as_completed(futs):
                n, s = futs[f]
                out[n][str(s)] = trace(f.result())
    finally:
        shutil.rmtree(work, ignore_errors=True)
    empty = [f"{n}@{s}" for n in out for s, d in out[n].items() if not d]
    if empty:
        sys.exit(f"empty outlines: {empty}")
    body = json.dumps(out, separators=(",", ":"), sort_keys=True)
    OUT.write_text(
        "/* GENERATED by _build/build_icons.py. Do not edit.\n"
        f"   Lucide (lucide-static {version}, ISC, vendored in whynot-cut/templates/motion/icons/lucide/), strokes outlined\n"
        "   into fill paths per size (12: 1.25 px, 16 and 20: 1.5 px absolute stroke). Coloured by CSS fill classes only. */\n"
        f"window.MOCK_ICONS={body};\n", encoding="utf-8")
    print(f"icons: {len(NAMES)} names x {len(STROKE)} sizes -> {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
