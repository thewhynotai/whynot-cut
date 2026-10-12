"""List options of the `reel` CLI (3.0 T2.16, engine MI-5).

Every list option takes a comma list, the option repeated, or both: `--pick R01,R03`, `--pick R01 --pick R03` and
`--confirm-avoid R05,R06` all mean the same list (before, `--confirm-avoid R05,R06` silently matched nothing). Options
whose items may themselves hold a comma split only where the next item starts (`start`): `--adjust R03:in=00:12:04,000`
keeps its SRT-style time, `--set a=1,b=2` splits before `b=`.
"""
from __future__ import annotations

import re

ADJUST_START = r"[A-Za-z]+\d+\s*:"                # R03:in=..., T02:out=...
SETTING_START = r"[A-Za-z_][A-Za-z0-9_]*\s*="     # key=value


def items(values, start: str | None = None) -> list[str]:
    """The items of a list option's values (a string, or the list argparse collects with action="append"): split on
    commas (only before `start` when given), stripped, blanks and repeats dropped, order kept."""
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    sep = re.compile(r",\s*(?=" + start + ")") if start else re.compile(",")
    out: list[str] = []
    for v in values:
        for part in sep.split(str(v)):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def int_items(values, what: str) -> list[int]:
    """items() as whole numbers (`--words 79,80`); a value that is not one is a clear error, not a traceback."""
    out = []
    for x in items(values):
        try:
            out.append(int(x))
        except ValueError:
            raise SystemExit(f"{what}: {x!r} is not a whole number (e.g. 79,80)") from None
    return out
