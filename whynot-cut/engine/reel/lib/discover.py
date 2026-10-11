"""Stage 1: recursive input discovery, classification, environment audit."""
from __future__ import annotations

import platform
import re
import shutil
from pathlib import Path

from .common import (AUDIO_EXT, DOC_EXT, FONT_EXT, IMAGE_EXT, RAW_IMAGE_EXT, SUB_EXT, VIDEO_EXT,
                     Paths, ENV_DIR, ffmpeg_exe, is_junk, now_iso, run, sha1_head, write_json, write_text)

ROLE_HINTS = [  # (substring in lowercase relative path, role)
    ("brief", "client_brief"), ("profile", "client_brief"), ("about", "client_brief"), ("bio", "client_brief"),
    ("color", "brand_colors"), ("colour", "brand_colors"), ("palat", "brand_colors"), ("palet", "brand_colors"),
    ("brand", "branding_doc"), ("font", "typography"), ("typo", "typography"),
    ("logo", "logo"), ("headshot", "headshot"), ("portrait", "portrait"), ("photo", "client_photo"),
    ("broll", "broll_video"), ("b-roll", "broll_video"), ("b_roll", "broll_video"), ("stock", "broll_video"),
    ("ref", "editing_reference"), ("raw", "source_footage"), ("footage", "source_footage"),
    ("music", "music"), ("sfx", "sfx"), ("sound", "sfx"),
]


def classify(p: Path, rel: str) -> dict:
    ext = p.suffix.lower()
    kind = ("video" if ext in VIDEO_EXT else "audio" if ext in AUDIO_EXT else
            "image" if ext in IMAGE_EXT else "raw_image" if ext in RAW_IMAGE_EXT else
            "font" if ext in FONT_EXT else "subtitle" if ext in SUB_EXT else
            "document" if ext in DOC_EXT else "other")
    low = rel.lower()
    # hints only apply to file kinds they make sense for: "Profile.jpg" is a photo, not a client brief (seen on a
    # real client folder); a poster in assets/Brand is a brand image whose colours can be measured
    allowed = {"document": {"client_brief", "brand_colors", "branding_doc", "typography", "editing_reference"},
               "image": {"logo", "headshot", "portrait", "client_photo"},
               "raw_image": {"logo", "headshot", "portrait", "client_photo"},
               "video": {"editing_reference", "source_footage", "broll_video"},
               "audio": {"music", "sfx", "source_footage"}}.get(kind)
    role = next((r for k, r in ROLE_HINTS if k in low and (allowed is None or r in allowed)), None)
    if kind in ("image", "raw_image") and role is None and ("brand" in low or "colo" in low or "palet" in low):
        role = "brand_image"
    if kind == "document" and any(k in low for k in ("broll", "b-roll", "b_roll", "stock")):
        role = "broll_license"      # SOURCES.md / licence next to the B-roll clips (not an editing reference)
    top = rel.split("/")[0]
    parts = rel.split("/")
    if top == "data" and len(parts) > 2 and parts[1].lower() == "episodes" and kind in ("video", "document"):
        # finished podcast episodes are cut into reels (podcast mode); never treated as a clip to edit whole
        return {"path": str(p), "rel": rel, "kind": kind, "ext": ext,
                "role": "episode" if kind == "video" else "episode_sheet", "size_bytes": p.stat().st_size}
    if kind == "video" and top == "data":
        role = "editing_reference_video" if role == "editing_reference" else (role or "source_footage")
    if kind == "document" and top == "data" and role != "broll_license":
        # only a document whose path says it is a reference (data/References/...) is one; any other loose document in
        # data/ (notes, a music.json, a stray export) stays unclassified instead of silently steering the edit style
        role = "editing_reference_doc" if role == "editing_reference" else role
    if kind == "font":
        role = "brand_font"
    if kind == "subtitle":
        role = "existing_transcript"
    if kind in ("image", "raw_image") and top == "assets" and role is None:
        role = "client_image"
    return {"path": str(p), "rel": rel, "kind": kind, "ext": ext, "role": role or "unclassified",
            "size_bytes": p.stat().st_size}


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
            "models_dir": str(ENV_DIR / "models")}


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
    if len(by_role.get("client_brief", [])) > 1:
        warnings.append("Multiple client brief documents — check for conflicts.")
    loose = [f["rel"] for f in files if f["role"] == "unclassified" and f["kind"] == "document"
             and f["rel"].startswith("data/") and not any(k in f["rel"].lower() for k, _ in ROLE_HINTS)]
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
