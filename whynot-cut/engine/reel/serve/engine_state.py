"""The engine state `reel serve` shows in the panel (3.0 Addendum C2.3 / C2.4). Read only: nothing here writes a file.

active.json
    <engine home>/state/active.json (contract/engine_state.schema.json): {client_root, item, stage, session_id,
    claude_pid, at}. The `reel` writer commands write it (T6.2b, the executor's part). It is read defensively. Each of
    these means "no item": a missing file, one over ACTIVE_MAX (64 KiB), one that is not UTF-8 JSON or breaks the
    schema, an `at` more than STALE_S (12 h) old or more than SKEW_S in the future, a client_root that is relative, has
    a '..' segment or is not a folder, an item that is not one plain folder name (lib/common.py:420
    check_project_id), and an item folder that resolves outside <client_root>/output/projects.
    A network client_root (UNC, \\\\nas\\share\\... or //nas/share/...) is accepted: NAS client folders are real. Its
    existence check is timed; one that takes longer than UNC_PROBE_S marks that root slow and it is skipped ("no
    item", logged once) for UNC_RETRY_S, so a dead share is not touched on every 2 s poll. A check that never returns
    is bounded by the daemon (serve/app.py: one engine-state worker, FIELDS_TIMEOUT).

Reading a file (every read here)
    A file is read only when it is a regular file (S_ISREG: never a FIFO, device or socket, so no read can block on
    one), at most its cap (EVIDENCE_MAX unless stated), resolves inside its folder (an item's evidence: the item folder
    <client_root>/output/projects/<item>; a client file: the client folder; a shipped config: the plugin folder) and,
    for client files, has one link (st_nlink 1: a hard link needs no privilege on Windows and would show another file's
    text or verdict). It is opened through the resolved path that was checked, non-blocking, and checked again on the
    open handle (fstat) before a byte is read. Anything else reads as "not there".
    The engine's own helpers (lib/plan.py approval_state / plan_fingerprint, lib/motion_plan.py fingerprint,
    lib/common.py seq_fps) read files with no cap. Before one is called, every file it will read is checked the same
    way (a missing file is fine: the helper has a default); if any is refused the helper is not called (no approval /
    no fingerprint / the default sequence rate SEQ_FPS). The files are listed in _approval_inputs, _motion_inputs and
    _config_files, from the helpers' code.

PanelState from the item's evidence files (panel_fields)
    Every path is relative to the item folder <client_root>/output/projects/<item> (lib/common.py:449 Paths) and is the
    one the engine's own writer uses; no file is invented. A file that is refused (above) or not a JSON object reads
    as "not there". A motion item is one whose 00_inputs/source.json has kind "motion_reel"
    (lib/motion_config.py:24-31). Line numbers are those of release/3.0 at 47cca9b (engine/reel/...).
      transcript  02_transcription/transcript.json exists (cli.py:822, cmd_next)
      plan        01_analysis/timeline-spec.json exists (cli.py:826); motion: 01_analysis/motion-plan.json exists and
                  motion-validation.json `ok` is true, failed when false (motion_qc.py:195, motion_plan.py:744-746)
      approve     lib/plan.py approval_state (plan.py:945) over 01_analysis/plan-approval.json {approved, by, at,
                  plan_fingerprint, format[, kind]} (cli.py:488, 496): "current" -> done; a compiled plan without a
                  current approval -> waiting, with the approval card
      build       07_premiere/ppro-build-result.json `status`: PRPROJ_BUILT and PRPROJ_BUILT_WITH_ISSUES -> done,
                  FAILED -> failed (ppro_build.py:367); motion: 04_after_effects/motion-build-result.json `status`
                  PROJECT_ASSEMBLED -> done (motion_build.py:108, motion_qc.py:199)
      frames      08_quality_control/visual-verification.json `verdict`: pass -> done, fail -> failed
                  (verify.py:306-308, motion_qc.py:41-43)
      qc          08_quality_control/qc-results.json `ok`: true -> done, false -> failed (qc.py:291-292,
                  motion_qc.py:175)
      approval inputs (_approval_inputs): plan-approval.json, plus the motion fingerprint's inputs only for a motion
                  item or a record of kind "motion" (T4.6: the data/Music folders are watched and listed, and the
                  licence files, music.json and the tracks the music choice reads are watched, so the panel recomputes
                  when a licence or track changes; the engine reads them itself, capped and link-safe, so they are not
                  inputs), plus timeline-spec.json unless the record is of kind "motion"
      handoff     09_handoff/README.md exists (cli.py:835)
    Approval card (only while the approve step is waiting):
      fingerprint the current plan's, what approve-plan records: lib/plan.py plan_fingerprint (plan.py:912,
                  cli.py:496); motion: motion-validation.json `fingerprint` when it equals lib/motion_plan.py
                  fingerprint() now (cli.py:480-488). No current fingerprint -> no card.
      summary     01_analysis/edit-plan.md (plan.py:1042); motion: 01_analysis/motion-plan.md (motion_plan.py:804),
                  made for the editor by editor_summary: those files end with chat instructions and commands
                  ("**To approve:** reply 'approved' ... `reel approve-plan`", plan.py:1041; "Animatic: <path> | not
                  rendered yet (`reel motion-animatic`)" and "**To approve:** ... the lead records `reel approve-plan
                  --by editor`", motion_plan.py:802-803). Those footers are removed by structure (the "**To
                  approve:**" paragraph, the "Animatic: " line). Everything else keeps every line and table row (the
                  editor approves those rows: "Watch this reel", "Reply to the doctor", "Ask Claude" stay); commands
                  are removed token by token: a code span that looks like a command (it has a space, or starts with
                  reel / claude / npm / npx / python / py) goes, a one-word span stays as its plain word; `reel` +
                  a registered subcommand (cli.registered_commands) or a flag goes with its flags; `claude --flag`
                  goes; "Claude Code" reads "Claude"; no backtick is left. Headings, bold and links are collapsed to
                  plain text (a table row reads "a · b · c"; "__" is left alone: My_reel__v2 is a file name);
                  clipped to SUMMARY_MAX characters
      preview_mp4 08_quality_control/preview/<item>_preview.mp4 (cli.py:828); motion:
                  08_quality_control/animatic/<item>_animatic.mp4 (motion_qc.py:190); null when absent
      flagged     []: no evidence file carries the medical / religious flags (the reviewers report to the lead)
    QC tiles (at most QC_MAX):
      the newest 08_quality_control/premiere_frames/run-*/ folder (ppro_build.py:479): every frame_<ms>.png
      (adobe/premiere-uxp/src/ops/export-frames.ts:30; the first token of ASCII digits is the ms, ppro_build.py:
      492-493), t_s = ms / 1000, tc = frame_to_tc at the sequence rate (ppro_build.py:524), label "" (the engine keeps
      no per-frame label). Motion: the newest 08_quality_control/ae_frames/run-*/frames.json {frames: [{frame, scene,
      kind, file}]} (motion_render.py:151, 208), t_s = frame / motion-plan.json `fps` (motion_render.py:190), label
      "<scene> <kind>". A run folder or frame that resolves outside the item folder is left out. Only finite numbers
      reach the state (a non-finite fps or t_s drops the tile; the daemon's JSON refuses NaN / Infinity) and a tile
      whose tc is longer than TC_MAX (32) characters is dropped (never cut: a cut timecode names another time). The
      verdict is visual-verification.json's when its `sheet` is that run's _sheet.jpg and its `sheet_mtime` is not
      older than the sheet (verify.py:306-307, ppro_build.py:528, motion_qc.py:26-30), else "pending".
    Left out on purpose: `context` (project path, sequence name, ...), staleness of a done step other than the approval
    (cli.py stale_steps), media-pending slates among the frames, per-frame labels and thumbnails.

Cost (PanelFields)
    The panel polls a snapshot every 2 s. PanelFields caches the item's fields by the mtime / size / mode / links /
    inode / ctime of every file and folder they are read from (the evidence files, the run folders, the helpers'
    inputs and configs), the listing (entry names and kinds) of every folder whose entries are listed (the frame
    folders and their run-* folders: NTFS stamps a folder's mtime in clock ticks, so a frame written in the same tick
    as the folder's last change leaves the folder's stat as it was) and a sha256 of the small gate files (GATE_FILES,
    at most GATE_HASH_MAX each) and of the data/Music licence files and music.json the music choice reads (T4.6):
    an approval, verdict or licence or
    verdict rewritten in place with the same size and a kept mtime still changes the key. A result built while any
    read failed for a reason other than "not found" (a sharing violation, a permission flip, a share that dropped)
    is never cached. active.json itself is read on every call, so staleness and a changed item are seen at once. An
    unchanged item is never re-read or re-fingerprinted. Blocking (file reads, hashing): the daemon runs it on its own
    bounded worker with a timeout (serve/app.py App._item_fields), never on the event loop or the default executor.
    PanelFields.generation (G2 H3) moves only when the fields served change; the daemon's push on change compares it
    (with_generation hands the fields and their generation over together), so a cache hit costs no comparison.

The build stamp (C1.8 / C2.3)
    <plugin>/adobe/expected.json {product, build, sha} is written by release.py (the executor's part) with `build` =
    the shipped .ccx's build.json `build`: the build id YYYYMMDDTHHMMSSZ (premiere-uxp/scripts/build.mjs buildId),
    which is also the panel bundle's __WNC_BUILD__ (hello client.build). panel_update compares them
    (messages.compare_builds).
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import logging
import math
import os
import re
import stat
import threading
import time
from pathlib import Path, PurePath

from contract import validate
from lib import common

__all__ = ["ACTIVE_MAX", "EXPECTED_MAX", "EVIDENCE_MAX", "STALE_S", "SKEW_S", "QC_MAX", "TC_MAX", "STEP_IDS",
           "UNC_PROBE_S", "UNC_RETRY_S", "active_path", "expected_path", "read_active", "read_expected",
           "panel_update", "panel_fields", "editor_summary", "PanelFields"]

log = logging.getLogger(__name__)

ACTIVE_MAX = 64 * 1024
EXPECTED_MAX = 64 * 1024
EVIDENCE_MAX = 8 * 1024 * 1024        # also the cap for every file an engine helper reads
STALE_S = 12 * 3600
SKEW_S = 5 * 60                       # a writer's clock a little ahead is fine; a record from the future is not
QC_MAX = 500                          # session.schema.json panel_state.qc maxItems
SUMMARY_MAX = 20000                   # approval.summary maxLength
PATH_MAX = 4096                       # qc_frame.file / approval.preview_mp4 maxLength
TC_MAX = 32                           # qc_frame.tc maxLength
GATE_HASH_MAX = 64 * 1024             # the gate files' content hash covers at most this much of each
# The small files whose content decides a gate or a verdict: their hash is part of PanelFields' cache key
GATE_FILES = ("01_analysis/plan-approval.json", "08_quality_control/qc-results.json",
              "08_quality_control/visual-verification.json", "07_premiere/ppro-build-result.json",
              "04_after_effects/motion-build-result.json", "01_analysis/motion-validation.json")
UNC_PROBE_S = 1.0                     # a network client folder slower than this to answer is skipped ...
UNC_RETRY_S = 60.0                    # ... and not touched again for this long
STEP_IDS = ("transcript", "plan", "approve", "build", "frames", "qc", "handoff")    # pipeline_step.id, in order
EMPTY = {"client": "", "item": "", "pipeline": [], "approval": None, "qc": []}

_MISSING = object()                   # _check: nothing at that path
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOCTTY", 0)
_SLOW_ROOTS: dict[str, float] = {}    # raw UNC client_root -> time.monotonic() until which it is skipped
_SLOW_LOCK = threading.Lock()


def active_path(home) -> Path:
    return Path(home) / "state" / "active.json"


def expected_path() -> Path:
    return common.PLUGIN_DIR / "adobe" / "expected.json"


def _empty(**over) -> dict:
    out = {"client": "", "item": "", "pipeline": [], "approval": None, "qc": []}
    out.update(over)
    return out


# ------------------------------------------------------------------------------------------------ reading files
_FAILS = threading.local()            # .n: reads on this thread that failed for a reason other than "not found"


def _failed(e: BaseException | None = None) -> None:
    """Count a read that failed for a reason other than "not found" (an OSError such as a sharing violation, a
    permission flip or a share that dropped; None: any failure): PanelFields never caches a result built on one. A
    ValueError / RuntimeError (a bad path, a link loop) is a property of the files, not a transient failure."""
    if e is None or (isinstance(e, OSError) and not isinstance(e, (FileNotFoundError, NotADirectoryError))):
        _FAILS.n = getattr(_FAILS, "n", 0) + 1


def _regular(st: os.stat_result, cap: int | None, links: bool) -> bool:
    return stat.S_ISREG(st.st_mode) and (cap is None or st.st_size <= cap) and (not links or st.st_nlink <= 1)


def _check(path, base: Path | None, cap: int | None = None, *, links: bool = True):
    """_MISSING when nothing is at `path`; the resolved Path when it is a regular file inside `base` (None: anywhere),
    at most `cap` bytes (None: any size) and, with `links`, one link; else None (refused: a folder, FIFO, device,
    socket, too big, outside `base`, hard-linked, unreadable)."""
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return _MISSING
    except (OSError, ValueError) as e:
        _failed(e)
        return None
    try:
        r = Path(path).resolve(strict=True)
        if base is not None and not r.is_relative_to(base):
            return None
        st = os.stat(r)
    except (OSError, RuntimeError, ValueError) as e:
        _failed(e)
        return None
    return r if _regular(st, cap, links) else None


def _open_checked(r: Path, cap: int | None, links: bool, limit: int) -> bytes | None:
    """At most `limit` bytes of the checked file `r`: non-blocking open, fstat again on the handle; None otherwise."""
    try:
        fd = os.open(r, _OPEN_FLAGS)
    except (OSError, ValueError) as e:
        _failed(e)
        return None
    try:
        with open(fd, "rb") as f:
            if not _regular(os.fstat(f.fileno()), cap, links):   # swapped between the check and the open
                return None
            return f.read(limit)
    except OSError as e:
        _failed(e)
        return None


def _read_capped(path, cap: int, base: Path | None = None, *, links: bool = True) -> bytes | None:
    """The bytes of a file _check accepts, read through the resolved path it checked (non-blocking open, fstat again on
    the handle); None for anything else."""
    r = _check(path, base, cap, links=links)
    if not isinstance(r, Path):
        return None
    data = _open_checked(r, cap, links, cap + 1)
    return data if data is not None and len(data) <= cap else None


def _parse(data: bytes | None) -> dict | None:
    if data is None:
        return None
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (ValueError, RecursionError):
        return None
    return doc if isinstance(doc, dict) else None


def _json(path, cap: int = EVIDENCE_MAX, base: Path | None = None, *, links: bool = True) -> dict | None:
    """A JSON object from a UTF-8 file (a BOM is fine), or None."""
    return _parse(_read_capped(path, cap, base, links=links))


# ------------------------------------------------------------------------------------------------ build stamp
def read_expected(path=None) -> dict | None:
    """<plugin>/adobe/expected.json as {product, build, sha} (only `build` is needed), or None."""
    doc = _json(Path(path) if path else expected_path(), EXPECTED_MAX, links=False)
    if not doc or not isinstance(doc.get("build"), str) or not 0 < len(doc["build"]) <= 64:
        return None
    return doc


def panel_update(client_build, path=None) -> str:
    """welcome.update.panel for a hello's client.build: ok | stale | newer | unknown (no expected.json: unknown)."""
    from .messages import compare_builds
    exp = read_expected(path)
    return compare_builds(client_build, exp["build"]) if exp else "unknown"


