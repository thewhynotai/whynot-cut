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
    old folder is LEFT in place: the editor deletes it after checking the new one.
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
from urllib.parse import quote

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
# transcript check, cut_proposals, motion_plan.fingerprint, reels.reels_plan_fingerprint): never rewritten by a move
SIGNED = ("01_analysis/timeline-spec.json", "01_analysis/motion-script.json", "01_analysis/reels-plan.json",
          "02_transcription/words.json", "06_audio/dialogue/pauses.json", "branding/brand-tokens.json")
# the JSON files known to carry media paths with nothing bound to their bytes (the release track's REL-PREVIEW list,
# without the signed ones): a move points them at the new folder. Per clip / episode: the part after its folder.
REBASE_JSON = {INVENTORY, "01_analysis/edit-decisions.json", "00_inputs/input-manifest.json", "00_inputs/preflight.json", "00_inputs/source.json",
               "02_transcription/transcript.json", "03_broll/captions/captions-manifest.json",
               "06_audio/sfx/sfx-library.json", "07_premiere/base-manifest.json", "07_premiere/ppro-build-result.json",
               "07_premiere/timeline-manifest.json", "08_quality_control/preview/preview-result.json",
               "08_quality_control/project-status.json", "08_quality_control/qc-results.json",
               "08_quality_control/visual-verification.json", "01_analysis/reference_analysis/reference-measurements.json"}
_END = r"(?=[\\/\"'`<>)\],;|\t\r\n]|$)"           # a root ends at a separator, a quote or the end, never mid-name


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


def _only_ours(dest: Path, src_files: dict, started_ns) -> bool:
    """Is everything in an interrupted copy something this client has (so removing it loses nothing of the editor's)?
    Every file must be one of the client's; outside output/ (rewritten for the new place) it may be shorter (the copy
    stopped while writing it), never larger; none newer than the interrupted run started. A file the client doesn't
    have, or a newer one, means someone worked there: refused."""
    if not isinstance(started_ns, int) or isinstance(started_ns, bool):
        return False
    for rel, size, mns in scan(dest, "verify")["files"]:
        if rel not in src_files or mns > started_ns:      # a copy keeps the client's times: newer = someone's work
            return False
        if size > src_files[rel] and not rel.startswith("output/"):
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
            mine = mark and mark.get("mode") == mode and isinstance(mark.get("from"), str) and mark["from"] and \
                _same(mark["from"], src) and \
                _only_ours(dest, {r: s for r, s, _m in scan(src, mode)["files"]}, mark.get("started_ns"))
            if not mine:
                return _refusal(f"{dest} exists and is not empty; nothing was written", pick)
            partial = True                               # our own copy, interrupted: it is removed and made again
    other = other_client(real(dest.parent) if partial else rd, src)    # a partial copy looks like a client itself
    if other:
        return _refusal(f"{dest} is inside another client's folder ({other}); nothing was written", pick)
    return {"ok": True, "partial": partial}


# --------------------------------------------------------------------------- what still names the old folder
def _forms(o: str, n: str, text: bool) -> list[tuple[str, str]]:
    """Each way a file spells a root, with the new root in the same spelling: as is, with forward slashes, escaped (JSON
    text, or a Python list's repr inside a message), and in text files also XML-escaped and as a file URL (interchange
    XML pathurl, %-encoded)."""
    from html import escape
    forms = [(o, n), (o.replace("\\", "/"), n.replace("\\", "/"))]
    forms += [(json.dumps(a, ensure_ascii=e)[1:-1], json.dumps(b, ensure_ascii=e)[1:-1])
              for a, b in list(forms) for e in (True, False)]
    if text:
        po, pn = o.replace("\\", "/"), n.replace("\\", "/")
        forms.append((quote(po if po.startswith("/") else "/" + po, safe="/:"),
                      quote(pn if pn.startswith("/") else "/" + pn, safe="/:")))
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
                out.append((re.compile(re.escape(a) + r"(?:\\\\|\\|/)", flags), ""))
            else:
                out.append((re.compile(re.escape(a) + _END, flags), b))
    return out


def _sub(s: str, pairs) -> tuple[str, int]:
    n = 0
    for pat, rep in pairs:
        s, k = pat.subn(lambda _m, rep=rep: rep, s)
        n += k
    return s, n


