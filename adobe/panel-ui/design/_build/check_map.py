"""The coverage map and the screen files agree (coverage map §4 A-1; executor ruling 2026-10-18 §5.4).

    python adobe/panel-ui/design/_build/check_map.py [--self-test]

- Every screen ID the map names (P-07, A-03, I-05, J-02, ...) has a file in design/screens/ (P-07-approval.html).
- Every screen file is named in the map at least once.
- A range written "X-01…X-09" (or "X-01...X-09") counts as every ID in it; an ID written "NEW P-2x" (proposed, not drawn
  yet) is skipped.
Read-only. It never runs in tools/test.sh and never blocks an engine commit: the rule is enforced at the executor's
acceptance (the check is a tool for that). Prints one line per problem and a summary; exit 1 on any problem.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DESIGN = pathlib.Path(__file__).resolve().parent.parent
REPO = DESIGN.parents[2]
MAP = REPO / "docs" / "superpowers" / "specs" / "ui-coverage-map.md"
SCREENS = DESIGN / "screens"

RANGE = re.compile(r"\b([PAIJ])-(\d{2})\s*(?:…|\.\.\.)\s*\1-(\d{2})\b")
NEW = re.compile(r"\bNEW\s+[PAIJ]-\d{2}\b")
ID = re.compile(r"(?<![\w-])([PAIJ])-(\d{2})(?![\w])")


def ids_in(text: str) -> set[str]:
    """The screen IDs a text names: ranges expanded, "NEW X-nn" skipped."""
    out: set[str] = set()
    for m in RANGE.finditer(text):
        for n in range(int(m.group(2)), int(m.group(3)) + 1):
            out.add(f"{m.group(1)}-{n:02d}")
    text = RANGE.sub(" ", NEW.sub(" ", text))
    for m in ID.finditer(text):
        out.add(f"{m.group(1)}-{m.group(2)}")
    return out


def files_ids() -> set[str]:
    return {m.group(0) for f in SCREENS.glob("*.html") if (m := re.match(r"[PAIJ]-\d{2}", f.name))}


def check(map_text: str, on_disk: set[str]) -> list[str]:
    named = ids_in(map_text)
    problems = [f"named in the map, no screen file: {i}" for i in sorted(named - on_disk)]
    problems += [f"screen file not named in the map: {i}" for i in sorted(on_disk - named)]
    return problems


def self_test() -> int:
    text = "P-01…P-03 · A-02 · NEW P-27 · I-01...I-02 · see P-10 `verse` · K-T1 is not a screen · J-01"
    got = ids_in(text)
    want = {"P-01", "P-02", "P-03", "A-02", "I-01", "I-02", "P-10", "J-01"}
    assert got == want, got
    assert check(text, want | {"P-99"}) == ["screen file not named in the map: P-99"]
    assert check(text + " P-50", want) == ["named in the map, no screen file: P-50"]
    print("check_map self-test: ok")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    problems = check(MAP.read_text(encoding="utf-8"), files_ids())
    for p in problems:
        print(p)
    print(f"check_map: {len(files_ids())} screen files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