# ------------------------------------------------------------------------------------------------ active.json
def _parse_at(s: str) -> _dt.datetime | None:
    try:
        at = _dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo is not None else None


def _is_unc(raw: str) -> bool:
    """A network path: \\\\server\\share\\... or //server/share/... (either separator)."""
    return len(raw) > 2 and raw[0] in "\\/" and raw[1] in "\\/"


def _probe_root(p: Path) -> Path:
    return p.resolve(strict=True)


def _client_root(raw: str) -> Path | None:
    if "\x00" in raw or any(part == ".." for part in PurePath(raw).parts):
        return None
    p = Path(raw)
    if not p.is_absolute():
        return None
    unc = _is_unc(raw)
    if unc:
        with _SLOW_LOCK:
            until = _SLOW_ROOTS.get(raw)
            if until is not None and time.monotonic() >= until:
                del _SLOW_ROOTS[raw]
                until = None
        if until is not None:
            return None                           # a slow share: left alone until UNC_RETRY_S has passed
    t0 = time.monotonic()
    try:
        r = _probe_root(p)
        ok = r.is_dir()
    except (OSError, RuntimeError, ValueError):
        r, ok = None, False
    if unc and time.monotonic() - t0 > UNC_PROBE_S:
        with _SLOW_LOCK:
            _SLOW_ROOTS[raw] = time.monotonic() + UNC_RETRY_S
        log.warning("reel serve: the network client folder took over %gs to answer; the panel skips it for %gs",
                    UNC_PROBE_S, UNC_RETRY_S)
        return None
    return r if ok else None


