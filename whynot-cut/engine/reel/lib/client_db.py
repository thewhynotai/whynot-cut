"""Stage 2: persistent client database (brand tokens, typography, asset manifest).

Machine-extractable facts are extracted here. Semantic documents (client-profile.md,
client-identity.json, audience-profile.md, content-guidelines.md) are authored by Claude
from the brief following references/client-intelligence.md — this module only creates
placeholders for them if absent and never invents content.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .common import (active_profile, FONT_EXT, IMAGE_EXT, RAW_IMAGE_EXT, Paths, is_junk, now_iso, read_json, run,
                     sha1_head, write_json, write_text)
from .discover import read_document

HEX = re.compile(r"#([0-9A-Fa-f]{6})\b")
from . import plat

def installed_postscript_names() -> dict:
    """PostScript name -> installed file, for every face in the OS font folders, collections and Adobe Fonts included
    (an installed copy may be renamed: Windows per-user installs, Adobe Fonts' obfuscated names). lib/fonts.py keeps
    the index and rebuilds it when a font folder changes (a font installed while a long-lived process runs is found)."""
    from . import fonts
    return fonts.postscript_names()


def hex_to_rgb(h: str) -> list[int]:
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def extract_colors(paths: Paths, inventory: dict) -> list[dict]:
    seen, out = set(), []
    for f in inventory["files"]:
        if f["kind"] != "document":
            continue
        txt = read_document(Path(f["path"]))
        for m in HEX.finditer(txt):
            h = "#" + m.group(1).upper()
            if h not in seen:
                seen.add(h)
                out.append({"hex": h, "rgb": hex_to_rgb(h), "source": f["rel"],
                            "rgb_float": [round(c / 255, 4) for c in hex_to_rgb(h)]})
    return out


def image_palette(p: Path, n: int = 6) -> list[dict]:
    """Dominant colours of an image (median cut on a small copy), most common first, with their share of the image.
    Near-identical swatches are merged. These are measurements, not the client's official brand colours."""
    from PIL import Image
    with Image.open(p) as im:
        small = im.convert("RGB")
        small.thumbnail((200, 200))
    q = small.quantize(colors=n * 2, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors() or [], reverse=True)
    total = float(sum(c for c, _ in counts)) or 1.0
    out = []
    for c, idx in counts:
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        if any(sum(abs(a - b) for a, b in zip(rgb, o["rgb"])) < 40 for o in out):
            continue
        out.append({"hex": "#%02X%02X%02X" % rgb, "rgb": list(rgb), "share": round(c / total, 3)})
        if len(out) == n:
            break
    return out


def font_info(p: Path) -> dict:
    from fontTools.ttLib import TTFont
    f = TTFont(str(p), lazy=True)
    name = f["name"]

    def nm(i):
        r = name.getName(i, 3, 1, 0x409) or name.getName(i, 1, 0, 0)
        return str(r) if r else None
    cmap = f.getBestCmap() or {}
    arabic = sum(1 for c in cmap if 0x0600 <= c <= 0x06FF)
    latin = sum(1 for c in cmap if 0x41 <= c <= 0x7A)
    pres_forms = sum(1 for c in cmap if 0xFE70 <= c <= 0xFEFF)
    weight = f["OS/2"].usWeightClass if "OS/2" in f else None
    installed = [str(d / p.name) for d in plat.font_dirs() if (d / p.name).exists()]
    if not installed and nm(6):
        hit = installed_postscript_names().get(nm(6))
        installed = [hit] if hit else []
    return {"file": str(p), "family": nm(1), "subfamily": nm(2), "full_name": nm(4),
            "postscript_name": nm(6), "typographic_family": nm(16), "typographic_subfamily": nm(17),
            "weight_class": weight, "arabic_glyphs": arabic, "latin_glyphs": latin,
            "arabic_presentation_forms": pres_forms, "has_gsub": "GSUB" in f,
            "supports_arabic": arabic > 30, "supports_latin": latin >= 52,
            "installed_locations": installed, "installed": bool(installed)}


def image_info(p: Path, deriv_dir: Path) -> dict:
    from PIL import Image, ImageOps
    info = {"file": str(p), "name": p.name, "format": p.suffix.lower().lstrip("."),
            "size_bytes": p.stat().st_size, "fingerprint": sha1_head(p)}
    src = p
    if p.suffix.lower() in RAW_IMAGE_EXT:
        # camera RAW: make a high-quality JPEG derivative (keeps the original untouched)
        deriv_dir.mkdir(parents=True, exist_ok=True)
        jpg = deriv_dir / (p.stem + "_from_raw.jpg")
        how = raw_to_jpeg(p, jpg) if not jpg.exists() else "cached"
        if not jpg.exists():
            info.update(skipped=True, raw_note=f"camera RAW not converted ({how}); export a JPEG from Lightroom/Camera "
                                               f"Raw into assets/ (the optional `rawpy` reader is not part of the "
                                               f"engine runtime)")
            return info
        info["raw_derivative"] = str(jpg)
        info["raw_note"] = "Default camera-RAW render; re-develop in Camera Raw for final use."
        src = jpg
    with Image.open(src) as f:                       # closed at once (MI-9): exif_transpose returns a loaded copy
        info["exif_orientation"] = (f.getexif() or {}).get(0x0112, 1)
        im = ImageOps.exif_transpose(f)
    w, h = im.size
    info.update({"width": w, "height": h, "mode": im.mode,
                 "orientation": "portrait" if h > w else "landscape" if w > h else "square",
                 "megapixels": round(w * h / 1e6, 1)})
    alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
    info["has_alpha_channel"] = alpha
    if alpha:
        a = im.convert("RGBA").getchannel("A")
        lo, hi = a.getextrema()
        info["alpha_used"] = lo < 250
    else:
        info["alpha_used"] = False
    # display derivative: orientation baked, max 1920 long edge... but keep >= 2x for punch-ins
    deriv_dir.mkdir(parents=True, exist_ok=True)
    disp = deriv_dir / (p.stem + ("_alpha.png" if info["alpha_used"] else "_display.jpg"))
    if not disp.exists():
        d = im.copy()
        d.thumbnail((2160, 3840))
        if info["alpha_used"]:
            d.save(disp)
        else:
            d.convert("RGB").save(disp, quality=92)
    info["display_derivative"] = str(disp)
    info["use_for_print_res"] = w >= 2160 or h >= 3840
    return info


def raw_to_jpeg(src: Path, dst: Path) -> str:
    """macOS sips, else rawpy if installed (optional on Windows). Returns how it was done or why not."""
    import shutil as _sh
    if _sh.which("sips"):
        run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "92", str(src), "--out", str(dst)], check=False)
        return "sips"
    try:
        import rawpy  # type: ignore
        from PIL import Image
        with rawpy.imread(str(src)) as r:
            Image.fromarray(r.postprocess(use_camera_wb=True)).save(dst, quality=92)
        return "rawpy"
    except ImportError:
        return "no RAW converter on this OS"
    except Exception as e:  # noqa: BLE001
        return f"rawpy failed: {type(e).__name__}"


