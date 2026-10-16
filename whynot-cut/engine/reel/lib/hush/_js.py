# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""JavaScript value-to-string rules the Hush twins need (String(x), Number#toString) so output text matches the panel."""
from __future__ import annotations

from decimal import Decimal

__all__ = ["js_num_str", "js_str"]


def js_num_str(x):
    """Number.prototype.toString for finite doubles: -48 -> "-48", -44.4 -> "-44.4", 1e-7 -> "1e-7", 1e21 -> "1e+21"."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if x != x:
        return "NaN"
    if x in (float("inf"), float("-inf")):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    if x.is_integer() and abs(x) < 1e21:
        return str(int(x))
    sign, digits, exp = Decimal(repr(abs(x))).as_tuple()
    ds = "".join(str(d) for d in digits).rstrip("0") or "0"
    k = len(ds)
    n = exp + len(digits)  # the value is 0.<digits> * 10**n
    if k <= n <= 21:
        body = ds + "0" * (n - k)
    elif 0 < n <= 21:
        body = ds[:n] + "." + ds[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + ds
    else:
        e = n - 1
        body = ds[0] + ("." + ds[1:] if k > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return ("-" if x < 0 else "") + body


def js_str(v):
    """String(v) for the JSON-like values that reach the filler matcher."""
    if isinstance(v, str):
        return v
    if v is None:
        return "null"
    return js_num_str(v)
