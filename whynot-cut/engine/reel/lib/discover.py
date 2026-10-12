"""Stage 1: recursive input discovery, classification, environment audit."""
from __future__ import annotations

import platform
import re
import shutil
from pathlib import Path

from .common import (AUDIO_EXT, DOC_EXT, FONT_EXT, IMAGE_EXT, RAW_IMAGE_EXT, SUB_EXT, VIDEO_EXT,
                     Paths, ffmpeg_exe, models_dir, is_junk, now_iso, run, sha1_head, write_json, write_text)

# Role hints (3.0 T2.5, IM-8). Two kinds of hint:
#   * AMBIGUOUS words (ref, raw, stock, footage, about, bio) sit inside ordinary words and names ("Refractive", "Reflux",
#     "Preface", "Strawberry", "Biology"): they only count as a WORD of the path, delimited by anything that is not a
#     letter (space _ - . / digits) or by a lowercase-to-uppercase step ("RawClip", "Ref1").
#   * DISTINCTIVE asset hints (logo, headshot, brief, colo(u)r, palet, brand, font, photo, ...) keep substring matching as
#     in 2.x: "whitelogo.png", "clientbrief.docx", "brandcolors.txt" are what real asset folders hold.
_L = r"[^\W\d_]"                                 # one letter in any script
_LOWER_UPPER = re.compile(r"(?<=[a-z])(?=[A-Z])")
# B-roll: the glued "broll" stays a substring as in 2.x; the separated forms ("b-roll", "b_roll", "b roll") need a word
# start and end, so "Jacob rolls", "Bob rolling", "Sub roll" are not B-roll (fix round 2, review I1)
_BROLL = rf"broll|(?<!{_L})b[-_ ]rolls?(?!{_L})"
_HINTS = [  # (key, word-bounded?, regex on the lowercase path, role); the first hint that fits the file kind wins
    ("brief", False, r"brief", "client_brief"), ("profile", False, r"profile", "client_brief"),
    ("about", True, r"about(?:us|me)?", "client_brief"), ("bio", True, r"bios?", "client_brief"),
    ("biograph", False, r"biograph", "client_brief"),
    ("color", False, r"colou?r", "brand_colors"), ("palette", False, r"pal[ae]t", "brand_colors"),
    ("brand", False, r"brand", "branding_doc"), ("font", False, r"font", "typography"),
    ("typo", False, r"typo", "typography"),
    ("logo", False, r"logo", "logo"), ("headshot", False, r"headshot", "headshot"),
    ("portrait", False, r"portrait", "portrait"), ("photo", False, r"photo", "client_photo"),
    ("broll", False, _BROLL, "broll_video"), ("stock", True, r"stocks?", "broll_video"),
    ("ref", True, r"refs?|references?", "editing_reference"), ("raw", True, r"raw", "source_footage"),
    ("footage", True, r"footage", "source_footage"),
    ("music", False, r"music", "music"), ("sfx", False, r"sfx", "sfx"), ("sound", False, r"sound", "sfx"),
]
ROLE_HINTS = [(key, re.compile(rf"(?<!{_L})(?:{pat})(?!{_L})" if word else pat), word, role)
              for key, word, pat, role in _HINTS]
_BRAND_IMAGE = re.compile(r"brand|colo|palet")        # a poster in assets/Brand: an image whose colours can be measured
_BROLL_DOC = re.compile(rf"{_BROLL}|(?<!{_L})stocks?(?!{_L})")
CONFLICT_KEYS = {"ref", "raw", "stock", "broll"}      # only these hints are specific enough to warn when a folder disagrees

# hints only apply to file kinds they make sense for: "Profile.jpg" is a photo, not a client brief (seen on a real
# client folder); a poster in assets/Brand is a brand image whose colours can be measured
_ALLOWED = {"document": {"client_brief", "brand_colors", "branding_doc", "typography", "editing_reference"},
            "image": {"logo", "headshot", "portrait", "client_photo"},
            "raw_image": {"logo", "headshot", "portrait", "client_photo"},
            "video": {"editing_reference", "source_footage", "broll_video"},
            "audio": {"music", "sfx", "source_footage"}}
_DOC_ROLES = {"editing_reference": "editing_reference_doc"}
_VIDEO_ROLES = {"editing_reference": "editing_reference_video"}


