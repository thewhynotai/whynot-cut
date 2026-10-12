"""A small JSON Schema validator for the command contract (draft 2020-12 SUBSET, standard library only).

The engine runtime is hash-locked, so `jsonschema` is not a dependency: this module validates the contract's own
schemas and nothing else. Supported keywords:

    $ref ("#/..." in the same file, "<name>.schema.json#/..." inside the contract folder), $defs, type (string or list;
    "integer" and "number" exclude booleans), properties, required, additionalProperties (bool or schema), items,
    minItems, maxItems, enum, const, minimum, maximum, minLength, maxLength, pattern (re.search, unanchored), anyOf,
    oneOf, format ("date-time" only: RFC 3339 with a time zone)

format "date-time" differs from ajv-formats 3.0.1 (the TypeScript side of the contract tests) at the edges, on purpose:
ajv also accepts a space separator (instead of "T") and the offsets "+0300" and "+03" (no colon / no minutes);
this validator wants RFC 3339 strictly (T or t, "Z" or "+hh:mm"). In the other direction Python accepts a leap second
(":60") at any time of day, ajv only at 23:59:60. Values a program writes itself, `expires_at` from Python's isoformat()
or JavaScript's toISOString(), pass both.

plus the annotation keywords $schema, $id, title, description, examples, default. Any other keyword in a contract schema
is an error (`check_schema`): a schema author must not rely on something this validator would silently ignore.

API
    load(name) -> dict                       "request", "ping", "ping.schema.json" or "protocol"; KeyError if unknown
    validate(instance, schema_or_name) -> list[str]
                                             schema_or_name: a schema (dict / bool) or "<name>" or "<name>#/$defs/data";
                                             errors read "<JSON pointer>: <message>"; an empty list means valid
    check_schema(schema) -> list[str]        problems with a schema (unsupported keyword, malformed value, bad $ref)
    validate_request(req) -> list[str]       the request envelope, then `data` against the action's $defs/data
    validate_result(res) -> list[str]        the result envelope, then `readback` against the action's $defs/readback
                                             (when ok) or $defs/readback_failure (when not ok and the action defines one)
"""
from __future__ import annotations

import calendar
import json
import math
import re
from functools import lru_cache
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent

ANNOTATIONS = frozenset({"$schema", "$id", "title", "description", "examples", "default"})
KEYWORDS = frozenset({"$ref", "$defs", "type", "properties", "required", "additionalProperties", "items", "minItems",
                      "maxItems", "enum", "const", "minimum", "maximum", "minLength", "maxLength", "pattern", "anyOf",
                      "oneOf", "format"})
TYPES = ("null", "boolean", "object", "array", "string", "number", "integer")
FORMATS = ("date-time",)
MAX_DEPTH = 64                      # $ref chains / schema nesting: a loop is reported, never a RecursionError
# `$` in Python also matches before a trailing newline (ECMA-262 and ajv do not), and the digit shorthand matches any Unicode digit:
# the module's own patterns use fullmatch and [0-9]
_NAME = re.compile(r"[A-Za-z0-9_]+")
_REF_FILE = re.compile(r"([A-Za-z0-9_]+)\.schema\.json")
_DATE_TIME = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?"
                        r"(?:[Zz]|[+-]([0-9]{2}):([0-9]{2}))")


