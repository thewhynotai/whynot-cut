# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Take a client folder somewhere else (3.0 Phase 4 T4.5 part B): `reel client-move`, `reel client-clone`, the
rewrite-only "already moved" mode, and the check that refuses a copied client nobody migrated.

Owner rule (2026-10-18): the copy carries ONLY the client folder (no dev project, no engine home); every path stored in
its database is relative to the client root (lib/client_db.py), and bringing it back acts on that client folder only.

  * move(src, dest): the whole client, every file and folder with its modification time (`reel next` compares times,
    the reference-style fingerprint uses them), then a check (file list, sizes, the database by hash), then, under the
    new folder's writer lock, the database's paths made relative (client_db.migrate) and every other place under
    output/ that names the old folder pointed at the new one (rebase: JSON values, .md reports, interchange XMLs). The
    old folder is LEFT in place: the editor deletes it after checking the new one (and, while a project links media
    there or a kept file may still be opened by the old folder's path, after relinking it or running its step again:
    `old_folder` names them).
  * clone(src, dest): a new, independent client with the same brand database: output/client_database without media
    (no assets/ or data/ files, no derivatives, no asset manifest, no reference-analysis cache), empty assets/ and data/,
    a fresh `.whynot-client`. Never the lease, lock files or the client's settings file.
  * already_moved(root): the editor moved or copied the folder by hand: the same rewrite, in place.
  * unmigrated(root): the CLI's refusal for a copied client whose database or discovery still names files in the
    folder it was copied from (else preflight would read the ORIGINAL clip and a build would import it).

Links (junctions, symlinks) are recorded and never followed (COORDINATION rule 15): a link is recreated as a link, its
target moved along when it points inside the old folder, kept when it points outside; a client whose output/ or
database is itself a link is refused (the copy would share it). Every run is a dry run unless `apply`. A failed copy is
removed again: only the names this run made, links unlinked as names. An interrupted one leaves
`.whynot-move-incomplete`; the next run removes its own partial copy only when everything in it came from the client.
Pipeline logs (history) and Premiere/After Effects projects (binary) are listed with their fix, never rewritten.

The files an approval or sign-off hashes byte for byte (the timeline spec, the words, the motion script, the pauses, the
reels plan, the brand tokens) are pointed at the new folder too, so no plan or transcript reads the old folder's media.
That voids those approvals ON PURPOSE (executor ruling 2026-10-19 on BL-14 Q1, option (c)): each one is listed by item
and kind in the result (`approvals_to_redo`) and, through VOIDED_REL, on NEEDS-YOU until the editor gives it again.
Nothing here approves anything again. A clone leaves the source's approvals untouched and starts with none.
Known limits: a reel cut from an episode is told to confirm its own transcript again (its check came from the
episode's); the editor's reels picks are not listed on their own (the reels-plan line says to pick again); a run killed
between rewriting an item's words and pinning its old-form transcript check (no hash) leaves that check counting for
the new words in the engine, while NEEDS-YOU lists it.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import zlib
from pathlib import Path

from . import client_db, linksafe
from .client_move_paths import FOLD_CASE, inside, other_client, real
from .errors import Guidance

INCOMPLETE = ".whynot-move-incomplete"
IS_WIN = sys.platform == "win32"
SPARE = 64 * 1024 * 1024
CLONE_SKIP = ("output/client_database/assets", "output/client_database/asset-manifest.json",
              "output/client_database/reference_analysis")
PROJECT_EXT = {".prproj": "premiere", ".aep": "after_effects", ".aepx": "after_effects"}
TEXT_EXT = {".md", ".xml", ".txt", ".csv", ".srt", ".vtt", ".html", ".jsx", ".tsv"}
LOG_EXT = {".log"}
TEXT_MAX = 64 * 1024 * 1024
INVENTORY = "output/discovery/input-inventory.json"
# JSON files an approval or sign-off hashes byte for byte (plan.plan_fingerprint, transcribe.words_fingerprint and the
# transcript check, cut_proposals, motion_plan.fingerprint, reels.reels_plan_fingerprint): rewritten like the others,
# and the approvals they carry are listed as voided (APPROVALS)
SIGNED = ("01_analysis/timeline-spec.json", "01_analysis/motion-script.json", "01_analysis/reels-plan.json",
          "02_transcription/words.json", "06_audio/dialogue/pauses.json", "branding/brand-tokens.json")
# the JSON files known to carry media paths with nothing bound to their bytes (the release track's REL-PREVIEW list,
# without the signed ones): a move points them at the new folder. Per clip / episode: the part after its folder.
REBASE_JSON = {INVENTORY, "01_analysis/edit-decisions.json", "00_inputs/input-manifest.json", "00_inputs/preflight.json", "00_inputs/source.json",
               "02_transcription/transcript.json", "03_broll/captions/captions-manifest.json",
               "06_audio/sfx/sfx-library.json", "07_premiere/base-manifest.json", "07_premiere/ppro-build-result.json",
               "07_premiere/timeline-manifest.json", "08_quality_control/preview/preview-result.json",
               "08_quality_control/project-status.json", "08_quality_control/qc-results.json",
               "08_quality_control/visual-verification.json", "01_analysis/reference_analysis/reference-measurements.json",
               # opened later by the absolute path they store (review 7fcbc1d P3-2): `reel verify --record` stats the
               # sheet, motion-render / motion-qc probe `main`; no fingerprint, check or sign-off hashes their bytes
               "08_quality_control/verify/verify-build.json", "04_after_effects/motion-render-result.json",
               "01_analysis/motion-plan.json",
               # Claude's map of SFX kinds to the client's sound files (review 087e8e3 P3-1): `reel sfx` opens the
               # paths; the plan reads only its keys, and no fingerprint or sign-off hashes it
               "06_audio/sfx-map.json",
               # audio-clean's report (the footage and the cleaned wav: qc reads only its metrics) and its cut check
               # (review b690c54 P2-1): rewritten, so the advice never asks for `reel audio-clean` again, which would
               # rewrite the signed pauses.json (motion approvals stale) with the default pause settings
               "06_audio/dialogue/dialogue-clean-report.json", "06_audio/dialogue/cut-verification.json"}
# the step that really writes a kept file again (review 087e8e3 P3-1), named in the delete advice while that file may
# still be opened by the old folder's path: by the item's kind (its flag), then the part after the item's folder, an
# exact file or a folder ending in "/" (`reel sfx` writes <kind>.provenance.json). A kept file not here has no step
# that safely writes it again (Claude's or the editor's own; 02_transcription/chunks/: `reel transcribe` skips while a
# transcript exists and --force throws the corrections away; `reel ppro-frames` writes only images; `reel audio-clean`
# never: see REBASE_JSON): the old folder is kept for it
STEP_OF = {"projects": ("--video-id", {"06_audio/sfx/": "reel sfx"}),
           "episodes": ("--episode", {"00_inputs/episode.json": "reel episode-prep"})}
# an After Effects frames run's record (motion_render.frames): its `render` path is never opened (the panel and the
# frame checks read its frame names), and `reel motion-frames` again would turn a recorded visual pass into pending
# (review 291b5d1 P3-1): kept like a log, never in the delete advice
AE_FRAMES_RECORD = re.compile(r"output/projects/[^/]+/08_quality_control/ae_frames/run-[^/]+/frames\.json")
# inside the client database only these (besides client_db.migrate's own files) are rewritten: everything else there is
# bound to its bytes (the reference style every video's copy is checked against, the sealed rules registry) or written
# by the editor or Claude, and none of it is opened as media
DB_REBASE = ("output/client_database/client-database-status.json",)
RELINK = {"premiere": "File > Link Media", "after_effects": "File > Dependencies > Find Missing Footage"}  # per app
BRAND_TOKENS = "output/client_database/branding/brand-tokens.json"   # signed (motion plans): rewritten, kept absolute
# (its readers open it directly, not through client_db.load)
# the approvals and sign-offs a move voids on purpose: kind -> (its own file in the item's folder, the NEEDS-YOU line in
# English and Arabic ({item}), what the editor does again: English, Arabic). Editor's words: no commands (HOW has those,
# for the move's result). Only the plan and the transcript are the editor's own approvals; the others say what the
# editor does once the step ran again.
APPROVALS = {
    "plan": ("01_analysis/plan-approval.json", "client moved: approve the plan again for {item}",
             "اتنقل العميل: وافق تاني على الخطة لـ {item}",
             "look at the plan again and approve it", "بص على الخطة تاني ووافق عليها"),
    "transcript": ("02_transcription/verification.json", "client moved: approve the transcript again for {item}",
                   "اتنقل العميل: وافق تاني على التفريغ لـ {item}",
                   "listen to the transcript again and confirm it", "اسمع التفريغ تاني وأكّده"),
    "cut-proposals": ("01_analysis/cut-proposals.json", "client moved: choose the cuts again for {item}",
                      "اتنقل العميل: اختار القص تاني لـ {item}",
                      "choose the cuts again from a new list of proposals", "اختار القص تاني من قائمة اقتراحات جديدة"),
    "review": ("review-flags.json", "client moved: the content review is needed again for {item}",
               "اتنقل العميل: مراجعة المحتوى لازم تتعمل تاني لـ {item}",
               "the content review is done again before anything on screen is approved",
               "مراجعة المحتوى بتتعمل تاني قبل الموافقة على أي كلام على الشاشة"),
    "reels-plan": ("01_analysis/reels-plan-validated.json", "client moved: pick the reels again for {item}",
                   "اتنقل العميل: اختار الريلز تاني لـ {item}",
                   "the reels plan is checked again, then you pick the reels again",
                   "خطة الريلز بتتراجع تاني، وبعدين تختار الريلز تاني"),
}
HOW = {"plan": "`reel approve-plan --by editor` after the editor looked at the plan",
       "plan-motion": "`reel motion-plan` again, then `reel approve-plan --by editor` after the editor looked at it",
       "transcript": "`reel transcript-verify --by editor` after the editor listened",
       "cut-proposals": "`reel cut-proposals` again, then the editor chooses",
       "review": "`reel review-flags` again with the reviewer's new table",
       "reels-plan": "`reel reels-plan --episode {item}` again, then the editor picks"}
# which of the item's files each approval hashes: an approval that can't be checked (None) is listed only when one of
# them was rewritten; one that held and no longer holds always is (the dry run's forecast uses the same rule)
TIMELINE_BOUND = ("01_analysis/timeline-spec.json",)
MOTION_BOUND = ("01_analysis/motion-script.json", "02_transcription/words.json", "06_audio/dialogue/pauses.json")
BOUND = {"transcript": ("02_transcription/words.json",), "cut-proposals": ("02_transcription/words.json",),
         "reels-plan": ("01_analysis/reels-plan.json", "02_transcription/words.json")}
PENDING_REL = "output/.whynot-move-pending.json"  # an "already moved" run that did not end cleanly: its old folder
VOIDED_REL = "output/client-move-approvals.json"    # the voided approvals NEEDS-YOU lists until each holds again
URL = re.compile(r"file://[^\s<>\"'`()\[\]{}]+")    # pathurl %-encodes brackets: one here ends the URL (a .md link)
TIME_SLACK_NS = 2_000_000_000                       # FAT keeps file times to 2 s, exFAT to 10 ms, NTFS to 100 ns
_END = r"(?=[\\/\"'`<>)\],;|\t\r\n]|$)"           # a root ends at a separator, a quote or the end, never mid-name
_START = r"(?:(?<![\w./\\-])|(?<=\\[nrt])|(?<=\\\\\?\\))"   # ...and starts there too (/Users/ed/A is no part of
                                                   # /Volumes/B/Users/ed/A), also after an escaped \n or a \\?\ prefix


def _x(p) -> str:
    r"""The form the OS opens even past 260 characters (Windows: \\?\ prefix); unchanged elsewhere."""
    s = os.path.abspath(str(p))
    if not IS_WIN or s.startswith("\\\\?\\") or len(s) < 240:
        return s
    return "\\\\?\\UNC\\" + s[2:] if s.startswith("\\\\") else "\\\\?\\" + s


def _refusal(what: str, how: str, **kw) -> dict:
    return {"refused": what, "how": how, **kw}


def _excluded(rel: str, mode: str) -> bool:
    """A name this copy never carries (POSIX `rel` from the client root)."""
    low = rel.casefold() if FOLD_CASE else rel
    if low in (INCOMPLETE, "output/.whynot-lock") or (low.startswith("output/") and low.endswith(".lock")):
        return True
    if mode != "clone":
        return False
    if low == "output" or low == "output/client_database":
        return False
    if not low.startswith("output/client_database/"):
        return True                                   # media, projects, logs, discovery, the marker, the settings
    return any(low == s or low.startswith(s + "/") for s in CLONE_SKIP)


def _link_info(p: str, st) -> dict:
    target = os.readlink(_x(p))
    target = client_db._plain("\\\\?\\" + target[4:] if target.startswith("\\??\\") else target)
    junction = IS_WIN and getattr(st, "st_reparse_tag", 0) == stat.IO_REPARSE_TAG_MOUNT_POINT
    is_dir = bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_DIRECTORY) if IS_WIN else \
        os.path.isdir(p)
    return {"target": target, "kind": "junction" if junction else "symlink", "is_dir": is_dir}