def _words(rel: str) -> str:
    """The path as lowercase words: camelCase steps become boundaries."""
    return _LOWER_UPPER.sub(" ", rel).lower()


def hint_match(rel: str, kind: str | None = None) -> tuple[str, str] | None:
    """(key, role) of the first role hint found in the path that makes sense for the file kind, else None."""
    allowed = _ALLOWED.get(kind)
    low, words = rel.lower(), _words(rel)
    for key, rx, word, role in ROLE_HINTS:
        if (allowed is None or role in allowed) and rx.search(words if word else low):
            return key, role
    return None


def hint_role(rel: str, kind: str | None = None) -> str | None:
    m = hint_match(rel, kind)
    return m[1] if m else None


# The known data folders: the first folder under data/ decides the role of every file below it (any depth); filename
# hints only decide outside them. The folder is recognised by its WORDS, so "Raw", "Raw Footage", "RawClips", "Rushes",
# "References", "Refs", "B-roll", "Stock footage" all count. Role per file kind; a kind not listed falls through to the
# hints (a document under Raw is never a reference: it stays unclassified and discovery warns about it).
_FOLDER_ROLES = {
    "source": {"video": "source_footage", "audio": "source_footage", "document": "unclassified"},
    "reference": {"video": "editing_reference_video", "document": "editing_reference_doc"},
    "broll": {"video": "broll_video", "document": "broll_license"},
    "music": {"audio": "music"},
    "sfx": {"audio": "sfx"},
}
_FOLDER_WORDS = [   # (folder kind, words); the first row with a word in the folder name wins, the MOST SPECIFIC role
    # first: "Raw B-roll", "B-roll raw", "Raw Stock" are B-roll and "Reference Raw" is references, never source footage
    ("reference", {"ref", "refs", "reference", "references"}), ("broll", {"broll", "stock", "stocks"}),
    ("source", {"raw", "rushes"}), ("source", {"footage"}), ("music", {"music"}), ("sfx", {"sfx"}),
]


def folder_kind(name: str) -> str | None:
    """The kind of known data folder a folder name is (source/reference/broll/music/sfx), by its words."""
    w = {x for x in re.split(r"[^a-z]+", _words(name)) if x}
    if re.search(_BROLL, name.lower()):
        w.add("broll")
    return next((k for k, ws in _FOLDER_WORDS if ws & w), None)


def _folder_role(parts: list[str], kind: str) -> tuple[str | None, str]:
    """(role the known data folder gives this file, the path below that folder) or (None, whole path)."""
    if len(parts) > 2 and parts[0] == "data":
        fk = folder_kind(parts[1])
        role = _FOLDER_ROLES.get(fk, {}).get(kind) if fk else None
        if role:
            return role, "/".join(parts[2:])
    return None, "/".join(parts)


def classify(p: Path, rel: str) -> dict:
    ext = p.suffix.lower()
    kind = ("video" if ext in VIDEO_EXT else "audio" if ext in AUDIO_EXT else
            "image" if ext in IMAGE_EXT else "raw_image" if ext in RAW_IMAGE_EXT else
            "font" if ext in FONT_EXT else "subtitle" if ext in SUB_EXT else
            "document" if ext in DOC_EXT else "other")
    top = rel.split("/")[0]
    parts = rel.split("/")
    folder_role, below = _folder_role(parts, kind)
    role = None
    conflict = None
    if folder_role is None:
        role = hint_role(rel, kind)
        if kind in ("image", "raw_image") and role is None and _BRAND_IMAGE.search(rel.lower()):
            role = "brand_image"
        if kind == "document" and _BROLL_DOC.search(_words(rel)):
            role = "broll_license"      # SOURCES.md / licence next to the B-roll clips (not an editing reference)
    else:
        # the folder decides; a specific filename hint that says something else is reported (discover warns), never obeyed
        m = hint_match(below, kind)
        if m and m[0] in CONFLICT_KEYS:
            hint = (_VIDEO_ROLES if kind == "video" else _DOC_ROLES if kind == "document" else {}).get(m[1], m[1])
            if hint != folder_role and not (kind == "document" and folder_role in ("broll_license", "unclassified")):
                conflict = hint
    if top == "data" and len(parts) > 2 and parts[1].lower() == "episodes" and kind in ("video", "audio", "document"):
        # finished podcast episodes are cut into reels (podcast mode); never treated as a clip to edit whole.
        # An audio-only episode (an audio podcast) can only become motion videos (motion mode, 2.2).
        if kind == "document":
            return {"path": str(p), "rel": rel, "kind": kind, "ext": ext, "role": "episode_sheet",
                    "size_bytes": p.stat().st_size}
        return {"path": str(p), "rel": rel, "kind": kind, "ext": ext, "role": "episode", "media": kind,
                "size_bytes": p.stat().st_size}
    if folder_role:
        role = folder_role
    elif kind == "video" and top == "data":
        role = "editing_reference_video" if role == "editing_reference" else (role or "source_footage")
    elif kind == "document" and top == "data" and role != "broll_license":
        # only a document whose path says it is a reference (a word: ref, reference) is one; any other loose document in
        # data/ (notes, a music.json, a stray export) stays unclassified instead of silently steering the edit style
        role = "editing_reference_doc" if role == "editing_reference" else role
    if kind == "font":
        role = "brand_font"
    if kind == "subtitle":
        role = "existing_transcript"
    if kind in ("image", "raw_image") and top == "assets" and role is None:
        role = "client_image"
    item = {"path": str(p), "rel": rel, "kind": kind, "ext": ext, "role": role or "unclassified",
            "size_bytes": p.stat().st_size}
    if conflict:
        item["folder_hint_conflict"] = conflict       # the filename suggests this role; the folder said otherwise
    return item