def _item(raw: str) -> str | None:
    try:
        common.check_project_id(raw)            # one plain folder name: no separator, drive colon, control char, '..'
    except Exception:
        return None
    return raw


def read_active(home, now: _dt.datetime | None = None) -> dict | None:
    """{client_root: Path, item, project: Path, record} of a usable active.json, else None."""
    rec = _json(active_path(home), ACTIVE_MAX, links=False)
    if rec is None or validate(rec, "engine_state"):
        return None
    at = _parse_at(rec["at"])
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if at is None or (now - at).total_seconds() > STALE_S or (at - now).total_seconds() > SKEW_S:
        return None
    item = _item(rec["item"])
    if item is None:
        return None
    root = _client_root(rec["client_root"])
    if root is None:
        return None
    projects = root / "output" / "projects"
    project = projects / item
    try:
        if project.exists() and not project.resolve().is_relative_to(projects.resolve()):
            return None                          # a link that leaves the client folder
    except (OSError, RuntimeError, ValueError):
        return None
    return {"client_root": root, "item": item, "project": project, "record": rec}


# ------------------------------------------------------------------------------------------------ editor summary
_HEADING = re.compile(r"^\s{0,3}(#{1,6})(?:\s+|$)")
_TABLE_RULE = re.compile(r"^[\s|:-]*-[\s|:-]*$")
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
# The engine's own footers, matched by structure (lib/plan.py:1041 write_edit_plan; lib/motion_plan.py:802-803
# write_motion_md): the "**To approve:** ..." paragraph and the motion plan's "Animatic: <path or note>" line.
_FOOTER = re.compile(r"^\s*\*\*To approve:\*\*")
_ANIMATIC = re.compile(r"^\s*Animatic:\s")
_CODE_SPAN = re.compile(r"(`+)(.*?)\1")                                   # a markdown code span on one line
_CODE_COMMAND = re.compile(r"(?:reel|claude|npm|npx|python[\d.]*|py)(?!\w)", re.I)
_REEL_AT = re.compile(r"(?<![\w-])reel[ \t]+(-{1,2}[A-Za-z][\w-]*(?:=\S*)?|[A-Za-z][\w-]*)(?![\w-])", re.I)
_CLAUDE_FLAG = re.compile(r"(?<![\w-])claude(?:[ \t]+-{1,2}[A-Za-z][\w-]*(?:=\S*)?)+(?![\w-])", re.I)
_FLAGS = re.compile(r"(?:[ \t]+-{1,2}[A-Za-z][\w-]*(?:=\S*)?)*")
_CLAUDE_CODE = re.compile(r"\bclaude[ \t]*code\b", re.I)
_EMPTY_PARENS = re.compile(r"\([ \t]*\)")
_SPACE_BEFORE = re.compile(r"[ \t]+([.,;:!?)])")
_SPACES = re.compile(r"(?<=\S)[ \t]{2,}")
# Used when the engine's command table (cli.registered_commands) cannot be loaded: the commands its footers name.
_FALLBACK_COMMANDS = frozenset({"approve-plan", "motion-animatic", "plan", "motion-plan", "ppro-build", "serve"})
_commands: frozenset | None = None


