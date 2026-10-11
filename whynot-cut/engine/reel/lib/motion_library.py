"""Licensed illustration packs for motion videos (spec §4.3).

Packs live in motion.json `library_dir` (default <engine home>/library/motion), outside client folders. Each pack folder
has pack.json {"id", "name", "license", "source", "attribution", "proof", "items": [{"id", "file", "tags"}]}. Only the
allowed licenses are usable; CC-BY needs its attribution text, `commercial` needs a proof (invoice or license id).
Anything else, or a folder without pack.json, makes the whole pack unusable. Nothing is generated or downloaded.
"""
from __future__ import annotations

import re
from pathlib import Path

from .common import ENV_DIR, read_json
from .motion_config import motion_cfg

FORBIDDEN_SVG = ("linearGradient", "radialGradient", "pattern", "mask", "filter", "clipPath", "<image", "<text")


def allowed() -> set[str]:
    return set(motion_cfg().get("licenses_allowed") or ["CC0-1.0", "MIT", "ISC", "Apache-2.0", "CC-BY-4.0", "commercial"])


def library_dir() -> Path:
    d = motion_cfg().get("library_dir")
    return Path(d).expanduser() if d else ENV_DIR / "library" / "motion"


def svg_ok(svg_text: str) -> tuple[bool, str]:
    hits = [k.strip("<") for k in FORBIDDEN_SVG if k in svg_text]
    if hits:
        return False, f"not solid fills only (uses {', '.join(hits)}): export it as PNG with alpha"
    from .motion_icons import svg_to_shapes
    try:
        n = len(svg_to_shapes(svg_text, 24))
    except Exception as e:  # noqa: BLE001
        return False, f"unreadable SVG: {e}"
    if n > 300:
        return False, f"{n} subpaths (max 300): export it as PNG with alpha"
    return True, ""


def _pack(d: Path) -> dict:
    meta = read_json(d / "pack.json")
    if not meta:
        return {"id": d.name, "name": d.name, "license": None, "attribution": "", "ok": False, "items": {},
                "problems": ["no pack.json (license manifest): the pack cannot be used"]}
    lic = str(meta.get("license") or "")
    problems = []
    if lic not in allowed():
        problems.append(f"license {lic!r} is not allowed ({', '.join(sorted(allowed()))})")
    if lic == "CC-BY-4.0" and not str(meta.get("attribution") or "").strip():
        problems.append("CC-BY-4.0 needs the attribution text to publish with the video")
    if lic == "commercial" and not str(meta.get("proof") or "").strip():
        problems.append("a commercial license needs a proof (invoice or license id)")
    items = {}
    for it in meta.get("items") or []:
        f = d / str(it.get("file", ""))
        kind = "png" if f.suffix.lower() == ".png" else "svg" if f.suffix.lower() == ".svg" else None
        if not f.is_file() or kind is None:
            problems.append(f"item {it.get('id')}: missing or unsupported file {it.get('file')!r} (PNG with alpha or SVG)")
            continue
        items[str(it.get("id"))] = {"path": f, "kind": kind, "tags": list(it.get("tags") or [])}
    return {"id": str(meta.get("id") or d.name), "name": meta.get("name", d.name), "license": lic,
            "attribution": str(meta.get("attribution") or ""), "source": meta.get("source", ""),
            "ok": not problems, "problems": problems, "items": items}


def load_packs(base: Path | None = None) -> list[dict]:
    base = Path(base) if base else library_dir()
    if not base.is_dir():
        return []
    return [_pack(d) for d in sorted(base.iterdir()) if d.is_dir() and not d.name.startswith(".")]


def resolve(ref: str, base: Path | None = None) -> dict:
    m = re.fullmatch(r"([^/]+)/([^/]+)", ref or "")
    if not m:
        raise ValueError(f"illustration {ref!r}: expected pack/item")
    pack = next((p for p in load_packs(base) if p["id"] == m.group(1)), None)
    if not pack:
        raise ValueError(f"illustration pack {m.group(1)!r} not found in {Path(base) if base else library_dir()}")
    if not pack["ok"]:
        raise ValueError(f"illustration pack {pack['id']!r} is unusable: {'; '.join(pack['problems'])}")
    it = pack["items"].get(m.group(2))
    if not it:
        raise ValueError(f"no item {m.group(2)!r} in pack {pack['id']!r} (items: {', '.join(pack['items'])})")
    if it["kind"] == "svg":
        ok, why = svg_ok(it["path"].read_text(encoding="utf-8", errors="replace"))
        if not ok:
            raise ValueError(f"illustration {ref}: {why}")
    return {"path": str(it["path"]), "kind": it["kind"], "license": pack["license"], "attribution": pack["attribution"],
            "pack": pack["id"]}