def read_document(p: Path) -> str:
    """Plain text of a client document. macOS uses textutil/mdls when present; every OS has the pure-Python readers
    below (.docx, .rtf, .pdf via pypdf), so Windows reads the same briefs and colour files."""
    ext = p.suffix.lower()
    if ext in (".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".srt", ".vtt"):
        return p.read_text(encoding="utf-8", errors="replace")
    try:
        if ext in (".rtf", ".docx", ".doc", ".html") and shutil.which("textutil"):
            return run(["textutil", "-convert", "txt", "-stdout", str(p)]).stdout
        if ext == ".docx":
            return _docx_text(p)
        if ext == ".rtf":
            return _rtf_text(p.read_text(encoding="latin-1", errors="replace"))
        if ext in (".html", ".htm"):
            import html
            return html.unescape(re.sub(r"<[^>]+>", " ", p.read_text(encoding="utf-8", errors="replace")))
        if ext == ".pdf":
            txt = ""
            if shutil.which("mdls"):
                txt = run(["mdls", "-raw", "-name", "kMDItemTextContent", str(p)], check=False).stdout
            if not txt.strip() or txt.strip() == "(null)":
                txt = _pdf_text(p)
            return txt
    except Exception as e:  # noqa: BLE001  (a broken document must not stop discovery)
        return f"[unreadable {ext}: {type(e).__name__}]"
    return ""


def _docx_text(p: Path) -> str:
    import zipfile
    from xml.etree import ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(p) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    return "\n".join("".join(t.text or "" for t in para.iter(ns + "t")) for para in root.iter(ns + "p"))


_RTF_TOKEN = re.compile(r"\\(\*|[a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)", re.S)
_RTF_SKIP = {"*", "fonttbl", "colortbl", "expandedcolortbl", "stylesheet", "info", "pict", "listtable", "themedata"}


def _rtf_text(rtf: str) -> str:
    """Minimal RTF to text: keeps \\uN unicode escapes and \\'hh bytes, drops control words and header groups."""
    out, i, depth, skip = [], 0, 0, []
    uc_skip = 0
    while i < len(rtf):
        c = rtf[i]
        if c == "{":
            depth += 1
            i += 1
        elif c == "}":
            if skip and skip[-1] == depth:
                skip.pop()
            depth -= 1
            i += 1
        elif c == "\\":
            m = _RTF_TOKEN.match(rtf, i)
            if not m:
                i += 1
                continue
            word, num, hexb, sym = m.groups()
            i = m.end()
            if word in _RTF_SKIP:
                if not skip or skip[-1] != depth:
                    skip.append(depth)
            elif skip:
                pass
            elif word == "u" and num:
                out.append(chr(int(num) % 65536))
                uc_skip = 1                       # the ANSI fallback character that follows \uN
            elif word in ("par", "line"):
                out.append("\n")
            elif word == "tab":
                out.append("\t")
            elif hexb:
                if uc_skip:
                    uc_skip -= 1
                else:
                    out.append(bytes([int(hexb, 16)]).decode("cp1252", errors="replace"))
            elif sym in ("\\", "{", "}"):
                out.append(sym)
        else:
            if not skip and c not in "\r\n":
                if uc_skip:
                    uc_skip -= 1
                else:
                    out.append(c)
            i += 1
    return "".join(out)


def _pdf_text(p: Path) -> str:
    from pypdf import PdfReader
    return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)