def build(paths: Paths, inventory: dict) -> dict:
    db = paths.client_db
    for sub in ("profile", "branding", "assets/derivatives", "templates"):
        (db / sub).mkdir(parents=True, exist_ok=True)

    # ---- colors
    colors = extract_colors(paths, [inventory][0])
    overrides = read_json(db / "branding/brand-roles.json", {})  # Claude/user-assigned roles
    palettes = []
    if not colors:   # no HEX codes in any document: measure candidates from brand images (posters, covers, logos)
        for f in inventory["files"]:
            if f["kind"] == "image" and f["role"] in ("brand_image", "logo"):
                try:
                    palettes.append({"source": f["rel"], "colors": image_palette(Path(f["path"]))})
                except Exception:  # noqa: BLE001
                    continue
    tokens = {"generated": now_iso(), "official_colors": colors,
              "measured_palettes": palettes,
              "roles": overrides.get("roles", {}),
              "derived": overrides.get("derived", {}),
              "notes": ["Only 'official_colors' come from client files. 'measured_palettes' are colours MEASURED from "
                        "brand images (candidates: a role taken from one must cite that image in brand-roles.json). "
                        "'derived' values are working tints computed for legibility and are NOT official brand colors."]}
    write_json(db / "branding/brand-tokens.json", tokens)

    # ---- fonts
    fonts = [font_info(Path(f["path"])) for f in inventory["files"] if f["kind"] == "font"]
    fams = {}
    for fi in fonts:
        fams.setdefault(fi["typographic_family"] or fi["family"], []).append(fi)
    typ_over = read_json(db / "branding/typography-roles.json", {})
    typography = {"generated": now_iso(), "families": {
        k: {"weights": sorted([{"style": f["typographic_subfamily"] or f["subfamily"],
                                 "postscript_name": f["postscript_name"], "weight_class": f["weight_class"],
                                 "file": f["file"], "installed": f["installed"]} for f in v],
                                key=lambda x: x["weight_class"] or 0),
            "supports_arabic": all(f["supports_arabic"] for f in v),
            "supports_latin": all(f["supports_latin"] for f in v)} for k, v in fams.items()},
        "roles": typ_over.get("roles", {}),
        "missing_or_uninstalled": [f["file"] for f in fonts if not f["installed"]],
        "notes": typ_over.get("notes", [])}
    write_json(db / "branding/typography.json", typography)

    # ---- images
    imgs = [f for f in inventory["files"] if f["kind"] in ("image", "raw_image") and f["rel"].startswith("assets")]
    cls = read_json(db / "assets/asset-classification.json", {}).get("assets", {})
    assets, skipped_raw = [], []
    for f in imgs:
        info = image_info(Path(f["path"]), db / "assets/derivatives")
        info["rel"] = f["rel"]
        if info.get("skipped"):
            skipped_raw.append(f"{f['rel']}: {info['raw_note']}")
            continue
        c = cls.get(f["rel"], {})
        info["category"] = c.get("category") or ("logo" if f["role"] == "logo" else "unreviewed")
        info["description"] = c.get("description", "")
        info["use_cases"] = c.get("use_cases", [])
        info["approved"] = c.get("approved", True)  # supplied by client in assets/ = approved source
        assets.append(info)
    manifest = {"generated": now_iso(), "client": active_profile(paths.root) or paths.root.name, "count": len(assets),
                "assets": assets, "policy": [
                    "Originals referenced in place; derivatives live in client_database/assets/derivatives.",
                    "No AI-generated likeness of the client without explicit approval.",
                    "Do not retouch or alter the client's appearance."]}
    write_json(db / "asset-manifest.json", manifest)
    write_json(db / "assets/asset-manifest.json", manifest)

    # ---- placeholders for Claude-authored semantic docs (never overwrite)
    for rel, body in {
        "profile/client-profile.md": "# Client Profile\n\nTO BE AUTHORED from the client brief (see references/client-intelligence.md).\n",
        "profile/client-identity.json": None, "profile/audience-profile.md": "# Audience Profile\n\nTO BE AUTHORED.\n",
        "profile/content-guidelines.md": "# Content Guidelines\n\nTO BE AUTHORED.\n"}.items():
        p = db / rel
        if not p.exists():
            if body is None:
                write_json(p, {"status": "TO_BE_AUTHORED"})
            else:
                write_text(p, body)
    issues = []
    if not colors and overrides.get("roles"):
        issues.append("No HEX codes in documents: using the colour roles assigned in branding/brand-roles.json "
                      "(measured from brand images; ask the client to confirm HEX codes).")
    elif not colors and palettes:
        issues.append(f"No HEX codes in documents; candidate colours measured from {', '.join(x['source'] for x in palettes)} "
                      f"(brand-tokens.json measured_palettes): assign primary/accent roles in branding/brand-roles.json, "
                      f"citing the image, or ask the client for HEX codes.")
    elif not colors:
        issues.append("No HEX colors found in client documents.")
    if typography["missing_or_uninstalled"]:
        issues.append(f"Fonts not installed ({plat.font_install_hint()}): {typography['missing_or_uninstalled']}")
    issues += [f"Camera RAW skipped: {x}" for x in skipped_raw]
    if not any(a["category"] == "logo" for a in assets):
        issues.append("No logo identified.")
    unrev = [a["rel"] for a in assets if a["category"] == "unreviewed"]
    if unrev:
        issues.append(f"{len(unrev)} images not yet visually classified (write assets/asset-classification.json).")
    status = {"generated": now_iso(), "colors": len(colors), "fonts": len(fonts), "images": len(assets),
              "issues": issues,
              "ready": bool(colors) and not typography["missing_or_uninstalled"]
                       and any(a["category"] == "logo" for a in assets)}
    write_json(db / "client-database-status.json", status)
    return status