# ------------------------------------------------------------------------------------------------ loading
@lru_cache(maxsize=None)
def _read(filename: str) -> dict:
    try:
        return json.loads((CONTRACT_DIR / filename).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise KeyError(filename) from None


def _filename(name: str) -> str:
    """"ping" | "ping.schema.json" | "protocol" -> the file inside the contract folder (no path separators, ever)."""
    if not isinstance(name, str):
        raise KeyError(name)
    if name == "protocol" or name == "protocol.json":
        return "protocol.json"
    m = _REF_FILE.fullmatch(name)
    base = m.group(1) if m else name
    if not _NAME.fullmatch(base):
        raise KeyError(name)
    return base + ".schema.json"


def load(name: str) -> dict:
    """The parsed schema (or protocol.json) called `name`. Treat it as read-only: it is cached."""
    return _read(_filename(name))


def _pointer(doc, ptr: str):
    """Resolve a JSON pointer ("" or "/a/b") inside `doc`; KeyError when it leads nowhere."""
    if ptr == "":
        return doc
    if not ptr.startswith("/"):
        raise KeyError(ptr)
    cur = doc
    for raw in ptr[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise KeyError(ptr)
    return cur


def _resolve(ref: str, root, fname):
    """-> (subschema, root of its file, its file name). `fname` is the file `root` came from (None: an inline schema)."""
    if not isinstance(ref, str):
        raise KeyError(ref)
    file_part, _, ptr = ref.partition("#")
    if file_part == "":
        return _pointer(root, ptr), root, fname
    m = _REF_FILE.fullmatch(file_part)
    if not m:                                   # URLs, paths, parent folders: nothing outside the contract folder
        raise KeyError(ref)
    other = load(file_part)
    return _pointer(other, ptr), other, file_part


def _split_name(spec: str):
    file_part, _, ptr = spec.partition("#")
    doc = load(file_part)
    return _pointer(doc, ptr), doc, _filename(file_part)


# ------------------------------------------------------------------------------------------------ values
def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and not math.isfinite(v))


def _type_ok(v, t: str) -> bool:
    if t == "null":
        return v is None
    if t == "boolean":
        return isinstance(v, bool)
    if t == "object":
        return isinstance(v, dict)
    if t == "array":
        return isinstance(v, list)
    if t == "string":
        return isinstance(v, str)
    if t == "number":
        return _is_number(v)
    if t == "integer":
        return _is_number(v) and (isinstance(v, int) or v.is_integer())
    return False


def _type_name(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number" if math.isfinite(v) else "non-finite number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def _equal(a, b) -> bool:
    """JSON equality: true != 1, 1 == 1.0, deep for arrays and objects."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_number(a) and _is_number(b):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, dict)) or isinstance(b, (list, dict)):
        return False
    return a == b


@lru_cache(maxsize=None)
def _pattern(pat: str):
    """Compile a JSON Schema `pattern` with ECMA-262 end-of-input semantics: an unescaped `$` outside a character class
    means the very end of the string (Python's `$` would also match before a final newline). Other dialect differences
    (the digit shorthand matching non-ASCII digits) are not translated: write [0-9] in contract patterns."""
    out, i, in_class = [], 0, False
    while i < len(pat):
        c = pat[i]
        if c == "\\" and i + 1 < len(pat):
            out.append(pat[i:i + 2])
            i += 2
            continue
        if in_class:
            in_class = c != "]"
        elif c == "[":
            in_class = True
        elif c == "$":
            out.append(r"\Z")
            i += 1
            continue
        out.append(c)
        i += 1
    return re.compile("".join(out))


def _date_time_ok(s: str) -> bool:
    m = _DATE_TIME.fullmatch(s)
    if not m:
        return False
    y, mo, d, h, mi, sec = (int(m.group(i)) for i in range(1, 7))
    if not (1 <= mo <= 12) or not (1 <= d <= calendar.monthrange(y, mo)[1]):
        return False
    if h > 23 or mi > 59 or sec > 60:           # 60: a leap second
        return False
    if m.group(7) is not None and (int(m.group(7)) > 23 or int(m.group(8)) > 59):
        return False
    return True


def _where(path: str) -> str:
    return path or "/"


def _quote_list(names) -> str:
    return " or ".join(names)


# ------------------------------------------------------------------------------------------------ validation
def _check(inst, schema, path: str, root, fname, depth: int, out: list) -> None:
    if depth > MAX_DEPTH:
        out.append(f"{_where(path)}: schema nesting or $ref chain too deep (a $ref loop?)")
        return
    if schema is True:
        return
    if schema is False:
        out.append(f"{_where(path)}: no value is allowed here")
        return
    if not isinstance(schema, dict):
        out.append(f"{_where(path)}: malformed schema ({_type_name(schema)})")
        return
    if "$ref" in schema:
        try:
            sub, sub_root, sub_file = _resolve(schema["$ref"], root, fname)
        except KeyError:
            out.append(f"{_where(path)}: cannot resolve $ref {schema['$ref']!r}")
        else:
            _check(inst, sub, path, sub_root, sub_file, depth + 1, out)
    t = schema.get("type")
    if t is not None:
        names = [t] if isinstance(t, str) else list(t)
        if not any(_type_ok(inst, n) for n in names):
            out.append(f"{_where(path)}: expected {_quote_list(names)}, got {_type_name(inst)}")
    if "enum" in schema and not any(_equal(inst, e) for e in schema["enum"]):
        out.append(f"{_where(path)}: {json.dumps(inst, ensure_ascii=True)[:80]} is not one of "
                   f"{json.dumps(schema['enum'], ensure_ascii=True)[:120]}")
    if "const" in schema and not _equal(inst, schema["const"]):
        out.append(f"{_where(path)}: must be {json.dumps(schema['const'], ensure_ascii=True)[:80]}, "
                   f"got {json.dumps(inst, ensure_ascii=True)[:80]}")
    if _is_number(inst):
        if "minimum" in schema and inst < schema["minimum"]:
            out.append(f"{_where(path)}: {inst} is below the minimum {schema['minimum']}")
        if "maximum" in schema and inst > schema["maximum"]:
            out.append(f"{_where(path)}: {inst} is above the maximum {schema['maximum']}")
    if isinstance(inst, str):
        if "minLength" in schema and len(inst) < schema["minLength"]:
            out.append(f"{_where(path)}: string must have at least {schema['minLength']} characters, has {len(inst)}")
        if "maxLength" in schema and len(inst) > schema["maxLength"]:
            out.append(f"{_where(path)}: string must have at most {schema['maxLength']} characters, has {len(inst)}")
        if "pattern" in schema and not _pattern(schema["pattern"]).search(inst):
            out.append(f"{_where(path)}: {inst[:60]!r} does not match the pattern {schema['pattern']}")
        if schema.get("format") == "date-time" and not _date_time_ok(inst):
            out.append(f"{_where(path)}: {inst[:60]!r} is not an RFC 3339 date-time with a time zone (Z or +hh:mm)")
    if isinstance(inst, list):
        if "minItems" in schema and len(inst) < schema["minItems"]:
            out.append(f"{_where(path)}: array must have at least {schema['minItems']} items, has {len(inst)}")
        if "maxItems" in schema and len(inst) > schema["maxItems"]:
            out.append(f"{_where(path)}: array must have at most {schema['maxItems']} items, has {len(inst)}")
        if "items" in schema:
            for i, item in enumerate(inst):
                _check(item, schema["items"], f"{path}/{i}", root, fname, depth + 1, out)
    if isinstance(inst, dict):
        props = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in inst:
                out.append(f"{_where(path)}: required property {name!r} is missing")
        for name, sub in props.items():
            if name in inst:
                _check(inst[name], sub, f"{path}/{_esc(name)}", root, fname, depth + 1, out)
        if "additionalProperties" in schema:
            extra = schema["additionalProperties"]
            for name in inst:
                if name in props:
                    continue
                if extra is False:
                    out.append(f"{path}/{_esc(name)}: property {name!r} is not allowed here")
                elif extra is not True:
                    _check(inst[name], extra, f"{path}/{_esc(name)}", root, fname, depth + 1, out)
    if "anyOf" in schema:
        branches = []
        for i, sub in enumerate(schema["anyOf"]):
            errs: list = []
            _check(inst, sub, path, root, fname, depth + 1, errs)
            if not errs:
                branches = None
                break
            branches.append(f"[{i}] " + "; ".join(errs[:3]))
        if branches is not None:
            out.append(f"{_where(path)}: does not match any anyOf alternative: " + " | ".join(branches))
    if "oneOf" in schema:
        matched, branches = [], []
        for i, sub in enumerate(schema["oneOf"]):
            errs = []
            _check(inst, sub, path, root, fname, depth + 1, errs)
            if not errs:
                matched.append(i)
            else:
                branches.append(f"[{i}] " + "; ".join(errs[:3]))
        if len(matched) != 1:
            out.append(f"{_where(path)}: must match exactly one oneOf alternative, matches {len(matched)}"
                       + ("" if matched else ": " + " | ".join(branches)))


def _esc(name: str) -> str:
    return str(name).replace("~", "~0").replace("/", "~1")


def validate(instance, schema_or_name) -> list[str]:
    """Errors (empty = valid). `schema_or_name`: a schema, or "request" / "ping#/$defs/data" / "x.schema.json#/$defs/y"."""
    if isinstance(schema_or_name, str):
        schema, root, fname = _split_name(schema_or_name)
    else:
        schema, root, fname = schema_or_name, schema_or_name, None
    out: list = []
    _check(instance, schema, "", root, fname, 0, out)
    return out


# ------------------------------------------------------------------------------------------------ schema checking
def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _check_schema(schema, path: str, root, fname, depth: int, out: list) -> None:
    if depth > MAX_DEPTH:
        out.append(f"{_where(path)}: schema nesting too deep")
        return
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        out.append(f"{_where(path)}: a schema must be an object or a boolean, got {_type_name(schema)}")
        return
    for kw in schema:
        if kw not in KEYWORDS and kw not in ANNOTATIONS:
            out.append(f"{_where(path)}: unsupported keyword {kw!r} (the contract validator does not implement it)")

    def sub(key, value, child):
        _check_schema(child, f"{path}/{key}" if value is None else f"{path}/{key}/{value}", root, fname, depth + 1, out)

    def bad(keyword, msg):
        out.append(f"{_where(path)}: {keyword} {msg}")

    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str):
            bad("$ref", "must be a string")
        else:
            try:
                _resolve(ref, root, fname)
            except KeyError:
                out.append(f"{_where(path)}: cannot resolve $ref {ref!r}")
    if "$defs" in schema:
        if not isinstance(schema["$defs"], dict):
            bad("$defs", "must be an object of schemas")
        else:
            for k, v in schema["$defs"].items():
                sub("$defs", _esc(k), v)
    if "type" in schema:
        t = schema["type"]
        names = [t] if isinstance(t, str) else t
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n in TYPES for n in names):
            bad("type", f"must be one of {', '.join(TYPES)} or a non-empty list of them")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            bad("properties", "must be an object of schemas")
        else:
            for k, v in schema["properties"].items():
                sub("properties", _esc(k), v)
    if "required" in schema:
        r = schema["required"]
        if not isinstance(r, list) or not all(isinstance(n, str) for n in r):
            bad("required", "must be a list of property names")
    if "additionalProperties" in schema:
        ap = schema["additionalProperties"]
        if isinstance(ap, bool):
            pass
        elif isinstance(ap, dict):
            sub("additionalProperties", None, ap)
        else:
            bad("additionalProperties", "must be a boolean or a schema")
    if "items" in schema:
        it = schema["items"]
        if isinstance(it, (bool, dict)):
            sub("items", None, it)
        else:
            bad("items", "must be a schema")
    for kw in ("minItems", "maxItems", "minLength", "maxLength"):
        if kw in schema and (not _is_int(schema[kw]) or schema[kw] < 0):
            bad(kw, "must be a non-negative integer")
    for kw in ("minimum", "maximum"):
        if kw in schema and not _is_number(schema[kw]):
            bad(kw, "must be a number")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        bad("enum", "must be a non-empty list")
    if "pattern" in schema:
        if not isinstance(schema["pattern"], str):
            bad("pattern", "must be a string")
        else:
            try:
                _pattern(schema["pattern"])
            except re.error as e:
                bad("pattern", f"is not a valid regular expression ({e})")
    if "format" in schema and schema["format"] not in FORMATS:
        bad("format", f"{schema['format']!r} is not supported (only {', '.join(FORMATS)})")
    for kw in ("anyOf", "oneOf"):
        if kw in schema:
            alts = schema[kw]
            if not isinstance(alts, list) or not alts:
                bad(kw, "must be a non-empty list of schemas")
            else:
                for i, a in enumerate(alts):
                    sub(kw, str(i), a)


def check_schema(schema) -> list[str]:
    """Problems that make `schema` unfit for this validator (empty = fine). Refs are checked to resolve."""
    out: list = []
    _check_schema(schema, "", schema, None, 0, out)
    return out


# ------------------------------------------------------------------------------------------------ envelopes
def _actions() -> list:
    return list(load("protocol")["actions"])


def _under(prefix: str, errs: list[str]) -> list[str]:
    """Re-root errors found in a sub-document: "/times/0: x" -> "/data/times/0: x"; the sub-document's own "/: x" ->
    "/data: x"."""
    out = []
    for e in errs:
        path, sep, msg = e.partition(": ")
        out.append(f"{prefix}{'' if path == '/' else path}{sep}{msg}")
    return out


def validate_request(req) -> list[str]:
    """Request envelope + the action's `$defs/data` (errors under /data/...)."""
    errs = validate(req, "request")
    if isinstance(req, dict) and isinstance(req.get("action"), str) and req["action"] in _actions()             and isinstance(req.get("data"), dict):
        errs += _under("/data", validate(req["data"], f"{req['action']}#/$defs/data"))
    return errs


def validate_result(res) -> list[str]:
    """Result envelope + the action's `$defs/readback` when ok (errors under /readback/...). A failed result may carry a
    partial readback (e.g. the open project that blocked an After Effects build): it is checked against the action's
    `$defs/readback_failure` when there is one, else only that it is an object."""
    errs = validate(res, "result")
    if isinstance(res, dict) and isinstance(res.get("action"), str) and res["action"] in _actions()             and isinstance(res.get("readback"), dict):
        key = "readback" if res.get("ok") is True else "readback_failure"
        if key in load(res["action"]).get("$defs", {}):
            errs += _under("/readback", validate(res["readback"], f"{res['action']}#/$defs/{key}"))
    return errs