def _subcommands() -> frozenset:
    """The `reel` subcommand names (lowercase): the engine's command table, read once."""
    global _commands
    if _commands is None:
        try:
            import cli                                           # engine/reel/cli.py: imports lib.common only
            names = frozenset(str(n).lower() for n in cli.registered_commands())
        except Exception as e:                                   # noqa: BLE001 — the fallback covers the footers
            log.debug("engine state: no command table (%s)", type(e).__name__)
            names = frozenset()
        _commands = names | _FALLBACK_COMMANDS
    return _commands


def _code_span(m: re.Match) -> str:
    """A code span: nothing when it looks like a command (it has a space, or starts with reel / claude / npm / npx /
    python / py), else its one word as plain text."""
    body = m.group(2)
    if not body.strip() or any(c.isspace() for c in body) or _CODE_COMMAND.match(body):
        return ""
    return body


def _drop_reel_commands(s: str) -> str:
    """Remove each `reel <subcommand> [--flags]` and `reel --flag` token run; `reel` before any other word stays."""
    names = _subcommands()
    out, pos = [], 0
    while True:
        m = _REEL_AT.search(s, pos)
        if m is None:
            break
        tok = m.group(1)
        if tok.startswith("-") or tok.lower() in names:
            out.append(s[pos:m.start()])
            pos = _FLAGS.match(s, m.end()).end()
        else:                                                    # an ordinary "reel": look again from the next word
            out.append(s[pos:m.start(1)])
            pos = m.start(1)
    out.append(s[pos:])
    return "".join(out)


def _redact(line: str) -> str:
    """One line with its commands removed token by token (C1.4 / C2.2); every other word stays."""
    s = _CODE_SPAN.sub(_code_span, line).replace("`", "")
    s = _drop_reel_commands(s)
    s = _CLAUDE_FLAG.sub("", s)
    s = _CLAUDE_CODE.sub("Claude", s)
    if s == line:
        return line                                              # nothing removed: the line exactly as written
    s = _SPACES.sub(" ", _SPACE_BEFORE.sub(r"\1", _EMPTY_PARENS.sub("", s)))   # tidy where a token was taken out
    return s if line[:1].isspace() else s.lstrip()


def _plain(line: str) -> str:
    """One markdown line as plain text: no heading marks, bold, links; a table row as "a · b"."""
    line = _HEADING.sub("", line)
    line = _LINK.sub(r"\1", line).replace("**", "")
    s = line.strip()
    if s.startswith("|"):
        cells = [c.strip() for c in s.strip("|").split("|")]
        line = " · ".join(c for c in cells if c and c != "#")
    return line.rstrip()


def editor_summary(md: str) -> str:
    """The approval card's summary from edit-plan.md / motion-plan.md, for the editor (C1.4 / C2.2): the engine's
    footers removed by structure, commands removed token by token (every line and table row of the plan stays),
    markdown collapsed to plain text, at most SUMMARY_MAX characters."""
    out: list[str] = []
    in_footer = False                       # inside the "**To approve:**" paragraph: until a blank line or a heading
    for raw in md.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if in_footer:
            if raw.strip() and not _HEADING.match(raw):
                continue
            in_footer = False
        if _FOOTER.match(raw):
            in_footer = True
            continue
        if _ANIMATIC.match(raw) or (_TABLE_RULE.match(raw) and "|" in raw):
            continue
        out.append(_plain(_redact(raw)))
    lines: list[str] = []
    for line in out:
        if line.strip() or (lines and lines[-1].strip()):
            lines.append(line if line.strip() else "")
    text = "\n".join(lines).strip()
    return text if len(text) <= SUMMARY_MAX else text[:SUMMARY_MAX - 1] + "…"