def scan(src: Path, mode: str = "move") -> dict:
    """Every entry of the client, never following a link: {"dirs", "files": [(rel, size, mtime_ns)], "links":
    [{rel, target, kind, is_dir}], "excluded", "other"}."""
    out = {"dirs": [], "files": [], "links": [], "excluded": [], "other": []}

    def walk(d: str, rel: str):
        with os.scandir(_x(d)) as it:
            names = sorted(e.name for e in it)
        for name in names:
            p, r = os.path.join(d, name), f"{rel}/{name}" if rel else name
            st = os.lstat(_x(p))
            if _excluded(r, mode):
                out["excluded"].append(r)
                continue
            if linksafe._st_is_link(st):
                out["links"].append({"rel": r, **_link_info(p, st)})
            elif stat.S_ISDIR(st.st_mode):
                out["dirs"].append(r)
                walk(p, r)
            elif stat.S_ISREG(st.st_mode):
                out["files"].append((r, st.st_size, st.st_mtime_ns))
            else:
                out["other"].append(r)
    walk(str(src), "")
    return out


def _is_root(v: str, base) -> bool:
    a, b = client_db._parts(v), client_db._parts(str(base))
    return (a == b) if not FOLD_CASE else [x.casefold() for x in a] == [x.casefold() for x in b]


def _new_target(lk: dict, src: Path, dest: Path) -> str:
    """Where a recreated link points: inside the old folder (or the folder itself) -> the same place in the new one;
    elsewhere -> unchanged. A relative target that climbs out of the client becomes absolute (from the new place it
    would point somewhere else)."""
    t = lk["target"]
    if not os.path.isabs(t):
        landed = os.path.normpath(os.path.join(str(src), os.path.dirname(lk["rel"]), t))
        if client_db.rel_under(landed, str(src)) is not None or _is_root(landed, src):
            return t
        return landed
    if _is_root(t, src):
        return str(dest)
    tail = client_db.rel_under(t, str(src))
    if tail is not None:
        return str(dest.joinpath(*tail.split("/")))
    return t


def _make_link(lk: dict, at: str, target: str):
    if lk["kind"] == "junction":
        import _winapi                                   # CPython stdlib on Windows: a junction needs no privilege
        _winapi.CreateJunction(target, _x(at))
    else:
        os.symlink(target, _x(at), target_is_directory=lk["is_dir"])


def _free(dest: Path) -> int:
    p = dest
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(str(p)).free


