# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""JavaScript semantics the Tidy twins need (the twins of adobe/tools/tidy/src/js/{classify,plan,sync}.js take JSON-like
data from Premiere through the panel and must treat it the way the JS does):

* `key(v)`        the string a value becomes as an object property name (5 -> "5", None -> "null"): a node id may arrive
                  as a number and still be the same property;
* `js_order(keys)` the order `for (k in obj)` enumerates the keys of a plain object: array-index keys ("0".."4294967294")
                  first, ascending, then the others in insertion order;
* `truthy(v)`     `if (v)`: None, False, 0, 0.0, NaN and "" are false, an empty list or dict is TRUE;
* `num(v)`        a number for a comparison (`>=`, `>`): numbers as they are, numeric strings converted, anything else NaN;
* `u16len`, `u16slice`, `u16key`   length, slice and sort key in UTF-16 code units (JS strings are UTF-16: an emoji is two
                  units, a cut can land inside it and leave a lone surrogate, and `<` on strings compares units);
* `js_str(v)`     `String(v)` for the values that occur (strings as they are, numbers without a trailing .0).
Missing keys: a JS property that is not there is `undefined` and `JSON.stringify` leaves it out; `MISSING` marks it so the
twins can leave the key out of their result dicts too (a key that is there with the value None is JSON null).
"""
from __future__ import annotations

import math
import re

__all__ = ["PROTO_KEYS", "MISSING", "key", "js_order", "truthy", "num", "u16len", "u16slice", "u16key", "js_str", "get", "mk"]


class _Missing:
    def __repr__(self):
        return "MISSING"

    def __bool__(self):
        return False


MISSING = _Missing()
# names a plain JS object already has (inherited from Object.prototype): `obj[name]` is truthy before anything is stored
PROTO_KEYS = frozenset(["constructor", "toString", "valueOf", "hasOwnProperty", "isPrototypeOf", "propertyIsEnumerable", "toLocaleString",
                        "__proto__", "__defineGetter__", "__defineSetter__", "__lookupGetter__", "__lookupSetter__"])
_INDEX = re.compile(r"(?:0|[1-9][0-9]*)\Z")


def js_str(v) -> str:
    if isinstance(v, str):
        return v
    if v is None:
        return "null"
    if v is MISSING:
        return "undefined"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:
            return "NaN"
        if v in (math.inf, -math.inf):
            return "Infinity" if v > 0 else "-Infinity"
        return str(int(v)) if v == int(v) and abs(v) < 1e21 else repr(v)
    return str(v)


def key(v) -> str:
    """The property name a value is stored under in a JS object."""
    return js_str(v)


def js_order(keys):
    """`keys` (strings, insertion order) in the order a JS `for ... in` lists them."""
    idx = [k for k in keys if _INDEX.match(k) and int(k) < 4294967295]
    rest = [k for k in keys if not (_INDEX.match(k) and int(k) < 4294967295)]
    return sorted(idx, key=int) + rest


def truthy(v) -> bool:
    if v is None or v is MISSING or v is False or v == "":
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return not (v == 0 or v != v)
    return True


def num(v) -> float:
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip(" \t\n\r\v\f ﻿  ")
        if s == "":
            return 0.0
        try:
            return float(s)
        except ValueError:
            return math.nan
    return math.nan


def u16len(s: str) -> int:
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def u16slice(s: str, start: int, end: int) -> str:
    """s.slice(start, end) in UTF-16 code units (lone surrogates survive)."""
    raw = s.encode("utf-16-le", "surrogatepass")
    return raw[2 * start:2 * end].decode("utf-16-le", "surrogatepass")


def u16key(s: str) -> bytes:
    """A sort key that orders strings by UTF-16 code units, as JS `<` does (big-endian bytes compare as the units do)."""
    return s.encode("utf-16-be", "surrogatepass")


def get(d, name):
    """d[name] or MISSING (JS undefined) when the property is not there."""
    return d[name] if isinstance(d, dict) and name in d else MISSING


def mk(**pairs):
    """A result dict in the order given, leaving out the pairs whose value is MISSING (undefined is not serialised)."""
    return {k: v for k, v in pairs.items() if v is not MISSING}