# ------------------------------------------------------------------------------------------------ evidence
class _Item:
    """One item's folders and the checked reads of its files."""

    def __init__(self, paths: common.Paths):
        self.paths = paths
        self.root = paths.root                                       # resolved by Paths
        try:
            self.base = paths.project.resolve()
        except (OSError, RuntimeError, ValueError):
            self.base = paths.project
        try:
            self.plugin = common.PLUGIN_DIR.resolve()
        except (OSError, RuntimeError, ValueError):
            self.plugin = common.PLUGIN_DIR
        self._music_walk = None                                      # data/Music, walked once per item (T4.6)
        self._music_used = None                                      # ... and what the music choice reads of it

    def p(self, rel: str) -> Path:
        return self.paths.p(rel)

    def json(self, rel: str) -> dict | None:
        return _json(self.p(rel), EVIDENCE_MAX, self.base)

    def text(self, rel: str) -> str | None:
        data = _read_capped(self.p(rel), EVIDENCE_MAX, self.base)
        return None if data is None else data.decode("utf-8-sig", "replace")

    def is_file(self, rel_or_path) -> bool:
        path = self.p(rel_or_path) if isinstance(rel_or_path, str) else rel_or_path
        return isinstance(_check(path, self.base), Path)

    def inside(self, path: Path) -> bool:
        """A run folder or frame (listed, not read) that does not resolve outside the item folder."""
        try:
            return path.resolve().is_relative_to(self.base)
        except (OSError, RuntimeError, ValueError) as e:
            _failed(e)
            return False

    # -------------------------------------------------- what the engine helpers read (files, base, one link?)
    def _config_files(self, name: str) -> list | None:
        """The files Context.config(name) reads (lib/common.py:554-561): config/defaults/<name>, the client's
        reel-profile/profile.json for the profile id (active_profile, :532-542), profiles/<id>/<name> and the
        client's reel-profile/<name> (CLIENT_PROFILE_REL, :509). None when the profile id is not one plain name."""
        prof = self.root / common.CLIENT_PROFILE_REL
        files = [(common.CONFIG_DIR / name, self.plugin, False), (prof / "profile.json", self.root, True)]
        own = _json(prof / "profile.json", EVIDENCE_MAX, self.root) or {}
        pid = own.get("id")
        if pid:
            if not isinstance(pid, str) or _item(pid) is None:
                return None
            files.append((common.PROFILES_DIR / pid / name, self.plugin, False))
        files.append((prof / name, self.root, True))
        return files

    def _music(self) -> tuple[list, list, list]:
        """(folders, licence files, tracks) under the client's data/Music, walked once per item and never through a
        link (as lib/motion_audio.py _walk; nothing at all when data/ or data/Music is a link): the folders, the
        licence JSON files (<track>.licence.json / .license.json, licence.json / license.json) and music.json, and
        the tracks. Only regular files."""
        if self._music_walk is not None:
            return self._music_walk

        def link(q) -> bool:
            return os.path.islink(q) or getattr(os.path, "isjunction", lambda _p: False)(q)
        top = self.root / "data" / "Music"
        folders, lic, tracks = [top], [], []
        if link(self.root / "data") or link(top) or not top.is_dir():
            self._music_walk = (folders, lic, tracks)
            return self._music_walk
        folders = []
        try:
            for dirpath, dirnames, filenames in os.walk(top, followlinks=False):
                dirnames[:] = sorted(d for d in dirnames if not link(os.path.join(dirpath, d)))
                folders.append(Path(dirpath))
                for n in sorted(filenames):
                    q = os.path.join(dirpath, n)
                    if n.startswith(".") or link(q):
                        continue
                    try:
                        if not stat.S_ISREG(os.lstat(q).st_mode):
                            continue
                    except OSError:
                        continue
                    k = n.casefold()
                    if k.endswith((".licence.json", ".license.json")) or k in ("licence.json", "license.json",
                                                                              "music.json"):
                        lic.append(Path(q))
                    elif Path(n).suffix.lower() in common.AUDIO_EXT:
                        tracks.append(Path(q))
        except OSError as e:
            _failed(e)
        self._music_walk = (folders, lic, tracks)
        return self._music_walk

    def _music_read(self) -> tuple[list, list]:
        """(licence files, tracks) the motion plan's music choice reads (lib/motion_audio.py music_state): music off,
        or a recipe without a music mood -> none; a track picked by hand -> that track, its own licence files and its
        folder's licence; the auto pick -> every licence file, music.json and every track."""
        if self._music_used is None:
            self._music_used = self._music_choice_reads()
        return self._music_used

    def _music_choice_reads(self) -> tuple[list, list]:
        import unicodedata
        _folders, lic, tracks = self._music()
        script = self.json("01_analysis/motion-script.json")
        m = (script or {}).get("music", "__auto__")
        if m is False or (isinstance(m, dict) and m.get("off") is True):
            return [], []
        if isinstance(m, dict) and m.get("file"):
            from lib.motion_audio import given_rel  # the CLI fingerprint's own reading (absolute path, link, case)

            def key(x: str) -> str:
                return unicodedata.normalize("NFC", x.replace("\\", "/")).casefold()
            rel = given_rel(self.root, m["file"])
            if rel is None:
                return [], []
            want = key(rel)
            hit = [t for t in tracks if key(t.relative_to(self.root).as_posix()) == want]
            if not hit:
                return [], []
            t = hit[0]
            mine = {key(t.name) + x for x in (".licence.json", ".license.json")} | {"licence.json", "license.json"}
            return [f for f in lic if f.parent == t.parent and key(f.name) in mine], [t]
        rec = (self.json("00_inputs/source.json") or {}).get("recipe") or {}
        if not ((rec.get("music") or {}).get("mood") if isinstance(rec, dict) else None):
            return [], []
        return lic, tracks

    def _motion_inputs(self) -> list | None:
        """lib/motion_plan.py fingerprint: source.json (motion_config.source), the script, words, pauses, the client's
        brand tokens and motion.json (motion_config.motion_cfg). The data/Music files its music choice reads (T4.6)
        are watched (watched(), _music_read) but are not inputs here: the engine reads them itself with a cap (a
        licence at most 64 KB + 1 bytes, music.json 1 MB), lstat first, a regular file only, no link, one checked
        handle (lib/motion_audio.py _read_small), and hashes a track by size and head/tail only. An oversized or
        hard-linked licence is then just an invalid licence, never a reason to drop the approval card. BL-20: also the
        reel's 00_inputs/speakers.json and its episode's episode.json (the names shown, motion_plan.episode_sheet);
        BL-21: 02_transcription/captions-short.srt (the caption words shown, motion_plan.shown_cues); review 91b6b44
        P2-1: the compiled motion-plan.json and motion-validation.json (motion_plan.plan_edited hashes the plan)."""
        cfg = self._config_files("motion.json")
        if cfg is None:
            return None
        ep = self._episode_json()
        return [(self.p(rel), self.base, True) for rel in (
            "00_inputs/source.json", "01_analysis/motion-script.json", "02_transcription/words.json",
            "06_audio/dialogue/pauses.json", "00_inputs/speakers.json", "02_transcription/captions-short.srt",
            "01_analysis/motion-plan.json", "01_analysis/motion-validation.json")] + [
            (self.paths.client_db / "branding/brand-tokens.json", self.root, True)] + \
            ([(ep, self.root, True)] if ep else []) + cfg

    def _episode_json(self) -> Path | None:
        """BL-20: output/episodes/<EP>/00_inputs/episode.json of the item's source.json episode_id, whose sheet names
        the motion fingerprint reads; None without one or for an id the engine refuses (it then reads no episode:
        an id that is not text, motion_plan.episode_sheet, or not one plain name, check_project_id)."""
        eid = (self.json("00_inputs/source.json") or {}).get("episode_id")
        if not isinstance(eid, str):
            return None
        from lib.episode import EpisodePaths
        try:
            return EpisodePaths(self.root, eid).p("00_inputs/episode.json")
        except Exception:  # noqa: BLE001 — check_project_id refuses it (Guidance): the engine reads no episode either
            return None

    def _approval_inputs(self, motion: bool) -> list | None:
        """lib/plan.py approval_state (:945): plan-approval.json, then the motion fingerprint's inputs (a record with
        kind "motion") or timeline-spec.json (plan_fingerprint, :912). The motion inputs only for a motion item (or a
        record that says kind "motion": that is the branch approval_state takes); an edit item never depends on them."""
        rec = self.json("01_analysis/plan-approval.json") or {}
        files = [(self.p("01_analysis/plan-approval.json"), self.base, True)]
        if motion or rec.get("kind") == "motion":
            extra = self._motion_inputs()
            if extra is None:
                return None
            files += extra
        if rec.get("kind") != "motion":
            files.append((self.p("01_analysis/timeline-spec.json"), self.base, True))
        return files

    def inputs_ok(self, files: list | None) -> bool:
        return files is not None and all(_check(f, base, EVIDENCE_MAX, links=links) is not None
                                         for f, base, links in files)

    def watched(self) -> list[Path]:
        """Every file and folder panel_fields reads or lists for this item: PanelFields' cache key."""
        vid = self.paths.video_id
        out = [self.p(rel) for rel in (
            "00_inputs/source.json", "01_analysis/timeline-spec.json", "01_analysis/edit-plan.md",
            "01_analysis/plan-approval.json", "01_analysis/motion-plan.json", "01_analysis/motion-validation.json",
            "01_analysis/motion-plan.md", "01_analysis/motion-script.json", "02_transcription/transcript.json",
            "02_transcription/words.json", "06_audio/dialogue/pauses.json", "07_premiere/ppro-build-result.json",
            "04_after_effects/motion-build-result.json", "08_quality_control/visual-verification.json",
            "08_quality_control/qc-results.json", f"08_quality_control/preview/{vid}_preview.mp4",
            f"08_quality_control/animatic/{vid}_animatic.mp4", "09_handoff/README.md", "00_inputs/speakers.json",
            "02_transcription/captions-short.srt")]
        out.append(self.paths.client_db / "branding/brand-tokens.json")
        ep = self._episode_json()                     # BL-20: the episode sheet's names (motion fingerprint)
        if ep:
            out.append(ep)
        folders, lic, _all = self._music()            # T4.6: a licence or track added, edited or removed
        out += folders + lic + self._music_read()[1]  # tracks: only those the music choice reads
        for name in ("motion.json", "sequence-settings.json"):
            out += [f for f, _, _ in (self._config_files(name) or [])]
        for rel in ("08_quality_control/premiere_frames", "08_quality_control/ae_frames"):
            folder = self.p(rel)
            out.append(folder)
            try:
                runs = sorted(folder.glob("run-*"))
            except OSError as e:
                _failed(e)
                runs = []
            for run in runs:
                out += [run, run / "_sheet.jpg", run / "frames.json"]
        return out

    def listed(self) -> list[Path]:
        """Every folder whose entries panel_fields lists (the frame folders and their run-* folders) or the motion
        fingerprint reads (the data/Music folders, T4.6): PanelFields keys these by their listing (_listing), never
        by the folder's own mtime."""
        out = [f for f in self._music()[0] if f.is_dir()]
        for rel in ("08_quality_control/premiere_frames", "08_quality_control/ae_frames"):
            folder = self.p(rel)
            out.append(folder)
            try:
                out += sorted(folder.glob("run-*"))
            except OSError as e:
                _failed(e)
        return out


