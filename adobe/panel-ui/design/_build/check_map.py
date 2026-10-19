"""The coverage map and the screen files agree (coverage map §4 A-1; executor ruling 2026-10-18 §5.4).

    python adobe/panel-ui/design/_build/check_map.py [--self-test]

- Every screen ID the map names (P-07, A-03, I-05, J-02, ...) has a file in design/screens/ (P-07-approval.html).
- Every screen file is named in the map at least once.
- Every state the map names right after a screen ID ("P-10 `verse`, `risky`") is one of that screen's mock-states; a
  backticked word followed by "row" ("P-10 `words` row") is a row of the screen, not a state, and is not checked.
- A range "X-01…X-09" (also "...", "–" or "-" between two IDs, and in either order) counts as every ID in it.
- A proposed screen is skipped wherever it is marked NEW: "NEW P-27", "**NEW** P-27", "NEW: P-27", and every ID of a
  "NEW P-25/P-27" list or a "NEW P-25…P-27" range.
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

ONE = r"[PAIJ]-\d{2}"
# a NEW marker, then one ID, a range of IDs, or a slash list of IDs: all proposed, all skipped
NEW = re.compile(rf"(?:\*\*)?\bNEW\b(?:\*\*)?:?\s+(?:{ONE}(?:\s*(?:…|\.\.\.|–|-|/)\s*{ONE})*)")
RANGE = re.compile(r"\b([PAIJ])-(\d{2})\s*(?:…|\.\.\.|–)\s*\1-(\d{2})\b")
ID = re.compile(r"(?<![\w-])([PAIJ])-(\d{2})(?![\w])")
# a screen ID followed by its backticked states: "P-10 `verse`, `risky`" / "P-06 `autopilot`, `autopilot-stopped`"
STATES_AFTER = re.compile(rf"(?<![\w-])({ONE})((?:\s*,?\s*(?:and\s+)?`[a-z0-9][a-z0-9-]*`(?:\s+row\b)?)+)")
STATE_TOKEN = re.compile(r"`([a-z0-9][a-z0-9-]*)`(\s+row\b)?")


def strip_new(text: str) -> str:
    return NEW.sub(" ", text)


def ids_in(text: str) -> set[str]:
    """The screen IDs a text names: ranges expanded (either order), NEW-marked IDs skipped."""
    text = strip_new(text)
    out: set[str] = set()
    for m in RANGE.finditer(text):
        a, b = sorted((int(m.group(2)), int(m.group(3))))
        for n in range(a, b + 1):
            out.add(f"{m.group(1)}-{n:02d}")
    text = RANGE.sub(" ", text)
    for m in ID.finditer(text):
        out.add(f"{m.group(1)}-{m.group(2)}")
    return out


def states_named(text: str) -> list[tuple[str, str]]:
    """(screen id, state) pairs the text names right after a screen ID; "row" words are left out."""
    out = []
    for m in STATES_AFTER.finditer(strip_new(text)):
        for t in STATE_TOKEN.finditer(m.group(2)):
            if not t.group(2):
                out.append((m.group(1), t.group(1)))
    return out


def screen_states() -> dict[str, set[str]]:
    out = {}
    for f in SCREENS.glob("*.html"):
        m = re.match(ONE, f.name)
        meta = re.search(r'<meta name="mock-states" content="([^"]*)"', f.read_text(encoding="utf-8"))
        if m:
            out[m.group(0)] = {s.strip() for s in (meta.group(1).split(",") if meta else [])}
    return out


def check(map_text: str, states: dict[str, set[str]]) -> list[str]:
    on_disk = set(states)
    named = ids_in(map_text)
    problems = [f"named in the map, no screen file: {i}" for i in sorted(named - on_disk)]
    problems += [f"screen file not named in the map: {i}" for i in sorted(on_disk - named)]
    for sid, st in states_named(map_text):
        if sid in states and st not in states[sid]:
            problems.append(f"state named in the map, not in {sid}'s mock-states: {sid} `{st}`")
    return problems


def self_test() -> int:
    text = "P-01…P-03 · A-02 · NEW P-27 · I-01...I-02 · see P-10 `verse` · K-T1 is not a screen · J-01"
    got = ids_in(text)
    want = {"P-01", "P-02", "P-03", "A-02", "I-01", "I-02", "P-10", "J-01"}
    assert got == want, got
    all_states = {i: {"normal"} for i in want}
    all_states["P-10"] = {"normal", "verse"}
    assert check(text, {**all_states, "P-99": set()}) == ["screen file not named in the map: P-99"]
    assert check(text + " P-50", all_states) == ["named in the map, no screen file: P-50"]
    # reversed and en-dash ranges
    assert ids_in("P-09…P-07") == {"P-07", "P-08", "P-09"}, ids_in("P-09…P-07")
    assert ids_in("A-01–A-03") == {"A-01", "A-02", "A-03"}
    # NEW variants: a range, a slash list, bold, a colon, a newline after NEW
    assert ids_in("NEW P-25…P-27 and P-05") == {"P-05"}, ids_in("NEW P-25…P-27 and P-05")
    assert ids_in("NEW P-25/P-27") == set()
    assert ids_in("**NEW** P-27, NEW: P-28, → NEW\n   P-29") == set()
    # states after an ID; a "row" word is not a state
    assert states_named("P-10 `verse`, `risky` and P-06 `done-verse`; P-10 `words` row") == [("P-10", "verse"), ("P-10", "risky"), ("P-06", "done-verse")]
    bad = check("P-10 `nope` · P-01…P-03 · A-02 · I-01…I-02 · J-01", all_states)
    assert bad == ["state named in the map, not in P-10's mock-states: P-10 `nope`"], bad
    print("check_map self-test: ok")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    states = screen_states()
    problems = check(MAP.read_text(encoding="utf-8"), states)
    for p in problems:
        print(p)
    print(f"check_map: {len(states)} screen files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