def _sha1(p: str) -> str:
    h = hashlib.sha1()
    with open(_x(p), "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _incomplete_of(dest: Path) -> dict | None:
    try:
        doc = json.loads((dest / INCOMPLETE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _empty(d: Path) -> bool:
    with os.scandir(_x(d)) as it:
        return next(it, None) is None


def _same(a, b) -> bool:
    return inside(real(a), real(b)) and inside(real(b), real(a))


def _linked_database(src: Path) -> dict | None:
    """output/ or the client database (or anything in it) is a link: a copy would share it with the old folder, and the
    engine never writes through a link."""
    db = src / "output" / "client_database"
    for p in (src / "output", db):
        if linksafe.is_link(p):
            return _refusal(f"{p} is a link (junction or symlink): the copy would share it with this client, and the "
                            "engine never writes through a link (nothing was written)",
                            "Make it a plain folder again (move its contents back, then remove only the link), then run "
                            "it again.")
    found = [lk["rel"] for lk in scan(db, "scan")["links"]] if db.is_dir() else []
    if found:
        return _refusal(f"the client database holds links ({', '.join(found[:5])}): its files are rewritten for the new "
                        "place, never through a link (nothing was written)",
                        "Replace each link by the files it points to (or remove only the link), then run it again.")
    return None


def _prefix_of(part: str, whole: str) -> bool:
    """Are the bytes of `part` the start of `whole` (a copy that stopped while writing it)?"""
    try:
        with open(_x(part), "rb") as a, open(_x(whole), "rb") as b:
            for chunk in iter(lambda: a.read(1 << 20), b""):
                if b.read(len(chunk)) != chunk:
                    return False
    except OSError:
        return False
    return True


def _only_ours(src: Path, dest: Path, src_files: dict) -> bool:
    """Is everything in an interrupted copy the client's own copy (so removing it loses nothing of the editor's)? Every
    file must be one of the client's with its modification time (to what the drive keeps, TIME_SLACK_NS) and size (a
    copy keeps both; under output/ the rewrite for the new place keeps the time only), except at most one: the file the
    copy stopped in, whose bytes are the start of the client's file. Anything else means someone put or changed
    something there: refused."""
    stopped_in = 0
    for rel, size, mns in scan(dest, "verify")["files"]:
        if rel not in src_files:
            return False
        s_size, s_mns = src_files[rel]
        if abs(mns - s_mns) < TIME_SLACK_NS and (size == s_size or rel.startswith("output/")):
            continue
        stopped_in += 1
        if stopped_in > 1 or not _prefix_of(str(dest.joinpath(*rel.split("/"))), str(src.joinpath(*rel.split("/")))):
            return False
    return True


def check(src, dest, mode: str = "move") -> dict:
    """The refusals before anything is written: {"refused", "how"} or {"ok": True, "partial": bool}."""
    src, dest = Path(os.path.abspath(Path(src).expanduser())), Path(os.path.abspath(Path(dest).expanduser()))
    pick = "Pick a new, empty folder outside every client folder (e.g. next to this client), then run it again."
    if not ((src / "assets").is_dir() and (src / "data").is_dir()):
        return _refusal(f"{src} is not a client folder (it needs assets/ and data/); nothing was written",
                        "Pass --root the client folder itself.")
    linked = _linked_database(src)
    if linked:
        return linked
    if not dest.parent.is_dir():
        return _refusal(f"the folder that should hold the copy doesn't exist: {dest.parent} (nothing was written)",
                        "Create it first, or check the path you typed.")
    if linksafe.is_link(dest):
        return _refusal(f"{dest} is a link (junction or symlink); the engine never writes through a link", pick)
    rs, rd = real(src), real(dest)
    if inside(rd, rs) or inside(rs, rd):
        return _refusal(f"{dest} and the client folder {src} contain each other (or are the same folder, maybe "
                        "through a link); nothing was written", pick)
    partial = False
    if os.path.lexists(dest):
        if not dest.is_dir():
            return _refusal(f"{dest} exists and is not a folder; nothing was written", pick)
        if not _empty(dest):
            mark = _incomplete_of(dest)
            ours = mark and mark.get("mode") == mode and isinstance(mark.get("from"), str) and mark["from"] and \
                type(mark.get("started_ns")) is int and _same(mark["from"], src)
            if not ours:
                return _refusal(f"{dest} exists and is not empty; nothing was written", pick)
            if not _only_ours(src, dest, {r: (s, m) for r, s, m in scan(src, mode)["files"]}):
                return _refusal(f"{dest} exists and is not empty: an interrupted copy of this client that changed after "
                                "it stopped, or holds files that are not the client's (nothing was written)",
                                "Check what is in it: if nothing there is yours, delete that folder yourself (a link in "
                                "it: remove only the link, never what it points to), then run it again. Or " +
                                pick[0].lower() + pick[1:])
            partial = True                               # our own copy, interrupted: it is removed and made again
    other = other_client(real(dest.parent) if partial else rd, src)    # a partial copy looks like a client itself
    if other:
        return _refusal(f"{dest} is inside another client's folder ({other}); nothing was written", pick)
    return {"ok": True, "partial": partial}


# --------------------------------------------------------------------------- what still names the old folder
def _forms(o: str, n: str, text: bool) -> list[tuple[str, str]]:
    """Each way a file spells a root, with the new root in the same spelling: as is, with forward slashes, escaped (JSON
    text, or a Python list's repr inside a message), and in text files also XML-escaped. A file URL is not spelled
    here: each one is read back to a path and written again for the new place (_rebase_text)."""
    from html import escape
    forms = [(o, n), (o.replace("\\", "/"), n.replace("\\", "/"))]
    forms += [(json.dumps(a, ensure_ascii=e)[1:-1], json.dumps(b, ensure_ascii=e)[1:-1])
              for a, b in list(forms) for e in (True, False)]
    if text:
        forms += [(escape(a, quote=False), escape(b, quote=False)) for a, b in list(forms)]
    out, seen = [], set()
    for a, b in forms:
        if a and a not in seen:
            seen.add(a)
            out.append((a, b))
    return out


def _pairs(olds, new: Path | None, text: bool, relative: bool = False) -> list:
    """(compiled old-root pattern, its replacement) for every spelling (`_forms`). `relative`: inside the client
    database, where paths are stored relative to the client root, the root and the separator after it are dropped."""
    out = []
    flags = re.IGNORECASE if FOLD_CASE else 0
    for o in olds:
        o = client_db._plain(str(o)).rstrip("\\/")
        for a, b in _forms(o, str(new) if new is not None else "", text):
            if relative:
                out.append((re.compile(_START + re.escape(a) + r"(?:\\\\|\\|/)", flags), ""))
            else:
                out.append((re.compile(_START + re.escape(a) + _END, flags), b))
    return out


def _sub(s: str, pairs) -> tuple[str, int]:
    n = 0
    for pat, rep in pairs:
        s, k = pat.subn(lambda _m, rep=rep: rep, s)
        n += k
    return s, n


def _head(p: str) -> str:
    """The drive or the server of a path (its first part), case folded."""
    parts = client_db._parts(p)
    return parts[0].casefold() if parts else ""


def _url_heads(olds) -> dict:
    """Each old root: ({its drive or server as written and as its real path}, its real path or None). A mapped drive
    Z: is \\\\nas\\work, and the build's pathurl writes the real one; the real path is looked up once per rebase."""
    out = {}
    for o in olds:
        ro = real(o) if client_db.native_abs(o) else None
        out[o] = ({_head(o), _head(ro) if ro else _head(o)}, ro)
    return out


def _rebased_url(url: str, olds, new: Path, heads: dict) -> str | None:
    """A file URL under an old root (or the root itself) written again by the build's own pathurl for the same place
    in `new`, its ?query / #fragment kept as they were; None = not under an old root."""
    from html import unescape
    from .premiere_xml import path_from_url, pathurl
    cut = min((i for i in (url.find("?"), url.find("#")) if i >= 0), default=len(url))
    path = str(path_from_url(unescape(url[:cut])))
    share = path[:2] in ("\\\\", "//")
    for o in olds:
        hs, ro = heads[o]
        if share and _head(path) not in hs:
            continue                                     # a share on another server: never looked up (an offline
        tail = "" if _is_root(path, o) else client_db.rel_under(path, o, ro)    # server stalls a lookup ~40 s)
        if tail is not None:
            return pathurl(new.joinpath(*[x for x in tail.split("/") if x])) + url[cut:]
    return None


def _rebase_text(text: str, olds, new: Path, pairs, heads: dict) -> tuple[str, int]:
    """Text pointed at `new`: each file URL (an interchange XML's pathurl, a link in a report) read back to a path and,
    when it is under an old root, written again by the build's own pathurl (a NAS share as file://server/share/..., a
    drive as file://localhost/C:/...); the rest by spelling (_pairs). Punctuation after a URL is not part of it.
    `heads`: _url_heads(olds), filled on the first URL and kept for the whole rebase."""
    out, n, at = [], 0, 0
    for m in URL.finditer(text):
        seg, k = _sub(text[at:m.start()], pairs)
        out.append(seg)
        n += k
        url = m.group(0).rstrip(".,;:!?")
        if not heads:
            heads.update(_url_heads(olds))
        moved = _rebased_url(url, olds, new, heads)
        out.append(moved if moved is not None else url)
        n += moved is not None
        at = m.start() + len(url)
    seg, k = _sub(text[at:], pairs)
    return "".join(out) + seg, n + k


def _rebased_value(s: str, olds, new: Path, relative: bool):
    """A whole value that IS a path under an old root: rebuilt for this computer from its tail (a Windows value moved
    to a Mac gets "/" separators, never a file name with backslashes in it); root-relative POSIX inside the database."""
    for o in olds:
        tail = client_db.rel_under(s, o) if not client_db.is_relative(s) else None
        if tail:
            return tail if relative else str(new.joinpath(*tail.split("/")))
    return None


def _rebase_doc(node, ctx: tuple, count: list):
    olds, new, pairs, relative, heads = ctx
    if isinstance(node, str):
        whole = _rebased_value(node, olds, new, relative)
        if whole is not None:
            count[0] += 1
            return whole
        s, k = _sub(node, pairs) if relative else _rebase_text(node, olds, new, pairs, heads)
        count[0] += k
        return s
    if isinstance(node, list):
        return [_rebase_doc(x, ctx, count) for x in node]
    if isinstance(node, dict):
        return {(_rebase_doc(k, ctx, count) if isinstance(k, str) else k): _rebase_doc(v, ctx, count)
                for k, v in node.items()}
    return node


def _names(path: str, needles: list, opener) -> bool | None:
    """Does the file hold one of the old roots (bytes, case folded where the OS folds)? None = couldn't read it."""
    keep = max((len(n) for n in needles), default=0)
    tail = b""
    try:
        with opener(_x(path)) as f:
            for chunk in iter(lambda: f.read(1 << 22), b""):
                buf = tail + chunk
                hay = buf.lower() if FOLD_CASE else buf
                if any(n in hay for n in needles):
                    return True
                tail = buf[-keep:]
    except (OSError, EOFError, gzip.BadGzipFile, zlib.error):
        return None
    return False


def _needles(olds) -> list:
    out = set()
    for o in olds:
        o = client_db._plain(str(o)).rstrip("\\/")
        for form in {o, o.replace("\\", "/"), o.replace("/", "\\"), json.dumps(o)[1:-1],
                     json.dumps(o, ensure_ascii=False)[1:-1]}:
            for sep in ("\\", "/"):
                for enc in ("utf-8", "utf-16-le", "utf-16-be"):
                    b = (form + sep).encode(enc)
                    out.add(b.lower() if FOLD_CASE else b)
    return sorted(out)


def _project_fix(rel: str, ext: str) -> str:
    parts = rel.split("/")
    vid = parts[2] if len(parts) > 3 and parts[:2] == ["output", "projects"] else None
    if ext == ".prproj":
        return ("Premiere: open it from the new place and use File > Link Media to point it at the new folder, or "
                f"rebuild it: `reel ppro-build --force{' --video-id ' + vid if vid else ''}`")
    return ("After Effects: open it from the new place and use File > Dependencies > Find Missing Footage, or "
            f"rebuild it: `reel ae-build --force{' --video-id ' + vid if vid else ''}`")


def _rewritable(rel: str, ext: str) -> str | None:
    """Why a file under output/ may NOT be rewritten (None = it may): in the client database, anything but DB_REBASE
    and the brand tokens (bound to its bytes, or the editor's or Claude's own writing); a JSON file not on the list of
    files known to carry media paths and nothing else that is bound to them (REBASE_JSON). Other text (reports,
    interchange XML) may be rewritten."""
    tail = rel.split("/", 3)[-1] if rel.startswith(("output/projects/", "output/episodes/")) else rel
    if ext == ".json" and tail in SIGNED:
        return None                    # an approval it carries is voided on purpose and listed (APPROVALS)
    if rel.startswith("output/client_database/"):
        if rel in DB_REBASE or rel == BRAND_TOKENS:
            return None
        if rel.startswith("output/client_database/reference_style/"):
            return ("every video's copy of the client reference style is checked against this folder's exact bytes "
                    "(`reel ref-style`): kept, so no video's style turns outdated. A path in it is a citation, never "
                    "opened")
        if rel == "output/client_database/reel-profile/rules.json":
            return ("sealed by `reel rules` (a rewrite would make the rules file refused as edited by hand): kept. A "
                    "path in a rule's text is never opened")
        return ("written by the editor or Claude (profile, notes, analysis): kept as written. A path in it is text, "
                "never opened")
    if ext != ".json" or tail in REBASE_JSON:
        return None
    return "not on the list of files a move may rewrite: it names the old folder until its step runs again"


def plausible_old(root, old, pointed: bool = True) -> str | None:
    """Why `old` can't be the folder this client was moved from (None = it can): a drive or file-system root, the home
    folder, the client itself or a folder above it, or (`pointed`) a folder no path of the database or inventory points
    into. The old folder of an "already moved" run that did not end cleanly (PENDING_REL) needs no pointing path: that
    run may have rewritten them all."""
    root = Path(root)
    parts = client_db._parts(str(old))
    home = client_db._parts(str(Path.home()))
    if len(parts) < 2 or _is_root(str(old), str(Path.home())) or len(parts) <= len(home) and \
            [x.casefold() for x in parts] == [x.casefold() for x in home[:len(parts)]]:
        return f"{old} is a drive, the top of the disk or your home folder, not a client folder"
    if _is_root(str(old), root) or client_db.rel_under(str(root), str(old)) is not None:
        return f"{old} is this client folder or a folder above it"
    if client_db.rel_under(str(old), str(root)) is not None:
        return f"{old} is a folder inside this client"
    pending = _pending(root) if pointed else None
    if not pointed or pending and _is_root(str(old), pending):
        return None
    seen = [0]

    def note(v):
        tail = client_db.rel_under(v, str(old)) if isinstance(v, str) and v and not client_db.is_relative(v) else None
        if tail and root.joinpath(*tail.split("/")).exists():
            seen[0] += 1
        return v
    _walk_known_paths(root, note)
    return None if seen[0] else f"nothing in this client's database or discovery points into {old}"


def rebase(root, olds, new=None, dry_run: bool = False, before: dict | None = None, _heads: dict | None = None) -> dict:
    """Point the files under root/output/ that name an old folder (`olds`) at `new` (default: root), keeping each file's
    modification time: the JSON files that carry media paths (REBASE_JSON and SIGNED; inside the client database
    root-relative), and .md/.xml/... text. A log (history) or a Premiere/AE project (binary) is never rewritten: those
    are listed with what happens to them. Writes only with `dry_run` False, through linksafe (never through a link).
    The approvals a rewrite voids (`before`: approvals() as they held in the old folder, default: here before the
    rewrite) are listed in `voided` (a dry run: the forecast) and, applied, added to VOIDED_REL (the forecast first, so
    a run stopped part way still lists them; `_heads`: the old folders' looked-up forms, shared by both passes so an
    offline share is looked up once). Returns {"rewritten":
    [{file, values}], "kept": [{file, why}], "projects": [{file, app, fix}], "voided": [{item, kind, ...}], "errors"}."""
    root = Path(root)
    new = Path(new) if new is not None else root
    olds = [o for o in dict.fromkeys(str(o) for o in olds if o) if not _is_root(o, new)]
    rep = {"rewritten": [], "kept": [], "projects": [], "voided": [], "errors": []}
    if not olds:
        return rep
    before = approvals(root) if before is None else before
    forced: list = []
    if not dry_run:             # first the forecast, so a run stopped part way (an error that escapes, Ctrl+C, a crash)
        heads: dict = {} if _heads is None else _heads                       # still lists what it voided so far
        ahead = rebase(root, olds, new, dry_run=True, before=before, _heads=heads)["voided"]
        added: set = set()
        if ahead:
            try:
                added = _record_voided(root, ahead, hashed=False)
            except (Guidance, OSError, ValueError) as e:
                rep["errors"].append({"file": VOIDED_REL, "why": str(e)})
                return rep                     # nothing rewritten: no approval voided without a record
    tp, needles = _pairs(olds, new, True), _needles(olds)
    heads = ({} if _heads is None else _heads) if dry_run else heads
    ctx_abs = (olds, new, _pairs(olds, new, False), False, heads)
    ctx_rel = (olds, new, _pairs(olds, new, False, True), True, heads)
    owned = {f"output/client_database/{r}" for r in client_db.path_files(root / "output" / "client_database")}
    for rel, size, _m in scan(root, "scan")["files"]:
        if rel in owned or rel in (PENDING_REL, VOIDED_REL):   # client_db.migrate's (stored relative, never
            continue                                     # re-absolutised); this module's own records
        low = rel.casefold()
        ext = os.path.splitext(low)[1]
        p = str(root.joinpath(*rel.split("/")))
        if ext in PROJECT_EXT and not low.startswith(("data/", "assets/")):
            hit = _names(p, needles, (lambda q: gzip.open(q, "rb")) if ext == ".prproj" else (lambda q: open(q, "rb")))
            if hit or hit is None:
                rep["projects"].append({"file": rel, "app": PROJECT_EXT[ext], "fix": _project_fix(rel, ext)
                                        if hit else "couldn't read it to check: open it and relink if needed"})
            continue
        if not low.startswith("output/") or ext not in TEXT_EXT | LOG_EXT | {".json"}:
            continue
        if size > TEXT_MAX:
            rep["kept"].append({"file": rel, "why": "too big to check (over 64 MB)"})
            continue
        why = "a log of what happened in the old folder: kept as written" if ext in LOG_EXT else \
            _rewritable(rel, ext)
        if why:
            if _names(p, needles, lambda q: open(q, "rb")):
                rep["kept"].append({"file": rel, "why": why})
            continue
        try:
            raw = Path(_x(p)).read_bytes()
            text = raw.decode("utf-8-sig" if ext == ".json" else "utf-8")
            if ext == ".json":
                count = [0]
                new_doc = _rebase_doc(json.loads(text), ctx_rel if rel.startswith("output/client_database/") and
                                      rel != BRAND_TOKENS else ctx_abs, count)
                n, data = count[0], json.dumps(new_doc, ensure_ascii=False, indent=2) + "\n"
            else:
                data, n = _rebase_text(text, olds, new, tp, heads)
        except (OSError, ValueError, RecursionError) as e:
            if _names(p, needles, lambda q: open(q, "rb")):
                rep["kept"].append({"file": rel, "why": f"names the old folder but couldn't be read ({type(e).__name__})"
                                                       ": it is refreshed when its step runs again"})
            continue
        if _names_text(data, needles):
            rep["kept"].append({"file": rel, "why": "still names the old folder in a form a move doesn't rewrite (a "
                                                    "link typed by hand?): check it yourself"})
        if not n:
            continue
        if not dry_run:
            try:
                st = os.stat(_x(p))
                linksafe.replace_atomic(p, root, data.encode("utf-8"), within="output")
                os.utime(_x(p), ns=(st.st_atime_ns, st.st_mtime_ns))
            except (Guidance, OSError) as e:
                rep["errors"].append({"file": rel, "why": str(e)})
                continue
            if rel.endswith("/02_transcription/words.json") and rel.count("/") == 4:
                try:
                    _pin_transcript_check(root, rel, hashlib.sha1(raw).hexdigest())
                except (Guidance, OSError) as e:      # the old check can't be pinned: listed whatever it says now
                    rep["errors"].append({"file": rel[:-len("words.json")] + "verification.json", "why": str(e)})
                    key = tuple(rel.split("/")[1:3]) + ("transcript",)
                    if before.get(key) is not False:         # never confirmed: nothing to list (r2 N-P3-2)
                        forced.append(key)
        rep["rewritten"].append({"file": rel, "values": n})
    from .safety.takes import ED, HISTORY
    for r in list(rep["rewritten"]):
        if r["file"].endswith("/" + ED) and _has_steps(root.joinpath(*r["file"].split("/")[:-2], *HISTORY.split("/"))):
            rep["kept"].append({"file": r["file"][:-len(ED)] + HISTORY,
                                "why": "`reel takes --undo` steps were recorded against the plan as it was before the "
                                       "move: an undo now refuses (nothing is overwritten); change the takes with "
                                       "`reel takes --drop/--keep` instead"})
    hit = {r["file"] for r in rep["rewritten"]}
    if dry_run:
        rep["voided"] = _voided(root, before, None, hit)
    else:                       # also after an error: what was rewritten so far voided its approvals (a rerun can't see
        rep["voided"] = _voided(root, before, approvals(root), hit, forced)    # them any more)
        if rep["voided"] or ahead:
            try:
                _record_voided(root, rep["voided"], drop=added)
            except (Guidance, OSError, ValueError) as e:
                rep["errors"].append({"file": VOIDED_REL, "why": str(e)})
    return rep


# --------------------------------------------------------------------------- approvals a move voids (ruling (c))
def _items(root: Path) -> list[tuple[str, str]]:
    """(folder, id) of every clip/reel (output/projects) and episode (output/episodes) folder, never through a link."""
    from .common import check_project_id
    out = []
    for folder, what in (("projects", "video id"), ("episodes", "episode id")):
        try:
            with os.scandir(_x(str(root / "output" / folder))) as it:
                names = sorted(e.name for e in it if e.is_dir(follow_symlinks=False) and not e.name.startswith((".", "_")))
        except (FileNotFoundError, NotADirectoryError):
            continue
        for n in names:
            try:
                check_project_id(n, what, strict=folder == "episodes")
            except Guidance:
                continue                                 # not an item folder the engine made
            out.append((folder, n))
    return out


def _plan_holds(p) -> bool:
    from .plan import approval_state
    return approval_state(p)["state"] == "current"


def _transcript_holds(p) -> bool:
    from .transcribe import transcript_verified
    return transcript_verified(p)


def _transcript_holds_pinned(p) -> bool:
    """For a check a move voided: given again, i.e. recorded with the current words' hash (`reel transcript-verify`
    always records it), never the old form without a hash."""
    from .transcribe import words_fingerprint
    v = json.loads(Path(_x(str(p.p(APPROVALS["transcript"][0])))).read_bytes().decode("utf-8-sig"))
    return isinstance(v, dict) and bool(v.get("verified")) and v.get("words_sha1") == words_fingerprint(p)


def _proposals_hold(p) -> bool:
    doc = json.loads(p.p(APPROVALS["cut-proposals"][0]).read_text(encoding="utf-8-sig"))
    words = p.p("02_transcription/words.json")
    return isinstance(doc, dict) and words.is_file() and \
        hashlib.sha1(words.read_bytes()).hexdigest() == doc.get("words_sha1")


def _review_holds(p) -> bool:
    from . import review_flags
    return review_flags.load(p) is not None


def _reels_hold(p) -> bool:
    from .reels import reels_plan_fingerprint
    doc = json.loads(p.p(APPROVALS["reels-plan"][0]).read_text(encoding="utf-8-sig"))
    return isinstance(doc, dict) and doc.get("fingerprint") == reels_plan_fingerprint(p)


_HOLDS = {"plan": _plan_holds, "transcript": _transcript_holds, "cut-proposals": _proposals_hold,
          "review": _review_holds, "reels-plan": _reels_hold}


def approvals(root) -> dict:
    """{(folder, item, kind): True (it holds) | False (it does not) | None (it can't be told here)} of every approval or
    sign-off (APPROVALS) whose own file is in an item's folder. Reads only."""
    from .common import Context, Paths, use_context
    from .episode import EpisodePaths
    root = Path(root)
    out: dict = {}
    with use_context(Context(root)):
        for folder, item in _items(root):
            p = EpisodePaths(root, item) if folder == "episodes" else Paths(root, item)
            for kind, spec in APPROVALS.items():
                if kind == "reels-plan" and folder != "episodes" or not p.p(spec[0]).is_file():
                    continue
                try:
                    out[(folder, item, kind)] = bool(_HOLDS[kind](p))
                except Exception:  # noqa: BLE001 — a check that can't run here (damaged file, no plan): "can't tell",
                    out[(folder, item, kind)] = None     # never "holds"; a move lists it to be given again
    return out


def _motion(root: Path, folder: str, item: str) -> bool:
    return root.joinpath("output", folder, item, "01_analysis", "motion-plan.json").is_file()


def _entry(folder: str, item: str, kind: str, motion: bool = False) -> dict:
    """One voided approval: the move's result line (`how`: the lead's command) and its NEEDS-YOU words (no commands)."""
    rel, en, ar, again, again_ar = APPROVALS[kind]
    return {"folder": folder, "item": item, "kind": kind, "file": f"output/{folder}/{item}/{rel}",
            "text": en.format(item=item), "text_ar": ar.format(item=item),
            "why": f"The move pointed {item}'s files at the new folder, so the approval given in the old folder no "
                   f"longer matches them; nothing approves it again by itself: {again}.",
            "why_ar": f"النقل خلّى ملفات {item} تشاور على الفولدر الجديد، فالموافقة اللي اتعملت في الفولدر القديم "
                      f"مبقتش ماشية عليها، ومفيش حاجة بتوافق تاني لوحدها: {again_ar}.",
            "how": HOW["plan-motion" if kind == "plan" and motion else kind].format(item=item)}


def _bound_hit(root: Path, key: tuple, hit: set) -> bool:
    """Whether the move rewrote a file the approval `key` hashes."""
    folder, item, kind = key
    base, motion = f"output/{folder}/{item}/", _motion(root, folder, item)
    bound = BOUND.get(kind) or (MOTION_BOUND if motion else TIMELINE_BOUND)
    return any(base + b in hit for b in bound) or kind in ("plan", "review") and motion and BRAND_TOKENS in hit


def _voided(root: Path, before: dict, after: dict | None, hit: set, forced=()) -> list[dict]:
    """The approvals a move voided: one that held before and does not hold now, or one that could not be told and
    whose hashed file was rewritten, or one `forced` (an old transcript check that could not be pinned). `after` None
    (a dry run): the forecast, every one that holds or can't be told whose hashed file would be rewritten."""
    keys = set(forced)
    for key, was in before.items():
        if was is False:
            continue
        if after is None or was is None:
            if _bound_hit(root, key, hit) and (after is None or after.get(key) is not True):
                keys.add(key)
        elif after.get(key) is not True:
            keys.add(key)
    return [_entry(*k, motion=_motion(root, k[0], k[1])) for k in sorted(keys)]


def _pin_transcript_check(root: Path, words_rel: str, old_sha: str):
    """A transcript check recorded before checks carried the words' hash counts for any words (transcribe
    .transcript_verified): once a move has rewritten the words, write into it the hash of the words it was given for
    (`old_sha`), so it is void like every other check instead of silently holding for the rewritten words. Never through
    a link; a damaged record is no check that holds (approvals() can't tell it; it is listed), left as it is."""
    vf = str(root.joinpath(*words_rel.split("/")[:-1], "verification.json"))
    if not os.path.lexists(_x(vf)):
        return
    if linksafe.is_link(vf):
        raise OSError(0, f"{vf} is a link: never written through")
    try:
        doc = json.loads(Path(_x(vf)).read_bytes().decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return                                     # damaged: holds nothing (listed when its words were rewritten)
    if not isinstance(doc, dict) or not doc.get("verified") or doc.get("words_sha1") is not None:
        return
    doc["words_sha1"] = old_sha
    st = os.stat(_x(vf))
    linksafe.replace_atomic(vf, root, (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                            within="output")
    os.utime(_x(vf), ns=(st.st_atime_ns, st.st_mtime_ns))


def _key(v) -> tuple | None:
    """(folder, item, kind) of a record entry, or None for anything else (hostile or damaged content is skipped)."""
    if not isinstance(v, dict):
        return None
    k = (v.get("folder"), v.get("item"), v.get("kind"))
    return k if all(isinstance(x, str) for x in k) and k[0] in ("projects", "episodes") and k[2] in APPROVALS else None


def _file_sha(root: Path, rel: str) -> str | None:
    """The hash of an approval file as an approval: its JSON without "stale" (a re-plan marks an approval stale; that is
    no approval given again) in a fixed form, or its bytes when it is no JSON object. None: no file."""
    f = str(root.joinpath(*rel.split("/")))
    try:
        if not os.path.isfile(_x(f)):
            return None
        raw = Path(_x(f)).read_bytes()
    except OSError:
        return None
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        doc = None
    if isinstance(doc, dict):
        raw = json.dumps({k: v for k, v in doc.items() if k != "stale"}, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha1(raw).hexdigest()


def _record_voided(root: Path, voided: list[dict], hashed: bool = True, drop=()) -> set:
    """Add the voided approvals to VOIDED_REL, each with the hash of its approval file as the move left it: NEEDS-YOU
    lists it only while that file is unchanged and does not hold (an approval given again changes it; a later re-plan
    is the usual flow then, never "client moved"). A newer entry for the same item and kind replaces the older one.
    `hashed` False (an applied run's forecast, written before anything is rewritten): a transcript check gets no hash
    (the run may still pin it), listed while it does not hold. `drop`: the keys that forecast ADDED (returned), removed
    unless the final list has them; an older entry is never dropped by it."""
    f = str(root.joinpath(*VOIDED_REL.split("/")))
    entries = {}
    if os.path.lexists(_x(f)):
        try:
            old = json.loads(Path(_x(f)).read_bytes().decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            old = None                             # damaged: rebuilt from this move's list
        for v in old.get("voided") if isinstance(old, dict) and isinstance(old.get("voided"), list) else []:
            k = _key(v)
            if k and (v.get("sha1") is None or isinstance(v.get("sha1"), str)):
                entries[k] = {"folder": k[0], "item": k[1], "kind": k[2], "sha1": v.get("sha1")}
    for k in drop:
        entries.pop(k, None)
    added = set()
    for v in voided:
        k = (v["folder"], v["item"], v["kind"])
        if k not in entries:
            added.add(k)
        elif not hashed:
            continue                               # the forecast keeps an older entry as it is
        entries[k] = {"folder": k[0], "item": k[1], "kind": k[2],
                      "sha1": _file_sha(root, v["file"]) if hashed or k[2] != "transcript" else None}
    doc = {"schema": 1, "voided": [entries[k] for k in sorted(entries)]}
    linksafe.replace_atomic(f, root, (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
                            within="output")
    return added


def _still_holds(root: Path, key: tuple) -> bool | None:
    from .common import Context, Paths, use_context
    from .episode import EpisodePaths
    folder, item, kind = key
    if kind == "reels-plan" and folder != "episodes":
        return None
    with use_context(Context(root)):
        p = EpisodePaths(root, item) if folder == "episodes" else Paths(root, item)
        try:
            return bool((_transcript_holds_pinned if kind == "transcript" else _HOLDS[kind])(p))
        except Exception:  # noqa: BLE001 — a check that can't run (damaged file, no plan): not given again, still listed
            return None


def still_void(root) -> list[dict]:
    """NEEDS-YOU's lines for the approvals a move voided (VOIDED_REL), Arabic first: each with folder, item, kind,
    file (the ref), text, text_ar, why, why_ar, how. One is listed while its item is there, its approval file is the one
    the move left (same hash; a missing hash: any) and it does not hold. Reads only; a damaged record raises
    ValueError (NEEDS-YOU names it unread)."""
    root = Path(root)
    f = str(root.joinpath(*VOIDED_REL.split("/")))
    if not os.path.isfile(_x(f)):
        return []
    doc = json.loads(Path(_x(f)).read_bytes().decode("utf-8-sig"))
    if not isinstance(doc, dict) or not isinstance(doc.get("voided"), list):
        raise ValueError(f"{VOIDED_REL}: not a list of voided approvals")
    items = set(_items(root))
    out = []
    for v in doc["voided"]:
        k = _key(v)
        if not k or (k[0], k[1]) not in items or not isinstance(v.get("sha1"), (str, type(None))):
            continue
        e = _entry(*k, motion=_motion(root, k[0], k[1]))
        now = _file_sha(root, e["file"])
        if now is None or v.get("sha1") is not None and now != v["sha1"] or _still_holds(root, k) is True:
            continue
        out.append(e)
    return sorted(out, key=lambda e: (e["folder"], e["item"], e["kind"]))


def _names_text(s: str, needles: list) -> bool:
    b = s.encode("utf-8")
    hay = b.lower() if FOLD_CASE else b
    return any(n in hay for n in needles)


def _has_steps(p: Path) -> bool:
    try:
        doc = json.loads(Path(_x(p)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and bool(doc.get("steps"))


# --------------------------------------------------------------------------- a copy nobody migrated
def _foreign(root: Path, v) -> str | None:
    """The folder `v` (an absolute path outside the client) was copied from, when the same file is here under it."""
    from pathlib import PurePosixPath, PureWindowsPath
    if not isinstance(v, str) or not v or client_db.is_relative(v) or client_db.rel_under(v, str(root)) is not None:
        return None
    win = bool(PureWindowsPath(v).drive) or "\\" in v
    pp = PureWindowsPath(v) if win else PurePosixPath(v)
    if not pp.is_absolute():
        return None
    parts = list(pp.parts)
    for i in range(1, len(parts) - 1):
        here = root.joinpath(*parts[i:])
        if parts[i].lower() in client_db.ANCHORS and here.exists():
            if client_db.native_abs(v) and _is_root(real(here), real(v)):   # the same file, through one of the client's
                return None                              # own links (a data/ junction to a store: older caches keyed its
            return str(type(pp)(*parts[:i]))             # real path, or another alias of it)
    return None


def _walk_known_paths(root: Path, fn):
    """Call fn on every path value of the client database (and the video part of the reference cache's keys) and of
    discovery's inventory: what the first readers of a client open."""
    db = root / "output" / "client_database"
    for rel in client_db.path_files(db):
        try:
            doc = client_db.read_json(db / rel)
        except ValueError:
            continue
        for spec in client_db.path_fields(rel):
            client_db._walk(doc, spec, fn)
        if rel == "reference_analysis/cache.json" and isinstance(doc, dict):
            for k in doc:
                fn(str(k).partition("|")[0])
    try:
        inv = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        inv = None
    for f in (inv.get("files") if isinstance(inv, dict) else None) or []:
        if isinstance(f, dict):
            fn(f.get("path"))


def _pending(root: Path) -> str | None:
    """The old folder an "already moved" run that did not end cleanly recorded (PENDING_REL), when it is a plausible
    one (a hostile or damaged marker is ignored: never a drive, the home folder or the client itself)."""
    f = str(Path(root).joinpath(*PENDING_REL.split("/")))
    try:
        doc = json.loads(Path(_x(f)).read_bytes().decode("utf-8-sig")) if os.path.isfile(_x(f)) else None
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    old = doc.get("old_root") if isinstance(doc, dict) else None
    if not isinstance(old, str) or not client_db.native_abs(old) or plausible_old(root, old, pointed=False):
        return None
    return old


def detect_old_root(root) -> str | None:
    """The folder this client was copied or moved from: the one an unfinished "already moved" run recorded (its files
    may no longer name it), else read off its database and discovery inventory: the part before the anchor folder
    (assets | data | output) of an outside path whose tail exists here; the most common one."""
    root = Path(root)
    pending = _pending(root)
    if pending:
        return pending
    seen: dict[str, int] = {}

    def note(v):
        old = _foreign(root, v)
        if old:
            seen[old] = seen.get(old, 0) + 1
        return v
    _walk_known_paths(root, note)
    return max(seen, key=lambda k: seen[k]) if seen else None


def unmigrated(root) -> dict | None:
    """The CLI's refusal, before any other command reads the client, when it is a copy whose database or discovery
    still names the folder it was copied from (else preflight reads the ORIGINAL clip and a build imports it)."""
    root = Path(os.path.abspath(Path(root).expanduser()))
    if not ((root / "assets").is_dir() and (root / "data").is_dir()):
        return None
    old = detect_old_root(root)
    if not old:
        return None
    if _pending(root):
        return {"refused": f"آخر تشغيل لـ --already-moved مخلصش، فشوية ملفات ممكن لسه بتشاور على {old}، فمش هقرا ولا "
                           f"هكتب فيه حاجة / the last `client-move --already-moved` here did not finish: some files may "
                           f"still point at {old} (nothing was read or written)",
                "how": f"Run `reel client-move --root \"{root}\" --already-moved --apply` again and fix what it "
                       "reports (a file another program holds, a link, a read-only drive).",
                "copied_from": old}
    return {"refused": f"فولدر العميل ده نسخة من {old} وملفاته لسه بتشاور على هناك، فمش هقرا ولا هكتب فيه حاجة / "
                       f"this client folder is a copy of {old}: its files still point there (nothing was read or "
                       "written)",
            "how": f"Make the copy use its own files first: `reel client-move --root \"{root}\" --already-moved` "
                   "(a dry run that shows what changes), then the same with --apply.",
            "copied_from": old}


# --------------------------------------------------------------------------- the copy
def _top(sc: dict, mode: str) -> list[str]:
    """The top-level names this copy makes (what a rollback may remove)."""
    names = {r.split("/")[0] for r in sc["dirs"]} | {r.split("/")[0] for r, _s, _m in sc["files"]} | \
        {lk["rel"].split("/")[0] for lk in sc["links"]} | {INCOMPLETE}
    if mode == "clone":
        names |= {"assets", "data", ".whynot-client"}
    return sorted(names)


def _rollback(dest: Path, names: list[str], made_dest: bool):
    """Remove what this run made: each of its top-level names (links unlinked as names, never entered), then the folder
    itself when this run created it and it is empty again."""
    for n in names:
        if os.path.lexists(_x(dest / n)):
            linksafe.remove(dest / n, dest)
    if made_dest:
        os.rmdir(_x(dest))


def _copy(src: Path, dest: Path, sc: dict, mode: str) -> list[dict]:
    """Make the copy; returns the links it made. Raises on the first failure (the caller removes the copy)."""
    made_links = []
    for rel in sc["dirs"]:
        os.mkdir(_x(dest.joinpath(*rel.split("/"))))
    if mode == "clone":
        for d in ("assets", "data"):
            if not (dest / d).exists():
                os.mkdir(_x(dest / d))
    for rel, _size, _m in sc["files"]:
        s, d = str(src.joinpath(*rel.split("/"))), str(dest.joinpath(*rel.split("/")))
        if os.path.lexists(_x(d)):
            raise FileExistsError(17, "the name is taken in the copy", d)
        shutil.copyfile(_x(s), _x(d), follow_symlinks=False)
        shutil.copystat(_x(s), _x(d), follow_symlinks=False)
        if rel.startswith("output/") and not os.stat(_x(d)).st_mode & stat.S_IWRITE:
            os.chmod(_x(d), stat.S_IMODE(os.stat(_x(d)).st_mode) | stat.S_IWRITE)   # engine files: rewritable here
    for lk in sc["links"]:
        at = str(dest.joinpath(*lk["rel"].split("/")))
        tgt = _new_target(lk, src, dest)
        try:
            _make_link(lk, at, tgt)
        except OSError as e:
            raise OSError(e.errno, f"can't recreate the {lk['kind']} {lk['rel']} -> {tgt} "
                                   f"({e.strerror or type(e).__name__})") from None
        made_links.append({"link": lk["rel"], "kind": lk["kind"], "from": lk["target"], "to": tgt})
    return made_links


def _dir_times(src: Path, dest: Path, sc: dict):
    """Folders last, deepest first: their times stay the source's (after everything inside them was written)."""
    for rel in reversed(sc["dirs"]):
        shutil.copystat(_x(src.joinpath(*rel.split("/"))), _x(dest.joinpath(*rel.split("/"))), follow_symlinks=False)


def _verify(src: Path, dest: Path, sc: dict) -> tuple[list[str], list[str]]:
    """(problems, time_warnings): every file there with its size, the database byte-identical, the times kept."""
    problems, times = [], []
    got = {r: (s, m) for r, s, m in scan(dest, "verify")["files"]}
    for rel, size, mns in sc["files"]:
        if rel not in got:
            problems.append(f"missing in the copy: {rel}")
            continue
        s2, m2 = got[rel]
        if s2 != size:
            problems.append(f"size differs: {rel} ({size} -> {s2})")
        elif rel.startswith("output/client_database/") and \
                _sha1(str(src.joinpath(*rel.split("/")))) != _sha1(str(dest.joinpath(*rel.split("/")))):
            problems.append(f"content differs: {rel}")
        if mns // 1_000_000_000 != m2 // 1_000_000_000:
            times.append(rel)
    return problems, times


def _rewrite_at(dest: Path, olds: list[str], command: str, before: dict) -> tuple[dict, dict]:
    """Under the new folder's own writer lock: the database made relative, everything else under output/ pointed at
    the new folder (`before`: the approvals as they held in the old folder). The lease is not left behind in the new
    folder."""
    from . import writer_lock
    from .client_move_paths import first_refusal
    linked = first_refusal(dest, (dest / "output", dest / writer_lock.LOG_REL, dest / writer_lock.LOCK_REL))
    if linked or linksafe.is_link(dest / "output"):
        raise OSError(0, (linked or {}).get("refused") or f"{dest / 'output'} is a link")
    lk = writer_lock.acquire(dest, command)
    try:
        db = client_db.migrate(dest / "output" / "client_database", old_roots=olds)
        rb = rebase(dest, olds, before=before)
    finally:
        lk.release()
        if (writer_lock.read(dest) or {}).get("session_id") == lk.sid:     # held for the session: not in the copy
            os.unlink(linksafe.confine(writer_lock.LOCK_REL, dest, within="output"))
    return db, rb


def _copy_client(src, dest, mode: str, apply: bool) -> dict:
    src, dest = Path(os.path.abspath(Path(src).expanduser())), Path(os.path.abspath(Path(dest).expanduser()))
    verb = "client-move" if mode == "move" else "client-clone"
    ref = check(src, dest, mode)
    copied = unmigrated(src) if "refused" not in ref else None
    if copied:
        ref = dict(copied, refused=copied["refused"].replace(" (nothing was read or written)", "; nothing was written"))
    if "refused" in ref:
        return {"mode": mode, "from": str(src), "to": str(dest), "applied": False, **ref}
    sc = scan(src, mode)
    total = sum(s for _r, s, _m in sc["files"])
    doc = {"mode": mode, "from": str(src), "to": str(dest), "applied": False, "files": len(sc["files"]),
           "folders": len(sc["dirs"]), "bytes": total, "excluded": sc["excluded"], "not_copied": sc["other"],
           "links": [{"link": lk["rel"], "kind": lk["kind"], "from": lk["target"], "to": _new_target(lk, src, dest)}
                     for lk in sc["links"]] if mode == "move" else [],
           "resumes_interrupted_copy": ref["partial"]}
    need =total + total // 100 + SPARE
    no_room = _refusal(f"not enough free space at {dest.parent}: the copy needs about {need // (1 << 20)} MB (nothing "
                       "was written)", "Free some space or pick another drive, then run it again.")
    if not ref["partial"] and _free(dest) < need:
        return dict(doc, **no_room)
    olds = list(dict.fromkeys([str(src), real(src)]))
    if not apply:
        if mode == "move":
            doc["outside_database"] = rebase(src, olds, new=dest, dry_run=True)
            doc["approvals_to_redo"] = doc["outside_database"]["voided"]
        close = (f" Close the Premiere and After Effects projects you have open at {src} first (an open project keeps "
                 "saving to the old folder while it is copied).") if mode == "move" else ""
        return dict(doc, next=f"dry run: nothing was written.{close} Run `reel {verb} --to <folder> --apply` to do it.")
    client_db._require_lock(src)
    names = _top(sc, mode)
    if ref["partial"]:
        _rollback(dest, sorted(e.name for e in os.scandir(_x(dest))), False)   # checked: all of it came from here
        if _free(dest) < need:
            return dict(doc, **no_room)
    made_dest = not os.path.lexists(dest)
    if made_dest:
        try:
            os.mkdir(_x(dest))
        except FileExistsError:
            return dict(doc, **_refusal(f"{dest} appeared while this was being prepared; nothing was written",
                                        "Run it again."))
    elif linksafe.is_link(dest) or not _empty(dest):
        return dict(doc, **_refusal(f"{dest} changed while this was being prepared (it is a link now, or not empty); "
                                    "nothing was written", "Run it again."))
    try:
        linksafe.create_new(INCOMPLETE, dest, (json.dumps({"from": str(src), "mode": mode, "started": time.strftime(
            "%Y-%m-%dT%H:%M:%S%z"), "started_ns": time.time_ns()}, ensure_ascii=False) + "\n").encode("utf-8"))
        before = approvals(src) if mode == "move" else {}  # a clone starts with none; the source's stay as they are
        made = _copy(src, dest, sc, mode)
        _dir_times(src, dest, sc)
        problems, times = _verify(src, dest, sc)
        if problems:
            raise OSError(0, "the copy doesn't match the client: " + "; ".join(problems[:5]))
        if mode == "clone":
            from .client_marker import write_marker
            write_marker(dest)
        rewrite, outside = _rewrite_at(dest, olds, f"reel {verb}", before)
        errors = rewrite["errors"] + outside["errors"]
        if errors:
            raise OSError(0, "the copy's files could not be rewritten for the new place: " +
                          "; ".join(f"{e['file']}: {e['why']}" for e in errors[:5]))
        _dir_times(src, dest, sc)                        # the rewrite touched folders (temp files): times back
    except BaseException as e:
        try:
            _rollback(dest, names, made_dest)
        except (OSError, Guidance) as e2:
            return dict(doc, **_refusal(f"the copy failed ({e}) and could not be removed completely ({e2})",
                                        f"In {dest}, delete only what this run made ({', '.join(names)}); anything "
                                        f"else there is not ours. The client at {src} is untouched. Then run it "
                                        "again."))
        if not isinstance(e, Exception):
            raise
        return dict(doc, **_refusal(f"the copy failed and was removed again: {e}", f"The client at {src} is "
                                    "untouched. Fix the cause, then run it again."))
    os.unlink(_x(dest / INCOMPLETE))
    doc.update(applied=True, links=made, database=rewrite, outside_database=outside, mtime_rounded=times,
               approvals_to_redo=_to_redo(dest, outside["voided"]))
    if times:
        doc["warnings"] = [f"{len(times)} file(s) lost part of their modification time on this drive (FAT/exFAT keeps "
                           "times to 2 s): `reel next` may ask to redo a step there. Prefer an NTFS / APFS drive."]
    if mode == "move":
        doc["old_folder"] = _old_folder(src, dest, outside["kept"], outside["projects"])
        doc["next"] = (f"close the Premiere and After Effects projects you have open at {src} first (an open project "
                       f"keeps saving to the old folder), then work from {dest} from now on" + _then(outside))
    else:
        doc["next"] = (f"a new client at {dest} with this client's brand database and no media: add its assets/ and "
                       "data/, then `reel discover` and `reel client-db` there")
    return doc


def _old_folder(src: Path, dest: Path, kept: list[dict], projects: list[dict]) -> str:
    """The delete advice for the old folder, Arabic first (reviews 7fcbc1d P3-2, 087e8e3 P3-1..3). Before the delete:
    the Premiere/After Effects projects that still link media there (`projects`: a byte search, never edited) are
    relinked or rebuilt; every distinct step that really writes a kept file a step may still open by the path it
    stores runs again (STEP_OF); a kept file no step writes again keeps the old folder until it is fixed by hand. A
    log (history), the client database's citations (never opened; its brand tokens and status are), the takes history
    (an undo refuses either way), the editor's sealed revise comments (a path in them is text) and an After Effects
    frames run's record (AE_FRAMES_RECORD) need nothing."""
    from .rules_loop import NOTES_REL
    from .safety.takes import HISTORY
    delete = (f"left in place at {src}: check the new folder (`reel next --root \"{dest}\"`), then delete the old one "
              "yourself")
    due = sorted(k["file"] for k in kept if os.path.splitext(k["file"])[1].casefold() not in LOG_EXT
                 and not (k["file"].startswith("output/client_database/") and k["file"] not in DB_REBASE + (BRAND_TOKENS,))
                 and not k["file"].endswith(("/" + HISTORY, "/" + NOTES_REL))
                 and not AE_FRAMES_RECORD.fullmatch(k["file"]))
    runs: dict = {}
    by_hand = []
    for rel in due:
        parts = rel.split("/")
        flag, table = STEP_OF.get(parts[1], (None, {})) if len(parts) > 3 and parts[0] == "output" else (None, {})
        tail = "/".join(parts[3:])
        verb = next((v for k, v in table.items() if tail == k or k.endswith("/") and tail.startswith(k)), None)
        if verb:
            runs.setdefault(f"`{verb} --root \"{dest}\" {flag} {parts[2]}`")
        else:
            by_hand.append(rel)
    ar, en = [], []
    if projects:
        names = [f"{p['file']} ({RELINK[p['app']]})" for p in projects]       # review b690c54 P3-2
        ar.append(f"افتح المشاريع دي من المكان الجديد ووصّل الميديا تاني، أو ابنيها تاني: {'، '.join(names)}")
        en.append(f"open these projects from the new place and relink their media, or rebuild them: "
                  f"{', '.join(names)}")
    if runs:
        ar.append(f"شغّل تاني: {'، '.join(runs)}")
        en.append(f"run again: {', '.join(runs)}")
    if by_hand:
        ar.append(f"سيب الفولدر القديم لحد ما الملفات دي تتصلّح بإيدك أو تتعمل تاني: {'، '.join(by_hand)}")
        en.append(f"keep the old folder until these files are fixed by hand or made again: {', '.join(by_hand)}")
    if not ar:
        return delete
    return f"قبل ما تمسح الفولدر القديم: {'؛ '.join(ar)}. Before you delete the old folder: {'; '.join(en)}. " \
           f"The old folder is {delete}"


def _to_redo(root: Path, voided: list[dict]) -> list[dict]:
    """This run's voided approvals, then the ones an earlier run voided that are still not given again (a run that
    stopped part way, an earlier move): once each. A damaged record adds nothing here (NEEDS-YOU names it unread)."""
    out = {(v["folder"], v["item"], v["kind"]): v for v in voided}
    try:
        for v in still_void(root):
            out.setdefault((v["folder"], v["item"], v["kind"]), v)
    except (OSError, ValueError, RecursionError):
        pass                                       # damaged record: named by NEEDS-YOU; this run's list stands
    return list(out.values())


def _then(outside: dict) -> str:
    out = []
    if outside["projects"]:
        out.append("relink or rebuild the Premiere/After Effects projects listed in `projects`")
    if outside["voided"]:
        out.append(f"give again the {len(outside['voided'])} approval(s) listed in `approvals_to_redo` (they are on "
                   "NEEDS-YOU too: the move voided them on purpose, nothing approves them again by itself)")
    return ("; then " + "; ".join(out)) if out else ""


def move(src, dest, apply: bool = False) -> dict:
    """`reel client-move --to DEST`: dry run unless `apply` (then this session must hold the client's writer lock)."""
    return _copy_client(src, dest, "move", apply)


def clone(src, dest, apply: bool = False) -> dict:
    """`reel client-clone --to DEST`: dry run unless `apply`."""
    return _copy_client(src, dest, "clone", apply)


def already_moved(root, old=None, apply: bool = False) -> dict:
    """The client folder was moved or copied by hand: rewrite its database's paths in place (relative) and point
    everything else under output/ at where it is now. Dry run unless `apply` (then under this session's writer lock)."""
    root = Path(os.path.abspath(Path(root).expanduser()))
    if not ((root / "assets").is_dir() and (root / "data").is_dir()):
        return _refusal(f"{root} is not a client folder (it needs assets/ and data/); nothing was written",
                        "Pass --root the client folder itself.")
    linked = _linked_database(root)
    if linked:
        return linked
    if old:
        bad = plausible_old(root, old)
        if bad:
            return _refusal(f"--from: {bad} (nothing was written)", "Give the folder the client was in before (the one "
                            "that held its assets/ and data/), or leave --from out to read it off the database.")
    old = str(old) if old else detect_old_root(root)
    olds = [old] if old else []
    db = root / "output" / "client_database"
    if apply:
        client_db._require_lock(root)
    marked = False
    if apply and olds and not (_pending(root) and _is_root(old, _pending(root))):
        try:                    # until a clean end: a rerun (and the copied-client refusal) still knows the old folder
            linksafe.replace_atomic(str(root.joinpath(*PENDING_REL.split("/"))), root, (json.dumps(
                {"old_root": old}, ensure_ascii=False) + "\n").encode("utf-8"), within="output")
            marked = True
        except (Guidance, OSError) as e:
            return _refusal(f"couldn't write {PENDING_REL} ({e}); nothing was written",
                            "Fix what it says (a link, a full or read-only drive), then run it again.")
    rep = client_db.migrate(db, old_roots=olds, dry_run=not apply)
    outside = rebase(root, olds, dry_run=not apply)
    doc = {"mode": "already-moved", "root": str(root), "old_root": old, "applied": apply, "database": rep,
           "outside_database": outside, "approvals_to_redo": _to_redo(root, outside["voided"])}
    errors = rep["errors"] + outside["errors"]
    # a damaged database file is no unfinished rewrite (a rerun can't rewrite it either, and `reel client-db` makes it
    # again): the marker goes unless a file could not be WRITTEN (r4 P3-1)
    if apply and not any(not e.get("damaged") for e in errors) and (marked or _pending(root)):
        try:
            os.unlink(linksafe.confine(PENDING_REL, root, within="output"))
        except (Guidance, OSError) as e:
            errors = [{"file": PENDING_REL, "why": f"couldn't be removed after a clean run ({e})"}]
    if errors:
        return dict(doc, ok=False, error="some files could not be rewritten: " +
                    "; ".join(f"{e['file']}: {e['why']}" for e in errors[:5]),
                    next="fix what each error says (a link, a damaged file, a file another program holds), then run "
                         "it again")
    if not rep["changed"] and not outside["rewritten"]:
        doc["next"] = "the client folder is already portable: nothing to change" + _then(outside)
    elif not apply:
        doc["next"] = "dry run: nothing was written. Run it again with --apply to rewrite."
    else:
        doc["next"] = "the client folder works from where it is now" + _then(outside)
    return doc
