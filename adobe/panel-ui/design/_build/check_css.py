"""Fail on CSS or markup the UXP kit cannot paint, in the mockup sources.

    python adobe/panel-ui/design/_build/check_css.py

Scans design/*.css, design/*.js (except the generated icons.js) and design/screens/*.html for the forbidden tokens
of the E-D2 brief: shadows, effects, the flex spacing property, the two-dimensional layout module, the native button
element, an SVG fill attribute, the inherited-colour keyword and logical inline margins. Prints one line per hit and a
summary line; exit 1 on any hit.
"""
from __future__ import annotations

import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")

DESIGN = pathlib.Path(__file__).resolve().parent.parent
FORBIDDEN = ["box-shadow", "filter", "gap:", "grid", "<button", 'fill="', "currentColor", "margin-inline"]


def main() -> int:
    files = sorted(DESIGN.glob("*.css")) + sorted(p for p in DESIGN.glob("*.js") if p.name != "icons.js") + sorted((DESIGN / "screens").glob("*.html"))
    hits = 0
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            low = line.lower()
            for tok in FORBIDDEN:
                if tok.lower() in low:
                    hits += 1
                    print(f"{f.relative_to(DESIGN).as_posix()}:{n}: forbidden '{tok}': {line.strip()[:100]}")
    print(f"check_css: {len(files)} files, {hits} forbidden hits")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