# --------------------------------------------------------------------------- portable paths (3.0 Phase 4 T4.5)
# The files of output/client_database/ that carry paths, and where (a "*" walks every dict value or list item). 3.0
# stores them relative to the client root (POSIX); 2.x and older 3.0 files hold absolute paths, maybe of the folder
# the client was copied from. Every reader goes through load(), which hands back paths it can open; nothing else
# reads these files (tests/test_t45_guard.py).
PATH_FIELDS: dict[str, tuple] = {
    "asset-manifest.json": (("assets", "*", "file"), ("assets", "*", "display_derivative"),
                            ("assets", "*", "raw_derivative")),
    "branding/typography.json": (("families", "*", "weights", "*", "file"), ("missing_or_uninstalled", "*")),
    "reference_analysis/cache.json": (("*", "video"), ("*", "contact_sheets", "*"), ("*", "cut_frames", "*")),
    "reference_analysis/reference-measurements.json": (("references", "*", "video"),
                                                       ("references", "*", "contact_sheets", "*")),
    "reference_analysis/*/measurements.json": (("video",), ("contact_sheets", "*"), ("cut_frames", "*")),
}
PATH_FIELDS["assets/asset-manifest.json"] = PATH_FIELDS["asset-manifest.json"]
ANCHORS = ("assets", "data", "output")            # the client root's own folders: where a copied path's tail starts