def _is_motion(it: _Item) -> bool:
    return (it.json("00_inputs/source.json") or {}).get("kind") == "motion_reel"


def _plan_fingerprint(it: _Item, motion: bool) -> str | None:
    """The fingerprint approve-plan would record now; None when there is no current, readable plan."""
    try:
        if motion:
            val = it.json("01_analysis/motion-validation.json") or {}
            if not val.get("ok") or not isinstance(val.get("fingerprint"), str):
                return None
            if not it.inputs_ok(it._motion_inputs()):
                return None
            from lib.motion_plan import fingerprint, plan_edited
            if plan_edited(it.paths):             # review 91b6b44 P2-1: a plan edited by hand gets no approval card
                return None
            return val["fingerprint"] if fingerprint(it.paths) == val["fingerprint"] else None
        if not isinstance(_check(it.p("01_analysis/timeline-spec.json"), it.base, EVIDENCE_MAX), Path):
            return None
        from lib.plan import plan_fingerprint
        return plan_fingerprint(it.paths)
    except Exception as e:                       # the engine's own readers: a broken file is "no plan", never a crash
        _failed(e)
        log.debug("engine state: no plan fingerprint (%s)", type(e).__name__)
        return None


def _approval_current(it: _Item, motion: bool) -> bool:
    try:
        if not it.inputs_ok(it._approval_inputs(motion)):
            return False
        from lib.plan import approval_state
        return approval_state(it.paths)["state"] == "current"
    except Exception as e:
        _failed(e)
        log.debug("engine state: approval unreadable (%s)", type(e).__name__)
        return False


def _seq_fps(it: _Item) -> float:
    """lib/common.py seq_fps over checked config files; the engine default SEQ_FPS when one is refused or odd."""
    if it.inputs_ok(it._config_files("sequence-settings.json")):
        try:
            fps = float(common.seq_fps())
            if math.isfinite(fps) and fps >= 1:
                return fps
        except Exception as e:
            _failed(e)
            log.debug("engine state: no sequence rate (%s)", type(e).__name__)
    return float(common.SEQ_FPS)


def _short_path(p: Path) -> str | None:
    s = str(p)
    return s if len(s) <= PATH_MAX else None


