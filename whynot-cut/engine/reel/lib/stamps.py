"""engine_version stamps on compiled artefacts (3.0 T2.3, engine MI-11).

The compilers write the engine's version (the plugin version, `.claude-plugin/plugin.json`) into what they compile:
01_analysis/timeline-spec.json (`reel plan`), 01_analysis/motion-plan.json (`reel motion-plan`) and an episode's
01_analysis/reels-plan-validated.json (`reel reels-plan`). The steps that consume them read through `read_compiled`:
    same major and minor (patch may differ)  -> silent
    another minor version, or no stamp (2.x) -> a warning, collected on the request's Context and printed with the
                                                command's JSON as `version_warnings` (lib/errors.emit)
    another major version                    -> refused: Guidance "re-run `reel plan`" (or the artefact's compiler)
"""
from __future__ import annotations

import re
from pathlib import Path

_VER = re.compile(r"\s*(\d+)\.(\d+)")
COMPILERS = {"timeline-spec.json": "reel plan", "motion-plan.json": "reel motion-plan",
             "reels-plan-validated.json": "reel reels-plan --episode <EP>"}


def engine_version() -> str:
    from .selfid import plugin_info
    return str(plugin_info().get("version") or "?")


def _major_minor(v) -> tuple[int, int] | None:
    m = _VER.match(str(v or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def compare(found, current: str | None = None) -> str:
    """'same' (major.minor equal) | 'minor' | 'major' | 'missing' (no stamp) | 'unknown' (unreadable version)."""
    if found in (None, ""):
        return "missing"
    a, b = _major_minor(found), _major_minor(current or engine_version())
    if a is None or b is None:
        return "unknown"
    if a[0] != b[0]:
        return "major"
    return "same" if a[1] == b[1] else "minor"


def _note(msg: str) -> None:
    from .common import current_context
    ctx = current_context()
    notes = getattr(ctx, "version_warnings", None)
    if notes is None:
        notes = ctx.version_warnings = []
    if msg not in notes:
        notes.append(msg)


def check(doc, path, rerun: str | None = None) -> str | None:
    """Refuse (Guidance) an artefact compiled by another major engine version; return (and note on the Context) the
    warning for another minor version or a missing stamp; None when it matches."""
    from .errors import Guidance
    if not isinstance(doc, dict):
        return None
    name = Path(path).name
    rerun = rerun or COMPILERS.get(name, "the step that compiles it")
    found, now = doc.get("engine_version"), engine_version()
    state = compare(found, now)
    if state == "major":
        raise Guidance(f"{name} was compiled by WhyNot Cut {found}; this is {now}, a different major version whose "
                       "steps read it differently", f"Re-run `{rerun}` to compile it again with this version, then "
                       "run this command again", where=str(path))
    if state == "same":
        return None
    msg = (f"{name} has no engine_version (compiled before 3.0): re-run `{rerun}` if anything looks off"
           if state == "missing" else
           f"{name} was compiled by WhyNot Cut {found}, this is {now}: re-run `{rerun}` to pick up this version's changes")
    _note(msg)
    return msg


def read_compiled(path, default=None, rerun: str | None = None):
    """read_json + check(): what consumers of a compiled artefact use."""
    from .common import read_json
    doc = read_json(path, default)
    if doc:
        check(doc, path, rerun)
    return doc


def stamp(doc: dict) -> dict:
    """A copy of doc with `engine_version` (this engine's version) set."""
    return dict(doc, engine_version=engine_version())