def path_fields(rel: str) -> tuple:
    rel = str(rel).replace("\\", "/")
    if rel in PATH_FIELDS:
        return PATH_FIELDS[rel]
    import fnmatch
    parts = rel.split("/")
    for pat, spec in PATH_FIELDS.items():
        pp = pat.split("/")
        if "*" in pat and len(pp) == len(parts) and all(fnmatch.fnmatchcase(a, b) for a, b in zip(parts, pp)):
            return spec
    return ()


def is_relative(v) -> bool:
    """A root-relative value: not absolute in Windows or POSIX form, no drive, no UNC, never climbing out (..)."""
    from pathlib import PurePosixPath, PureWindowsPath
    if not isinstance(v, str) or not v.strip():
        return False
    w = PureWindowsPath(v)
    if w.drive or w.root or PurePosixPath(v).is_absolute():
        return False
    return ".." not in v.replace("\\", "/").split("/")


def _norm(v: str, sep: str, fold: bool) -> str:
    s = v.replace("\\", sep).replace("/", sep).rstrip(sep)
    return s.casefold() if fold else s


def inside_root(v: str, root: str, fold: bool | None = None, sep: str | None = None) -> bool:
    """Is absolute `v` the client root or under it? Case folded where the file system folds it; when the strings
    differ (a junction, macOS /var vs /private/var) the real paths are compared too, on this computer's own form."""
    import os
    from . import client_move_paths as cmp
    fold = cmp.FOLD_CASE if fold is None else fold
    sep = os.sep if sep is None else sep
    for a, b in ((v, root), (cmp.real(v), cmp.real(root))):
        a, b = _norm(a, sep, fold), _norm(b, sep, fold)
        if a == b or a.startswith(b + sep):
            return True
    return False


def anchor_tails(p) -> list[str]:
    """The POSIX tails of an absolute path from each of its anchor folders (assets | data | output), earliest first:
    D:/data/old/C/assets/a.png -> [data/old/C/assets/a.png, assets/a.png]."""
    parts = list(p.parts[1:]) if p.anchor else list(p.parts)
    return ["/".join(parts[i:]) for i, s in enumerate(parts) if s.lower() in ANCHORS and i < len(parts) - 1]


def resolve(root, v):
    """A stored value -> a path this computer can open: relative -> under the root; absolute inside the root -> kept;
    absolute elsewhere -> the same file under this root when its tail from an anchor folder exists here (a client
    copied or moved by hand), else kept as it is (never invented)."""
    from pathlib import Path, PurePosixPath, PureWindowsPath
    if not isinstance(v, str) or not v:
        return v
    root = Path(root)
    if is_relative(v):
        return str(root.joinpath(*PurePosixPath(v.replace("\\", "/")).parts))
    win = bool(PureWindowsPath(v).drive) or "\\" in v
    if not win and not PurePosixPath(v).is_absolute():
        return v                                   # "../x" and the like: not a path we resolve
    if inside_root(v, str(root)):
        return v
    for tail in anchor_tails(PureWindowsPath(v) if win else PurePosixPath(v)):
        cand = root.joinpath(*tail.split("/"))
        if cand.exists():
            return str(cand)
    return v


def _walk(node, spec: tuple, fn):
    if not spec:
        return fn(node)
    key, rest = spec[0], spec[1:]
    if key == "*":
        if isinstance(node, list):
            for i, x in enumerate(node):
                node[i] = _walk(x, rest, fn)
        elif isinstance(node, dict):
            for k in list(node):
                node[k] = _walk(node[k], rest, fn)
    elif isinstance(node, dict) and key in node:
        node[key] = _walk(node[key], rest, fn)
    return node


def load(paths, rel: str, default=None):
    """A client-database file (`rel` under output/client_database/) with every path field resolved for this computer
    (`resolve`). `paths` is a Paths (or EpisodePaths, or anything with `client_db`), or the client_database folder
    itself; without a `root` the client root is two levels above client_database. Missing -> a copy of `default`;
    damaged -> errors.FileFormatError like read_json. Never writes."""
    import copy
    db = Path(paths) if isinstance(paths, (str, Path)) else Path(paths.client_db)
    root = getattr(paths, "root", None) if not isinstance(paths, (str, Path)) else None
    root = Path(root) if root else db.parent.parent
    doc = read_json(db / rel)
    if doc is None:
        return copy.deepcopy(default)
    for spec in path_fields(rel):
        _walk(doc, spec, lambda v: resolve(root, v))
    return doc
