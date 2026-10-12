"""Stage 1: recursive input discovery, classification, environment audit."""
from __future__ import annotations

import platform
import re
import shutil
from pathlib import Path

from .common import (AUDIO_EXT, DOC_EXT, FONT_EXT, IMAGE_EXT, RAW_IMAGE_EXT, SUB_EXT, VIDEO_EXT,
                     Paths, ffmpeg_exe, models_dir, is_junk, now_iso, run, sha1_head, write_json, write_text)

# Role hints (3.0 T2.5, IM-8). A hint is a WORD in the path, never a substring: "Refractive", "Reflux", "Preface" are not
# "ref", "Stock market" in data/Raw is not B-roll. A word is delimited by anything that is not a letter (space, _, -, /,
# ., digits) or by a lowercase-to-uppercase step ("ClientBrief", "BrandColors"). Plurals are part of the pattern.
_L = r"[^\W\d_]"                                 # one letter in any script
_HINTS = [  # (regex of the word in the lowercase path, role); the first hint that fits the file kind wins
    (r"briefs?", "client_brief"), (r"profiles?", "client_brief"), (r"about", "client_brief"), (r"bios?", "client_brief"),
    (r"colou?rs?", "brand_colors"), (r"pal+[ae]tt?es?", "brand_colors"),
    (r"brands?|branding", "branding_doc"), (r"fonts?", "typography"), (r"typo|typography", "typography"),
    (r"logos?", "logo"), (r"head[-_ ]?shots?", "headshot"), (r"portraits?", "portrait"), (r"photos?", "client_photo"),
    (r"b[-_ ]?rolls?", "broll_video"), (r"stock", "broll_video"),
    (r"refs?|references?", "editing_reference"), (r"raw", "source_footage"), (r"footage", "source_footage"),
    (r"music", "music"), (r"sfx", "sfx"), (r"sounds?", "sfx"),
]
ROLE_HINTS = [(re.compile(rf"(?<!{_L})(?:{pat})(?!{_L})"), role) for pat, role in _HINTS]
_BRAND_IMAGE = re.compile(rf"(?<!{_L})(?:brands?|branding|colou?rs?|pal+[ae]tt?es?)(?!{_L})")
_BROLL_WORD = re.compile(rf"(?<!{_L})(?:b[-_ ]?rolls?|stock)(?!{_L})")
_LOWER_UPPER = re.compile(r"(?<=[a-z])(?=[A-Z])")

# The known data folders (the first folder under data/, any case): their files get the role of the folder; filename
# hints only decide outside them. role per file kind; a kind not listed falls through to the hints.
DATA_FOLDERS = {
    "raw": {"video": "source_footage", "audio": "source_footage"},
    "references": {"video": "editing_reference_video", "document": "editing_reference_doc"},
    "reference": {"video": "editing_reference_video", "document": "editing_reference_doc"},
    "refs": {"video": "editing_reference_video", "document": "editing_reference_doc"},
    "broll": {"video": "broll_video", "document": "broll_license"},
    "b-roll": {"video": "broll_video", "document": "broll_license"},
    "b_roll": {"video": "broll_video", "document": "broll_license"},
    "music": {"audio": "music"},
    "sfx": {"audio": "sfx"},
}
_DOC_ROLES = {"editing_reference": "editing_reference_doc"}
_VIDEO_ROLES = {"editing_reference": "editing_reference_video"}


def _words(rel: str) -> str:
    """The path as lowercase words: camelCase steps become boundaries."""
    return _LOWER_UPPER.sub(" ", rel).lower()


def hint_role(rel: str, kind: str | None = None) -> str | None:
    """The first role hint whose WORD is in the path (and that makes sense for the file kind), else None."""
    allowed = _ALLOWED.get(kind)
    low = _words(rel)
    return next((r for rx, r in ROLE_HINTS if rx.search(low) and (allowed is None or r in allowed)), None)


# hints only apply to file kinds they make sense for: "Profile.jpg" is a photo, not a client brief (seen on a real
# client folder); a poster in assets/Brand is a brand image whose colours can be measured
_ALLOWED = {"document": {"client_brief", "brand_colors", "branding_doc", "typography", "editing_reference"},
            "image": {"logo", "headshot", "portrait", "client_photo"},
            "raw_image": {"logo", "headshot", "portrait", "client_photo"},
            "video": {"editing_reference", "source_footage", "broll_video"},
            "audio": {"music", "sfx", "source_footage"}}


def _folder_role(parts: list[str], kind: str) -> tuple[str | None, str]:
    """(role the known data folder gives this file, the path below that folder) or (None, whole path)."""
    if len(parts) > 2 and parts[0] == "data":
        role = DATA_FOLDERS.get(parts[1].lower(), {}).get(kind)
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
        low = _words(rel)
        if kind in ("image", "raw_image") and role is None and _BRAND_IMAGE.search(low):
            role = "brand_image"
        if kind == "document" and _BROLL_WORD.search(low):
            role = "broll_license"      # SOURCES.md / licence next to the B-roll clips (not an editing reference)
    else:
        # the folder decides; a filename hint that says something else is reported (discover warns), never obeyed
        hint = hint_role(below, kind)
        hint = (_VIDEO_ROLES if kind == "video" else _DOC_ROLES if kind == "document" else {}).get(hint, hint)
        if hint and hint != folder_role and not (kind == "document" and folder_role == "broll_license"):
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
    apps = {a["name"]: a["exe"] for a in plat.find_adobe_apps()}
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
    aer = plat.aerender_path()
    return {"generated": now_iso(), "os": plat.OS_NAME, "platform": platform.platform(), "machine": platform.machine(),
            "adobe_apps": apps, "aerender": str(aer) if aer else None,
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
             and f["rel"].startswith("data/") and hint_role(f["rel"]) is None]
    if loose:
        warnings.append(f"Documents in data/ not used as editing references (no 'ref' in the path): {', '.join(loose[:8])}"
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


def run_discovery(paths: Paths) -> dict:
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