def _newest_run(it: _Item, folder: Path, need: str) -> Path | None:
    try:
        runs = sorted(d for d in folder.glob("run-*") if d.is_dir() and it.inside(d)
                      and (not need or isinstance(_check(d / need, it.base, EVIDENCE_MAX), Path)))
    except OSError as e:
        _failed(e)
        return None
    return runs[-1] if runs else None            # run-YYYYmmdd-HHMMSS: the name order is the time order


def _same_file(a, b: Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))
    except (TypeError, ValueError):
        return False


def _run_verdict(it: _Item, vv: dict | None, run: Path) -> str:
    sheet = run / "_sheet.jpg"
    if not vv or vv.get("verdict") not in ("pass", "fail") or not _same_file(vv.get("sheet"), sheet):
        return "pending"
    try:
        recorded = float(vv.get("sheet_mtime"))
        if not math.isfinite(recorded) or not it.is_file(sheet) or sheet.stat().st_mtime > recorded + 1:
            return "pending"                     # the sheet was rebuilt after the verdict (or is not a plain file)
    except (OSError, TypeError, ValueError, OverflowError) as e:
        _failed(e)
        return "pending"
    return vv["verdict"]


def _ms_of(name: str) -> int | None:
    return next((int(tok) for tok in Path(name).stem.split("_") if tok.isascii() and tok.isdigit()), None)


def _tile(t_s, tc: str, file: str, label: str, verdict: str) -> dict | None:
    """One qc_frame, or None when its time is not a finite number (the daemon's JSON refuses NaN / Infinity) or its
    timecode is longer than TC_MAX (a cut timecode would name another time: the tile is dropped instead)."""
    if not isinstance(t_s, (int, float)) or not math.isfinite(t_s) or len(tc) > TC_MAX:
        return None
    return {"t_s": t_s, "tc": tc, "file": file, "label": label, "verdict": verdict}


def _edit_tiles(it: _Item, vv: dict | None) -> list:
    run = _newest_run(it, it.p("08_quality_control/premiere_frames"), "")
    if run is None:
        return []
    verdict = _run_verdict(it, vv, run)
    fps = _seq_fps(it)
    frames = []
    try:
        pngs = sorted(f for f in run.glob("*.png") if not f.name.startswith("._"))
    except OSError as e:
        _failed(e)
        return []
    for f in pngs:
        ms = _ms_of(f.name)
        file = _short_path(f)
        if ms is None or file is None or _check(f, it.base) is None:
            continue
        try:
            t = ms / 1000
            tile = _tile(t, common.frame_to_tc(round(t * fps), fps), file, "", verdict)
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
        if tile is not None:
            frames.append(tile)
    frames.sort(key=lambda q: q["t_s"])
    return frames[:QC_MAX]


def _motion_tiles(it: _Item, vv: dict | None) -> list:
    run = _newest_run(it, it.p("08_quality_control/ae_frames"), "frames.json")
    plan = it.json("01_analysis/motion-plan.json") or {}
    fps = plan.get("fps")
    if run is None or isinstance(fps, bool) or not isinstance(fps, (int, float)):
        return []
    try:
        fps = float(fps)
    except OverflowError:
        return []
    if not math.isfinite(fps) or fps < 1:
        return []
    doc = _json(run / "frames.json", EVIDENCE_MAX, it.base) or {}
    verdict = _run_verdict(it, vv, run)
    out = []
    frames = doc.get("frames")
    for rec in frames if isinstance(frames, list) else []:
        if not isinstance(rec, dict):
            continue
        frame, name = rec.get("frame"), rec.get("file")
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0 or not isinstance(name, str) \
                or not name or Path(name).name != name or PurePath(name).name != name or name in (".", ".."):
            continue                              # a file name, never a path
        file = _short_path(run / name)
        if file is None or _check(run / name, it.base) is None:
            continue
        label = " ".join(str(rec.get(k)) for k in ("scene", "kind") if isinstance(rec.get(k), str))[:512]
        try:
            tile = _tile(round(frame / fps, 6), common.frame_to_tc(frame, fps), file, label, verdict)
        except (OverflowError, ValueError, ZeroDivisionError):
            continue
        if tile is not None:
            out.append(tile)
        if len(out) >= QC_MAX:
            break
    return out


def _evidence(it: _Item) -> dict:
    P = it.p
    motion = _is_motion(it)
    st = dict.fromkeys(STEP_IDS, "pending")
    approval = None
    if it.is_file("02_transcription/transcript.json"):
        st["transcript"] = "done"
    if motion:
        val = it.json("01_analysis/motion-validation.json")
        if it.is_file("01_analysis/motion-plan.json") and val is not None:
            st["plan"] = "done" if val.get("ok") is True else "failed" if val.get("ok") is False else "pending"
    elif it.is_file("01_analysis/timeline-spec.json"):
        st["plan"] = "done"
    if st["plan"] == "done":
        if _approval_current(it, motion):
            st["approve"] = "done"
        else:
            fp = _plan_fingerprint(it, motion)
            if fp:
                st["approve"] = "waiting"
                md = it.text("01_analysis/motion-plan.md" if motion else "01_analysis/edit-plan.md")
                pv = P(f"08_quality_control/animatic/{it.paths.video_id}_animatic.mp4" if motion
                       else f"08_quality_control/preview/{it.paths.video_id}_preview.mp4")
                approval = {"summary": editor_summary(md) if md else "",
                            "preview_mp4": _short_path(pv) if it.is_file(pv) else None,
                            "flagged": [], "fingerprint": fp[:256]}
    build = it.json("04_after_effects/motion-build-result.json" if motion
                    else "07_premiere/ppro-build-result.json") or {}
    status = build.get("status")
    if motion:
        st["build"] = "done" if status == "PROJECT_ASSEMBLED" else "pending"
    else:
        st["build"] = ("done" if status in ("PRPROJ_BUILT", "PRPROJ_BUILT_WITH_ISSUES") else
                       "failed" if status == "FAILED" else "pending")
    vv = it.json("08_quality_control/visual-verification.json")
    verdict = (vv or {}).get("verdict")
    st["frames"] = "done" if verdict == "pass" else "failed" if verdict == "fail" else "pending"
    ok = (it.json("08_quality_control/qc-results.json") or {}).get("ok")
    st["qc"] = "done" if ok is True else "failed" if ok is False else "pending"
    if it.is_file("09_handoff/README.md"):
        st["handoff"] = "done"
    try:
        qc = _motion_tiles(it, vv) if motion else _edit_tiles(it, vv)
    except Exception as e:
        _failed(e)
        log.debug("engine state: no QC tiles (%s)", type(e).__name__)
        qc = []
    return {"pipeline": [{"id": s, "state": st[s]} for s in STEP_IDS], "approval": approval, "qc": qc}