def audit_environment() -> dict:
    from . import plat
    from .common import venv_python

    def which(n):
        return shutil.which(n)
    found = plat.adobe_report()                         # T2.11: a bad WHYNOT_*_APP is reported, not raised, here
    apps = {a["name"]: a["exe"] for a in found["all"]}
    tools = {
        "python_venv": str(venv_python()) if venv_python().exists() else None,
        "ffmpeg": ffmpeg_exe(), "ffprobe": which("ffprobe"),
        "osascript": which("osascript"), "textutil": which("textutil"), "sips": which("sips"),
        "powershell": which("powershell") or which("pwsh"),
    }
    mods = {}
    for m in ("faster_whisper", "av", "PIL", "fontTools", "arabic_reshaper", "bidi", "uharfbuzz", "freetype", "pypdf"):
        try:
            __import__(m)
            mods[m] = True
        except Exception:
            mods[m] = False
    aer = (found["aerender"] or {}).get("path")
    return {"generated": now_iso(), "os": plat.OS_NAME, "platform": platform.platform(), "machine": platform.machine(),
            "adobe_apps": apps, "aerender": aer,
            "tools": tools, "python_modules": mods,
            "models_dir": str(models_dir())}


def discover(paths: Paths, read_docs: bool = True) -> dict:
    if not paths.assets.is_dir() or not paths.data.is_dir():
        missing = [d.name for d in (paths.assets, paths.data) if not d.is_dir()]
        raise FileNotFoundError(f"Expected assets/ and data/ under {paths.root}; missing: {missing}")
    files, docs, skipped = [], {}, []
    for top in (paths.assets, paths.data):
        for p in sorted(top.rglob("*")):
            if p.is_dir():
                continue
            if is_junk(p):
                skipped.append(p.relative_to(paths.root).as_posix())
                continue
            rel = p.relative_to(paths.root).as_posix()
            item = classify(p, rel)
            item["fingerprint"] = sha1_head(p)
            files.append(item)
            if read_docs and item["kind"] in ("document", "subtitle"):
                txt = read_document(p)
                docs[rel] = txt
                item["text_chars"] = len(txt)
    by_role = {}
    for f in files:
        by_role.setdefault(f["role"], []).append(f["rel"])
    warnings = []
    if not by_role.get("source_footage") and not by_role.get("episode"):
        warnings.append("No source footage found in data/.")
    if not by_role.get("editing_reference_doc") and not by_role.get("editing_reference_video"):
        warnings.append("No editing reference (Markdown or video) found in data/.")
    if by_role.get("editing_reference_video") and not by_role.get("editing_reference_doc"):
        warnings.append("Editing reference supplied as VIDEO only (no Markdown) — style spec is derived "
                        "from measured cuts + visual review of contact sheets.")
    clash = [f for f in files if f.get("folder_hint_conflict")]
    if clash:
        warnings.append("Folder and file name disagree (the folder wins, so the file keeps the folder's role): "
                        + "; ".join(f"{f['rel']} (folder: {f['role']}, name suggests {f['folder_hint_conflict']})"
                                    for f in clash[:8])
                        + (f"; and {len(clash) - 8} more" if len(clash) > 8 else "")
                        + " - if the folder is wrong, the editor moves the file to the right data/ folder.")
    if len(by_role.get("client_brief", [])) > 1:
        warnings.append("Multiple client brief documents — check for conflicts.")
    loose = [f["rel"] for f in files if f["role"] == "unclassified" and f["kind"] == "document"
             and f["rel"].startswith("data/")
             and (hint_role(f["rel"]) is None or folder_kind(f["rel"].split("/")[1]) == "source")]
    if loose:
        warnings.append(f"Documents in data/ not used as editing references (data/Raw documents never are; elsewhere a 'ref' or 'reference' word in the path makes one): {', '.join(loose[:8])}"
                        f" — if one is a reference edit or a reels plan, move it to data/References/.")
    if len(by_role.get("editing_reference_doc", [])) > 1:
        warnings.append("Multiple editing-reference docs — check for conflicts; later files do not silently override.")
    if by_role.get("broll_video"):
        bdirs = {str(Path(r).parent).replace("\\", "/") for r in by_role["broll_video"]}
        lic = [f["rel"] for f in files if f["kind"] == "document" and str(Path(f["rel"]).parent).replace("\\", "/") in bdirs
               and any(k in f["rel"].lower() for k in ("licen", "source", "credit", "pexels", "rights"))]
        if not lic:
            warnings.append("B-roll videos found without a licence/sources file next to them (e.g. data/Broll/SOURCES.md): "
                            "confirm they are licensed before they go into a client edit.")
    if not by_role.get("music"):
        warnings.append("No music files supplied — background music track will be left as cue markers only.")
    if not by_role.get("sfx"):
        warnings.append("No SFX library supplied — pipeline will synthesize original procedural SFX.")
    inv = {"generated": now_iso(), "root": str(paths.root), "file_count": len(files),
           "files": files, "by_role": by_role, "skipped_junk": len(skipped), "warnings": warnings}
    return {"inventory": inv, "documents": docs}


