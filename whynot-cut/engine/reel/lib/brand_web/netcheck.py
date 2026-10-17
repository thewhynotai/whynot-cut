# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Which addresses the website reader may connect to (Addendum J2.2, J13.2).

Only global unicast addresses. Loopback, private, link-local, CGNAT, multicast, unspecified, documentation and every
other special range are refused, also when they are wrapped in an IPv6 form that carries an IPv4 address
(IPv4-mapped `::ffff:a.b.c.d`, IPv4-compatible `::a.b.c.d`, 6to4 `2002::/16`, Teredo `2001::/32`, NAT64 `64:ff9b::/96`):
the wrapped address is checked too. A host written as an odd number (`2130706433`, `0x7f.1`, `0177.0.0.1`, `127.1`) is
refused before any lookup, because resolvers read such forms as addresses.
"""
from __future__ import annotations

import ipaddress
import re

_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_NUMERIC_LABELS = re.compile(r"^(0x[0-9a-f]*|[0-9]+)(\.(0x[0-9a-f]*|[0-9]+))*\.?$", re.I)


def _v4_ok(a: ipaddress.IPv4Address) -> bool:
    return bool(a.is_global and not (a.is_multicast or a.is_reserved or a.is_loopback or a.is_link_local
                                      or a.is_private or a.is_unspecified))


def _wrapped_v4(a: ipaddress.IPv6Address) -> list:
    """The IPv4 addresses an IPv6 address carries (empty for a plain IPv6 address)."""
    out = []
    if a.ipv4_mapped:
        out.append(a.ipv4_mapped)
    if a.sixtofour:
        out.append(a.sixtofour)
    if a.teredo:
        out.extend(a.teredo)
    if a in _NAT64:
        out.append(ipaddress.IPv4Address(int(a) & 0xFFFFFFFF))
    if int(a) >> 32 == 0:                         # IPv4-compatible ::a.b.c.d (deprecated, still routed by some stacks)
        out.append(ipaddress.IPv4Address(int(a) & 0xFFFFFFFF))
    return out


def ip_ok(ip: str) -> bool:
    """True only for a global unicast address, after unwrapping any IPv4 address it carries."""
    try:
        a = ipaddress.ip_address(str(ip).split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv4Address):
        return _v4_ok(a)
    inner = _wrapped_v4(a)
    if inner:
        return all(_v4_ok(v) for v in inner)
    return bool(a.is_global and not (a.is_multicast or a.is_reserved or a.is_loopback or a.is_link_local
                                      or a.is_private or a.is_unspecified or a.is_site_local))


def classify_host(host: str) -> tuple:
    """("ip", canonical address) for an address literal, ("name", host) for a DNS name, ("bad", reason) for a host
    that is neither: odd numeric forms resolvers would read as an address, or an empty host."""
    h = (host or "").strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    if not h:
        return ("bad", "empty")
    try:
        return ("ip", str(ipaddress.ip_address(h.split("%", 1)[0])))
    except ValueError:
        pass
    if ":" in h:
        return ("bad", "not_an_address")
    if _NUMERIC_LABELS.match(h):
        return ("bad", "numeric_host")
    return ("name", h.lower())
