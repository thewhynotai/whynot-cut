# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""robots.txt for the website reader (Addendum J2.1), RFC 9309 matching.

`urllib.robotparser` uses the first matching rule; RFC 9309 says the longest match wins and Allow wins a tie, with `*`
and `$` in patterns. This module does that:
  * groups: consecutive `User-agent` lines share one group; every group naming our product token (`WhyNotCut`, any
    case) is merged; if none names us, every `*` group is merged; no group at all → everything allowed;
  * rules before the first `User-agent` line are ignored; an empty `Disallow:` is no rule;
  * paths and patterns are compared in one normal form: non-ASCII as UTF-8 percent-escapes, escapes in upper case;
  * `/robots.txt` itself is always allowed;
  * `Crawl-delay` (not in the RFC, honoured up to the fetcher's cap) is read from the chosen group.
What the fetcher does with HTTP answers (4xx = allow all, 5xx or unreachable = deny all) is `allow_all` / `deny_all`.
"""
from __future__ import annotations

import re
from urllib.parse import quote

AGENT = "whynotcut"
_SAFE = "/?=&;:@!$'()*+,%-._~[]"
_UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _escape(m) -> str:
    ch = chr(int(m.group(1), 16))
    return ch if ch in _UNRESERVED else m.group(0).upper()


def _norm(s: str) -> str:
    """One form for paths and patterns (RFC 9309 2.2.2): non-ASCII → UTF-8 escapes, escapes of unreserved characters
    decoded (`/%61dmin` is `/admin`), every other escape in upper case (`%2F` stays an escape, never a `/`)."""
    s = quote(s, safe=_SAFE)
    return re.sub(r"%([0-9a-fA-F]{2})", _escape, s)


class Rules:
    def __init__(self, rules=(), crawl_delay=None, source="file", allow_all=False, deny_all=False):
        self._rules = [(len(p), allow, self._compile(p)) for p, allow in rules]
        self.crawl_delay = crawl_delay
        self.source = source                    # file | 4xx | 5xx | unreachable
        self._allow_all = allow_all
        self._deny_all = deny_all

    @staticmethod
    def _compile(pattern: str):
        end = pattern.endswith("$")
        body = pattern[:-1] if end else pattern
        rx = ".*".join(re.escape(part) for part in body.split("*"))
        return re.compile(rx + ("$" if end else ""), re.S)

    def allowed(self, path: str) -> bool:
        p = _norm(path or "/")
        if p.split("?", 1)[0] == "/robots.txt":
            return True
        if self._deny_all:
            return False
        if self._allow_all:
            return True
        best = None                              # (length, allow)
        for length, allow, rx in self._rules:
            if rx.match(p) and (best is None or length > best[0] or (length == best[0] and allow)):
                best = (length, allow)
        return True if best is None else best[1]


def deny_all(source: str) -> Rules:
    return Rules(deny_all=True, source=source)


def allow_all(source: str) -> Rules:
    return Rules(allow_all=True, source=source)


def parse(text: str, agent: str = AGENT) -> Rules:
    agent = agent.lower()
    groups = []                                  # [agents set, rules list, crawl_delay]
    cur = None
    last_was_agent = False
    for raw in (text or "").lstrip("﻿").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key == "user-agent":
            if cur is None or not last_was_agent:
                cur = [set(), [], None]
                groups.append(cur)
            m = re.match(r"[A-Za-z_*-]+", val)          # the product token: "WhyNotCut/3.0" names us
            cur[0].add(m.group(0).lower() if m else val.lower())
            last_was_agent = True
            continue
        last_was_agent = False
        if cur is None:
            continue
        if key in ("allow", "disallow"):
            if val:
                cur[1].append((_norm(val), key == "allow"))
        elif key == "crawl-delay":
            try:
                d = float(val)
            except ValueError:
                continue
            if d >= 0 and d == d and d != float("inf"):
                cur[2] = d
    ours = [g for g in groups if agent in g[0]]
    chosen = ours or [g for g in groups if "*" in g[0]]
    if not chosen:
        return Rules()
    rules = [r for g in chosen for r in g[1]]
    delays = [g[2] for g in chosen if g[2] is not None]
    return Rules(rules, max(delays) if delays else None)
