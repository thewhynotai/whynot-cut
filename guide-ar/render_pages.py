#!/usr/bin/env python3
"""Render every page of a PDF to PNG for visual QC (not part of the build).

    python guide-ar/render_pages.py <pdf> <out_dir> [--scale 1.5]

Writes page-001.png, page-002.png … into out_dir and prints the page count.
Needs pypdfium2 and Pillow (pip install pypdfium2 pillow) — use any venv that has
them; keep the PNGs outside the repo.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--scale", type=float, default=1.5, help="1.0 = 72 dpi (default 1.5 = 108 dpi)")
    args = ap.parse_args(argv)
    try:
        import pypdfium2 as pdfium
    except ImportError:
        print("pypdfium2 is missing: pip install pypdfium2 pillow (in a separate QC venv)", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(args.pdf))
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            image = page.render(scale=args.scale).to_pil()
            image.save(args.out_dir / f"page-{i + 1:03d}.png")
            page.close()
        count = len(pdf)
    finally:
        pdf.close()
    print(count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