def _fields(act: dict, home) -> dict:
    root, item = act["client_root"], act["item"]
    out = _empty(client=root.name[:256] or str(root)[:256], item=item[:256])
    try:
        with common.use_context(common.Context(root=root, home=home)):
            out.update(_evidence(_Item(common.Paths(root, item))))
    except Exception as e:                        # never fail a snapshot over an evidence file
        _failed()                                 # ... and never cache one built this way
        log.warning("reel serve: engine state for %s unreadable (%s)", item, type(e).__name__)
        out["pipeline"] = [{"id": s, "state": "pending"} for s in STEP_IDS]
    return out


def panel_fields(home, now: _dt.datetime | None = None) -> dict:
    """{client, item, pipeline, approval, qc} for PanelState: the item active.json names, else the empty values.
    Blocking (file reads, hashing), uncached: the daemon calls a PanelFields (cached) on its own bounded worker."""
    act = read_active(home, now)
    return _empty() if act is None else _fields(act, home)


def _stat_key(p: Path):
    """What identifies a file's or folder's state without reading it: mtime, size, mode, links, inode (file index on
    Windows) and ctime (inode change; creation time on Windows). None when there is nothing to stat."""
    try:
        st = os.stat(p)
    except (OSError, ValueError) as e:
        _failed(e)
        return None
    return (st.st_mtime_ns, st.st_size, st.st_mode, st.st_nlink, st.st_ino, st.st_ctime_ns)


def _listing(folder: Path):
    """A folder's entries as sorted (name, link?, folder?, file?) — one directory read, no stat per entry (the kinds
    come with the listing on Windows, macOS and Linux). None when there is no folder. A folder's own mtime is not
    enough: NTFS stamps it from a clock that moves in ticks (about 1-16 ms), so a frame written in the same tick as the
    folder's last change leaves the folder's whole stat key as it was."""
    try:
        with os.scandir(folder) as entries:
            return tuple(sorted((e.name, e.is_symlink(), e.is_dir(follow_symlinks=False),
                                 e.is_file(follow_symlinks=False)) for e in entries))
    except (OSError, ValueError) as e:
        _failed(e)
        return None


def _gate_hash(path: Path, base: Path) -> str | None:
    """sha256 of the first GATE_HASH_MAX bytes of a gate file (checked like every read here; "-" when it is absent,
    None when it is refused or unreadable): a same-size rewrite that keeps the mtime still changes the key."""
    r = _check(path, base)
    if r is _MISSING:
        return "-"
    if not isinstance(r, Path):
        return None
    data = _open_checked(r, None, True, GATE_HASH_MAX)
    return None if data is None else hashlib.sha256(data).hexdigest()


class PanelFields:
    """panel_fields with a cache: the item's fields are computed again only when a file or folder they come from
    changed (_stat_key of every path in _Item.watched, the _listing of every folder in _Item.listed, plus a content
    hash of the small gate files in GATE_FILES and of the licence files the music choice reads (T4.6):
    an approval, verdict or licence rewritten in place with the same size and a kept mtime is still seen). active.json is read
    on every call. A result built while any read failed for a reason other than "not found" is never cached (the next
    call reads again). Thread-safe; every call returns its own copy.
    `generation` (G2 H3, the daemon's push on change) moves only when the fields served differ from the ones served
    before: a cache hit compares nothing, a new key whose fields came out the same (a touched file) does not move it."""

    def __init__(self):
        self._lock = threading.Lock()
        self._key = None
        self._val: dict | None = None
        self._served: dict | None = None          # the fields the last call returned (generation's reference)
        self._served_key = None                   # ... and their cache key (None: not served from a key)
        self.generation = 0

    def _served_now(self, val: dict, key) -> None:
        """Under the lock: the fields this call returns. Served from the same key as last time: nothing to compare;
        otherwise a change of the fields moves generation."""
        if key is not None and key == self._served_key:
            return
        if val != self._served:
            self._served = copy.deepcopy(val)
            self.generation += 1
        self._served_key = key

    def _signature(self, act: dict, home):
        try:
            with common.use_context(common.Context(root=act["client_root"], home=home)):
                it = _Item(common.Paths(act["client_root"], act["item"]))
                watched = it.watched()
                listed = tuple((str(f), _listing(f)) for f in it.listed())
                gates = tuple(_gate_hash(it.p(rel), it.base) for rel in GATE_FILES)
                # T4.6: the licence files and music.json the music choice reads, hashed like the gate files (a
                # same-size edit that keeps the mtime still changes the key)
                music = tuple((str(f), _gate_hash(f, it.root)) for f in it._music_read()[0])
            return (str(act["client_root"]), act["item"], tuple((str(p), _stat_key(p)) for p in watched), listed,
                    gates, music)
        except Exception as e:                    # no key: compute without the cache
            _failed(e)
            log.debug("engine state: no cache key (%s)", type(e).__name__)
            return None

    def __call__(self, home, now: _dt.datetime | None = None) -> dict:
        return self.with_generation(home, now)[0]

    def with_generation(self, home, now: _dt.datetime | None = None) -> tuple[dict, int]:
        """(the fields, the generation they belong to), taken together under the lock: a caller that compares
        generations (the daemon's push) never pairs one read's fields with another read's generation."""
        act = read_active(home, now)
        if act is None:
            val = _empty()
            with self._lock:
                self._served_now(val, None)
                return val, self.generation
        _FAILS.n = 0
        key = self._signature(act, home)
        if _FAILS.n:                              # a stat or hash failed: the key cannot be trusted
            key = None
        with self._lock:
            if key is not None and key == self._key and self._val is not None:
                self._served_now(self._val, key)  # a hit: unchanged unless something else was served meanwhile
                return copy.deepcopy(self._val), self.generation
        val = _fields(act, home)
        clean = not _FAILS.n
        with self._lock:
            if key is not None and clean:
                self._key, self._val = key, copy.deepcopy(val)
            else:                                 # never serve a result built over a failed read
                self._key, self._val = None, None
            self._served_now(val, key if clean else None)
            return val, self.generation
