"""JSON Schemas of the files Claude authors (3.0 T2.3, engine MI-11) and `reel validate`.

whynot-cut/schemas/<name>.schema.json (draft 2020-12), one per authored file:
    edit-decisions          01_analysis/edit-decisions.json            (`reel plan` compiles it)
    reels-plan              01_analysis/reels-plan.json of an episode  (`reel reels-plan`)
    motion-script           01_analysis/motion-script.json             (`reel motion-plan`)
    publish                 publish/publish.json of an episode         (`reel publish-check`)
    publish-reel            publish/reels/<REEL>.json                  ($defs/reel of publish.schema.json)
    transcript-corrections  02_transcription/transcript-corrections.json (`reel transcript-correct`)
    asset-needs             the optional `asset_needs` array of edit-decisions / motion-script (Phase 5)
plus one file the engine writes for the panel to read (never authored by hand):
    needs-you               output/needs-you.json                      (`reel needs-you --write`, T4.7)
Each schema carries its version twice: `$id` ends in ":<n>" and the optional `schema_version` property of a file is
`{"const": n}`. The schemas describe structure (types, required fields, the enums the engine enforces); the compilers
keep checking meaning (evidence in the transcript, times inside the media, templates of the profile).

Validation reuses the command contract's stdlib validator (engine/reel/contract/validator.py, owned by the Adobe track:
imported, never edited), so the schemas use only its keyword subset (`check_schema` proves it). That validator resolves
`$ref` only inside one document (or the contract folder), so `bundled()` copies the $defs of a referenced schema file
into the referencing one ("asset-needs.schema.json#/$defs/list" -> "#/$defs/asset-needs.list").
"""
from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

from .common import PLUGIN_DIR

SCHEMA_DIR = PLUGIN_DIR / "schemas"
# kind -> (schema file name without .schema.json, JSON pointer of the kind's schema inside it)
KINDS: dict[str, tuple[str, str]] = {
    "edit-decisions": ("edit-decisions", ""),
    "reels-plan": ("reels-plan", ""),
    "motion-script": ("motion-script", ""),
    "publish": ("publish", ""),
    "publish-reel": ("publish", "/$defs/reel"),
    "transcript-corrections": ("transcript-corrections", ""),
    "asset-needs": ("asset-needs", ""),
    "needs-you": ("needs-you", ""),
}
_FILE_REF = re.compile(r"([a-z0-9-]+)\.schema\.json")
_DEFS = "/$defs/"


def kind_name(kind: str | None) -> str | None:
    """'asset_needs' / 'Edit-Decisions' -> the KINDS key; None when unknown."""
    k = str(kind or "").strip().lower().replace("_", "-")
    return k if k in KINDS else None


def kind_for(path) -> str | None:
    """The kind a file name says: edit-decisions.json, reels-plan.json, motion-script.json, publish.json,
    transcript-corrections.json, asset-needs.json (or asset_needs.json); publish/reels/<REEL>.json -> publish-reel."""
    p = Path(path)
    if p.suffix.lower() != ".json":
        return None
    if p.parent.name.lower() == "reels" and p.parent.parent.name.lower() == "publish":
        return "publish-reel"
    k = kind_name(p.stem)
    return k if k != "publish-reel" else None


@lru_cache(maxsize=None)
def _raw(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _local(node, prefix: str, origin: str):
    """A $defs entry copied from another schema file: its "#/$defs/x" refs -> "#/$defs/<prefix>.x"."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                if not v.startswith("#" + _DEFS):
                    raise ValueError(f"{origin}.schema.json: $ref {v!r} cannot be bundled (only #/$defs/... refs)")
                out[k] = f"#{_DEFS}{prefix}.{v[len(_DEFS) + 1:]}"
            else:
                out[k] = _local(v, prefix, origin)
        return out
    if isinstance(node, list):
        return [_local(v, prefix, origin) for v in node]
    return node


@lru_cache(maxsize=None)
def bundled(name: str) -> dict:
    """The schema file `name` with every "<other>.schema.json#/$defs/x" ref made local. Read-only (cached)."""
    doc = copy.deepcopy(_raw(name))
    defs = doc.setdefault("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and not ref.startswith("#"):
                file_part, _, ptr = ref.partition("#")
                m = _FILE_REF.fullmatch(file_part)
                if not m or not ptr.startswith(_DEFS):
                    raise ValueError(f"{name}.schema.json: $ref {ref!r} must look like <name>.schema.json#/$defs/<def>")
                other = m.group(1)
                for k, v in (_raw(other).get("$defs") or {}).items():
                    defs.setdefault(f"{other}.{k}", _local(v, other, other))
                node["$ref"] = f"#{_DEFS}{other}.{ptr[len(_DEFS):]}"
            for v in list(node.values()):
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(doc)
    return doc


def schema_for(kind: str) -> dict:
    """The (bundled) schema a kind's files are validated against."""
    name, ptr = KINDS[kind]
    doc = bundled(name)
    return doc if not ptr else {"$defs": doc["$defs"], "$ref": "#" + ptr}


def schema_version(kind: str) -> int | None:
    name, _ = KINDS[kind]
    return ((_raw(name).get("properties") or {}).get("schema_version") or {}).get("const")


def validate(doc, kind: str) -> list[dict]:
    """[{path, msg}] (empty = valid). path is a JSON pointer ("" = the whole document)."""
    from contract import validate as contract_validate
    errs = []
    for e in contract_validate(doc, schema_for(kind)):
        path, _, msg = e.partition(": ")
        errs.append({"path": "" if path == "/" else path, "msg": msg})
    return errs


def validate_file(path, kind: str | None = None) -> dict:
    """`reel validate <file> [--kind K]`: {ok, kind, file, schema, schema_version, errors[{path, msg}]} (+ error/how
    when the file cannot be read or its kind is unknown)."""
    from .common import read_json
    from .errors import FileFormatError
    f = Path(path).expanduser()
    k = kind_name(kind) if kind else kind_for(f)
    res = {"ok": False, "kind": k, "file": str(f), "errors": []}
    if kind and not k:
        return dict(res, kind=kind, error=f"unknown kind {kind!r}", how=f"--kind is one of {', '.join(KINDS)}")
    if not k:
        return dict(res, error=f"cannot tell what {f.name} is from its name",
                    how=f"name the kind: reel validate {f.name} --kind <{'|'.join(KINDS)}>")
    res.update(schema=str(SCHEMA_DIR / f"{KINDS[k][0]}.schema.json"), schema_version=schema_version(k))
    if not f.is_file():
        return dict(res, error=f"not found: {f}", how="check the path (relative paths start at the current folder)")
    try:
        doc = read_json(f)
    except FileFormatError as e:
        return dict(res, errors=[{"path": "", "msg": f"not valid JSON: {e.reason} (line {e.line}, column {e.column})"}])
    errs = validate(doc, k)
    return dict(res, ok=not errs, errors=errs)