def report_md(inv: dict, env: dict) -> str:
    L = ["# Input Discovery Report", "", f"Root: `{inv['root']}`  ", f"Generated: {inv['generated']}  ",
         f"Files: {inv['file_count']} (skipped {inv['skipped_junk']} system metadata files)", "", "## By role", ""]
    for role, rels in sorted(inv["by_role"].items()):
        L.append(f"### {role} ({len(rels)})")
        L += [f"- `{r}`" for r in rels]
        L.append("")
    L += ["## Warnings", ""] + ([f"- {w}" for w in inv["warnings"]] or ["- none"])
    L += ["", "## Environment", "", f"- Platform: {env['platform']}",
          f"- Adobe apps: {', '.join(env['adobe_apps']) or 'none'}", f"- aerender: {env['aerender']}"]
    L += [f"- {k}: {v}" for k, v in env["tools"].items()]
    L += [f"- python module {k}: {'OK' if v else 'MISSING'}" for k, v in env["python_modules"].items()]
    return "\n".join(L) + "\n"


DISCOVERY_WAIT_S = 600.0              # a second discovery of the same client waits for the running one (T2.4)


def run_discovery(paths: Paths) -> dict:
    """Discovery of one client runs one at a time (3.0 T2.4): parallel subagents never interleave its writes."""
    from .file_lock import locked
    if not paths.assets.is_dir() or not paths.data.is_dir():
        # before the lock: taking it creates `<folder>/output/discovery/*.lock`, which a wrong --root (or one inside
        # assets/ or data/, the read-only source folders) must never get. Same error as discover() raises.
        missing = [d.name for d in (paths.assets, paths.data) if not d.is_dir()]
        raise FileNotFoundError(f"Expected assets/ and data/ under {paths.root}; missing: {missing}")
    with locked(paths.output / "discovery" / "input-inventory.json", DISCOVERY_WAIT_S):
        return _run_discovery(paths)


def _run_discovery(paths: Paths) -> dict:
    res = discover(paths)
    env = audit_environment()
    inv = res["inventory"]
    out = paths.output
    write_json(out / "discovery/input-inventory.json", inv)
    write_json(out / "discovery/environment.json", env)
    for rel, txt in res["documents"].items():
        write_text(out / "discovery/extracted_text" / (rel.replace("/", "__") + ".txt"), txt)
    write_text(out / "discovery/discovery-report.md", report_md(inv, env))
    if paths.video_id:
        write_json(paths.p("00_inputs/input-manifest.json"), {
            "video_id": paths.video_id, "generated": inv["generated"],
            "source_footage": [f for f in inv["files"] if f["role"] == "source_footage"],
            "editing_references": [f for f in inv["files"] if f["role"].startswith("editing_reference")],
            "existing_transcripts": [f for f in inv["files"] if f["role"] == "existing_transcript"],
            "music": [f for f in inv["files"] if f["role"] == "music"],
            "sfx": [f for f in inv["files"] if f["role"] == "sfx"],
            "client_database": str(paths.client_db),
            "note": "Inputs are referenced in place and never modified."})
    return {"inventory": inv, "environment": env}