def _rebased_value(s: str, olds, new: Path, relative: bool):
    """A whole value that IS a path under an old root: rebuilt for this computer from its tail (a Windows value moved
    to a Mac gets "/" separators, never a file name with backslashes in it); root-relative POSIX inside the database."""
    for o in olds:
        tail = client_db.rel_under(s, o) if not client_db.is_relative(s) else None
        if tail:
            return tail if relative else str(new.joinpath(*tail.split("/")))
    return None


def _rebase_doc(node, ctx: tuple, count: list):
    olds, new, pairs, relative = ctx
    if isinstance(node, str):
        whole = _rebased_value(node, olds, new, relative)
        if whole is not None:
            count[0] += 1
            return whole
        s, k = _sub(node, pairs)
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
        for form in {o, o.replace("\\", "/"), o.replace("/", "\\"), json.dumps(o)[1:-1]}:
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


def _rewritable(rel: str) -> str | None:
    """Why a JSON file under output/ may NOT be rewritten (None = it may): an approval or sign-off hashes its exact bytes
    (the plan, the words, the motion script, the reels plan, the pauses, the brand tokens), or it is not on the list of
    files known to carry media paths and nothing else that is bound to them (REBASE_JSON)."""
    tail = rel.split("/", 3)[-1] if rel.startswith(("output/projects/", "output/episodes/")) else rel
    if any(rel.endswith("/" + s) for s in SIGNED):
        return ("an approval or sign-off is bound to its exact content (plan approval, transcript check, cut "
                "proposals, motion or reels plan): kept so it stays approved. It names the old folder until its step "
                "runs again; question for the executor in BL-14")
    if tail in REBASE_JSON or rel.startswith("output/client_database/"):
        return None
    return "not on the list of files a move may rewrite: it names the old folder until its step runs again"


def plausible_old(root, old) -> str | None:
    """Why `old` can't be the folder this client was moved from (None = it can): a drive or file-system root, the home
    folder, the client itself or a folder above it, or a folder no path of the database or inventory points into."""
    root = Path(root)
    parts = client_db._parts(str(old))
    home = client_db._parts(str(Path.home()))
    if len(parts) < 2 or _is_root(str(old), str(Path.home())) or len(parts) <= len(home) and \
            [x.casefold() for x in parts] == [x.casefold() for x in home[:len(parts)]]:
        return f"{old} is a drive, the top of the disk or your home folder, not a client folder"
    if _is_root(str(old), root) or client_db.rel_under(str(root), str(old)) is not None:
        return f"{old} is this client folder or a folder above it"
    seen = [0]

    def note(v):
        tail = client_db.rel_under(v, str(old)) if isinstance(v, str) and v and not client_db.is_relative(v) else None
        if tail and root.joinpath(*tail.split("/")).exists():
            seen[0] += 1
        return v
    _walk_known_paths(root, note)
    return None if seen[0] else f"nothing in this client's database or discovery points into {old}"


def rebase(root, olds, new=None, dry_run: bool = False) -> dict:
    """Point the files under root/output/ that name an old folder (`olds`) at `new` (default: root), keeping each file's
    modification time: the JSON files that carry media paths (REBASE_JSON; inside the client database root-relative),
    and .md/.xml/... text. A file whose exact content an approval or sign-off is bound to is never rewritten (SIGNED),
    nor a log (history) or a Premiere/AE project (binary): those are listed with what happens to them. Writes only with
    `dry_run` False, through linksafe (never through a link). Returns {"rewritten": [{file, values}], "kept": [{file,
    why}], "projects": [{file, app, fix}], "errors"}."""
    root = Path(root)
    new = Path(new) if new is not None else root
    olds = [o for o in dict.fromkeys(str(o) for o in olds if o) if not _is_root(o, new)]
    rep = {"rewritten": [], "kept": [], "projects": [], "errors": []}
    if not olds:
        return rep
    tp, needles = _pairs(olds, new, True), _needles(olds)
    ctx_abs, ctx_rel = (olds, new, _pairs(olds, new, False), False), (olds, new, _pairs(olds, new, False, True), True)
    owned = {f"output/client_database/{r}" for r in client_db.path_files(root / "output" / "client_database")}
    for rel, size, _m in scan(root, "scan")["files"]:
        if rel in owned:                                 # client_db.migrate's: stored relative, never re-absolutised
            continue
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
            _rewritable(rel) if ext == ".json" else None
        if why:
            if _names(p, needles, lambda q: open(q, "rb")):
                rep["kept"].append({"file": rel, "why": why})
            continue
        try:
            text = Path(_x(p)).read_bytes().decode("utf-8-sig" if ext == ".json" else "utf-8")
            if ext == ".json":
                count = [0]
                new_doc = _rebase_doc(json.loads(text), ctx_rel if rel.startswith("output/client_database/")
                                      else ctx_abs, count)
                n, data = count[0], json.dumps(new_doc, ensure_ascii=False, indent=2) + "\n"
            else:
                data, n = _sub(text, tp)
        except (OSError, ValueError) as e:
            if _names(p, needles, lambda q: open(q, "rb")):
                rep["kept"].append({"file": rel, "why": f"names the old folder but couldn't be read ({type(e).__name__})"
                                                       ": it is refreshed when its step runs again"})
            continue
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
        rep["rewritten"].append({"file": rel, "values": n})
    return rep


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
        if parts[i].lower() in client_db.ANCHORS and root.joinpath(*parts[i:]).exists():
            return str(type(pp)(*parts[:i]))
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


def detect_old_root(root) -> str | None:
    """The folder this client was copied or moved from, read off its database and discovery inventory: the part before
    the anchor folder (assets | data | output) of an outside path whose tail exists here; the most common one."""
    root = Path(root)
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
    return {"refused": f"this client folder is a copy of {old}: its files still point there (nothing was read or "
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


def _rewrite_at(dest: Path, olds: list[str], command: str) -> tuple[dict, dict]:
    """Under the new folder's own writer lock: the database made relative, everything else under output/ pointed at
    the new folder. The lease is not left behind in the new folder."""
    from . import writer_lock
    from .client_move_paths import first_refusal
    linked = first_refusal(dest, (dest / "output", dest / writer_lock.LOG_REL, dest / writer_lock.LOCK_REL))
    if linked or linksafe.is_link(dest / "output"):
        raise OSError(0, (linked or {}).get("refused") or f"{dest / 'output'} is a link")
    lk = writer_lock.acquire(dest, command)
    try:
        db = client_db.migrate(dest / "output" / "client_database", old_roots=olds)
        rb = rebase(dest, olds)
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
        return dict(doc, next=f"dry run: nothing was written. Run `reel {verb} --to <folder> --apply` to do it.")
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
        made = _copy(src, dest, sc, mode)
        _dir_times(src, dest, sc)
        problems, times = _verify(src, dest, sc)
        if problems:
            raise OSError(0, "the copy doesn't match the client: " + "; ".join(problems[:5]))
        if mode == "clone":
            from .client_marker import write_marker
            write_marker(dest)
        rewrite, outside = _rewrite_at(dest, olds, f"reel {verb}")
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
    doc.update(applied=True, links=made, database=rewrite, outside_database=outside, mtime_rounded=times)
    if times:
        doc["warnings"] = [f"{len(times)} file(s) lost part of their modification time on this drive (FAT/exFAT keeps "
                           "times to 2 s): `reel next` may ask to redo a step there. Prefer an NTFS / APFS drive."]
    if mode == "move":
        doc["old_folder"] = (f"left in place at {src}: check the new folder (`reel next --root \"{dest}\"`), then "
                             "delete the old one yourself")
        doc["next"] = f"work from {dest} from now on" + _then(outside)
    else:
        doc["next"] = (f"a new client at {dest} with this client's brand database and no media: add its assets/ and "
                       "data/, then `reel discover` and `reel client-db` there")
    return doc


def _then(outside: dict) -> str:
    out = []
    if outside["projects"]:
        out.append("relink or rebuild the Premiere/After Effects projects listed in `projects`")
    if any("approval" in k["why"] for k in outside["kept"]):
        out.append("the plans/transcripts listed in `outside_database.kept` still name the old folder (kept so they "
                   "stay approved): re-run their steps before a build, or wait for the executor's answer (BL-14)")
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
    rep = client_db.migrate(db, old_roots=olds, dry_run=not apply)
    outside = rebase(root, olds, dry_run=not apply)
    doc = {"mode": "already-moved", "root": str(root), "old_root": old, "applied": apply, "database": rep,
           "outside_database": outside}
    errors = rep["errors"] + outside["errors"]
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
