# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Mixed Arabic + English text: paragraph direction, line breaking and per-line visual order (3.0 Phase 4 Task 54 =
Addendum M2-T1). One module for every renderer: the stills (hb_text), previews, thumbnails, caption grouping (Task 23)
and kinetic units (K-T5) call it instead of keeping their own bidi rules.

The order follows the Unicode Bidirectional Algorithm (UAX #9, Unicode 15 data from `unicodedata`):
1. the paragraph direction is decided ONCE per caption or graphic paragraph: HL1, RTL if the paragraph has any Arabic
   letter (bidi class AL) outside an isolate, even when it starts with a Latin term («AI بيغيّر الطب»); otherwise P2/P3
   (first strong letter; none = LTR). A client may force RTL. Every line of the paragraph keeps that direction;
2. the levels are resolved on the whole paragraph: X1–X10 (embeddings, overrides and isolates, for host text that
   carries them), W1–W7, N0 (bracket pairs), N1–N2, I1–I2;
3. the paragraph is broken into lines (`wrap`), and only then is each line reordered (L1–L2). Reordering never runs on
   the whole paragraph before breaking.
L3 is left to the shaper (runs keep their logical text, so marks stay on their letter) and so is L4: a run with
`rtl` True is shaped right-to-left and HarfBuzz/CoreText mirror its brackets. `visual()` mirrors brackets itself.

Line breaks fall only at spaces, never:
- between «الـ» and its Latin word («الـ MRI»), a number and its unit («٥٠٠ mg», «50 %», «١٠٠ جنيه»), a currency sign
  and its number («$ 50»), the digit groups of a phone number, the numbers of a range («10 - 20»);
- after an opening bracket or quote, or before a closing bracket, quote or punctuation mark;
and, when another break fits, not inside a short Latin run (≤ 3 words: «blood sugar level», «iPhone 15 Pro»).
Breaking at a no-break space (U+00A0, U+202F, U+2007) never happens. A unit is matched with its harakat dropped and
the Whisper spellings folded («دقيقه», «مرّات», «وحده»).

Pure functions, no files, no platform branch: Windows and macOS get the same lines and runs; a renderer that runs
its own UAX #9 (CoreText) gets host_text(). The bracket pairs come from the Unicode Character Database 15.0
(BidiBrackets.txt, Unicode License v3; the notice is in tests/fixtures/bidi/UNICODE-LICENSE.txt and, with the M2-T1
licence-notice patch, in the third-party notices); the tests pin `unicodedata.unidata_version` to the same 15.0.

API: direction(), paragraph(), line_runs(), logical_runs(), visual(), reorder(), word_pieces(), line_pieces(),
host_text(), phone_spans(), breaks(), word_breaks(), wrap(), lay_out(), set_digits(), punctuation_findings(),
control_findings().
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_DEPTH = 125                       # BD2
_MAX_BRACKET_STACK = 63               # BD16

_EMBED = {"LRE", "RLE", "LRO", "RLO"}
_ISO_INIT = {"LRI", "RLI", "FSI"}
_REMOVED = _EMBED | {"PDF", "BN"}     # X9
_NI = {"B", "S", "WS", "ON", "BN", "FSI", "LRI", "RLI", "PDI"}
# drawn as nothing: the explicit controls and the directional marks (they order text, they are never glyphs)
_INVISIBLE = _EMBED | {"PDF"} | _ISO_INIT | {"PDI"}
_MARKS = {"\u200e", "\u200f", "\u061c"}          # LRM, RLM, ALM

# BidiBrackets.txt (Unicode 15.0): opening, closing
_BRACKETS = ("()[]{}༺༻༼༽᚛᚜⁅⁆⁽⁾₍₎⌈⌉⌊⌋"
             "〈〉❨❩❪❫❬❭❮❯❰❱❲❳❴❵"
             "⟅⟆⟦⟧⟨⟩⟪⟫⟬⟭⟮⟯⦃⦄⦅⦆"
             "⦇⦈⦉⦊⦋⦌⦍⦐⦏⦎⦑⦒⦓⦔⦕⦖"
             "⦗⦘⧘⧙⧚⧛⧼⧽⸢⸣⸤⸥⸦⸧⸨⸩"
             "⹕⹖⹗⹘⹙⹚⹛⹜〈〉《》「」『』"
             "【】〔〕〖〗〘〙〚〛﹙﹚﹛﹜﹝﹞"
             "（）［］｛｝｟｠｢｣")
_OPEN = {_BRACKETS[i]: _BRACKETS[i + 1] for i in range(0, len(_BRACKETS), 2)}
_CLOSE = {c: o for o, c in _OPEN.items()}
_CANON = {"〈": "〈", "〉": "〉"}            # canonical equivalents match each other (BD16)
_MIRROR = dict(_OPEN, **_CLOSE)
_MIRROR.update({"<": ">", ">": "<", "«": "»", "»": "«", "‹": "›", "›": "‹",
                "≤": "≥", "≥": "≤"})


def _cls(ch: str) -> str:
    return unicodedata.bidirectional(ch) or "L"             # unassigned: L


# --------------------------------------------------------------------------- paragraph direction
def _isolate_scan(cls: list[str], start: int, end: int, stop_at_pdi: bool):
    """Yield (i, class) of the characters at isolate depth 0 from `start` (P2: isolate contents are skipped)."""
    depth = 0
    for i in range(start, end):
        c = cls[i]
        if c in _ISO_INIT:
            depth += 1
        elif c == "PDI":
            if depth:
                depth -= 1
            elif stop_at_pdi:
                return
        elif depth == 0:
            yield i, c


def _first_strong(cls: list[str], start: int, end: int, stop_at_pdi: bool = False) -> int | None:
    """P2/P3: 1 if the first strong letter is R/AL, 0 if L, None if there is none."""
    for _, c in _isolate_scan(cls, start, end, stop_at_pdi):
        if c == "L":
            return 0
        if c in ("R", "AL"):
            return 1
    return None


def direction(text: str, force_rtl: bool = False, hl1: bool = True) -> int:
    """The paragraph embedding level: 1 (RTL) or 0 (LTR). HL1: any Arabic letter (bidi class AL, a letter: not the
    Arabic punctuation «؟ ؛» that is AL too) outside an isolate makes the paragraph RTL; otherwise P2/P3.
    `force_rtl` is the client setting for an Arabic-first client. `hl1=False` is plain P2/P3 (the conformance test)."""
    if force_rtl:
        return 1
    cls = [_cls(c) for c in text]
    if hl1 and any(c == "AL" and unicodedata.category(text[i]).startswith("L")
                   for i, c in _isolate_scan(cls, 0, len(cls), False)):
        return 1
    return _first_strong(cls, 0, len(cls)) or 0


# --------------------------------------------------------------------------- resolution
@dataclass
class Paragraph:
    text: str
    base: int
    levels: list[int]
    classes: list[str]                 # the original bidi classes
    removed: list[bool] = field(default_factory=list)

    @property
    def rtl(self) -> bool:
        return bool(self.base & 1)


def _matching_pdi(cls: list[str]) -> dict[int, int]:
    """BD9: isolate initiator index -> its matching PDI index."""
    out, stack = {}, []
    for i, c in enumerate(cls):
        if c in _ISO_INIT:
            stack.append(i)
        elif c == "PDI" and stack:
            out[stack.pop()] = i
        elif c == "B":
            stack.clear()
    return out


def _explicit(cls: list[str], base: int, match: dict[int, int]) -> tuple[list[int], list[str]]:
    """X1–X8: embedding levels and the override-adjusted classes."""
    n = len(cls)
    levels, types = [base] * n, list(cls)
    stack = [(base, None, False)]          # (level, override 'L'|'R'|None, isolate)
    over_iso = over_emb = valid_iso = 0
    for i, c in enumerate(cls):
        top_level, top_over, _ = stack[-1]
        if c in _EMBED:
            levels[i] = top_level
            lvl = (top_level + 1) | 1 if c in ("RLE", "RLO") else (top_level + 2) & ~1
            if lvl <= MAX_DEPTH and over_iso == 0 and over_emb == 0:
                stack.append((lvl, {"RLO": "R", "LRO": "L"}.get(c), False))
            elif over_iso == 0:
                over_emb += 1
        elif c in _ISO_INIT:
            levels[i] = top_level
            if top_over:
                types[i] = top_over
            rtl = c == "RLI"
            if c == "FSI":
                end = match.get(i, n)
                rtl = _first_strong(cls, i + 1, end, stop_at_pdi=True) == 1
            lvl = (top_level + 1) | 1 if rtl else (top_level + 2) & ~1
            if lvl <= MAX_DEPTH and over_iso == 0 and over_emb == 0:
                valid_iso += 1
                stack.append((lvl, None, True))
            else:
                over_iso += 1
        elif c == "PDI":
            if over_iso > 0:
                over_iso -= 1
            elif valid_iso > 0:
                over_emb = 0
                while not stack[-1][2]:
                    stack.pop()
                stack.pop()
                valid_iso -= 1
            levels[i] = stack[-1][0]
            if stack[-1][1]:
                types[i] = stack[-1][1]
        elif c == "PDF":
            levels[i] = top_level
            if over_iso > 0:
                pass
            elif over_emb > 0:
                over_emb -= 1
            elif not stack[-1][2] and len(stack) >= 2:
                stack.pop()
        elif c == "B":
            levels[i] = base
        elif c == "BN":
            levels[i] = top_level
        else:
            levels[i] = top_level
            if top_over:
                types[i] = top_over
    return levels, types


def _sequences(levels: list[int], cls: list[str], removed: list[bool], match: dict[int, int]) -> list[list[int]]:
    """BD13: the isolating run sequences (lists of indices, X9-removed characters left out)."""
    runs: list[list[int]] = []
    for i in range(len(levels)):
        if removed[i]:
            continue
        if runs and levels[runs[-1][-1]] == levels[i]:
            runs[-1].append(i)
        else:
            runs.append([i])
    run_of = {r[0]: r for r in runs}
    pdi_targets = set(match.values())
    seqs = []
    for r in runs:
        if r[0] in pdi_targets and cls[r[0]] == "PDI":
            continue                            # continues the sequence of its initiator
        seq = list(r)
        while cls[seq[-1]] in _ISO_INIT and seq[-1] in match:
            nxt = run_of.get(match[seq[-1]])
            if nxt is None:
                break
            seq += nxt
        seqs.append(seq)
    return seqs


def _resolve_sequence(seq: list[int], text: str, cls: list[str], types: list[str], levels: list[int],
                      explicit: list[int], removed: list[bool], base: int) -> None:
    """W1–I2 on one isolating run sequence; `explicit` = the X1–X8 levels (sos/eos never read resolved levels)."""
    n = len(text)
    lvl = explicit[seq[0]]
    first, last = seq[0], seq[-1]
    prev = next((explicit[k] for k in range(first - 1, -1, -1) if not removed[k]), base)
    if cls[last] in _ISO_INIT:
        nxt = base                              # X10: an isolate initiator ends the sequence: compare with the base
    else:
        nxt = next((explicit[k] for k in range(last + 1, n) if not removed[k]), base)
    sos = "R" if max(prev, lvl) & 1 else "L"
    eos = "R" if max(nxt, lvl) & 1 else "L"
    t = [types[i] for i in seq]
    m = len(t)
    # W1
    for k in range(m):
        if t[k] == "NSM":
            if k == 0:
                t[k] = sos
            elif t[k - 1] in _ISO_INIT or t[k - 1] == "PDI":
                t[k] = "ON"
            else:
                t[k] = t[k - 1]
    # W2
    last_strong = sos
    for k in range(m):
        if t[k] in ("R", "L", "AL"):
            last_strong = t[k]
        elif t[k] == "EN" and last_strong == "AL":
            t[k] = "AN"
    # W3
    t = ["R" if x == "AL" else x for x in t]
    # W4
    for k in range(1, m - 1):
        if t[k] == "ES" and t[k - 1] == "EN" and t[k + 1] == "EN":
            t[k] = "EN"
        elif t[k] == "CS" and t[k - 1] == t[k + 1] and t[k - 1] in ("EN", "AN"):
            t[k] = t[k - 1]
    # W5
    k = 0
    while k < m:
        if t[k] == "ET":
            j = k
            while j < m and t[j] == "ET":
                j += 1
            if (k > 0 and t[k - 1] == "EN") or (j < m and t[j] == "EN"):
                for q in range(k, j):
                    t[q] = "EN"
            k = j
        else:
            k += 1
    # W6
    t = ["ON" if x in ("ES", "ET", "CS") else x for x in t]
    # W7
    last_strong = sos
    for k in range(m):
        if t[k] in ("R", "L"):
            last_strong = t[k]
        elif t[k] == "EN" and last_strong == "L":
            t[k] = "L"
    e = "R" if lvl & 1 else "L"
    # N0: bracket pairs (BD16), only characters that are still ON
    pairs, stack = [], []
    for k in range(m):
        ch = text[seq[k]]
        if t[k] != "ON":
            continue
        if ch in _OPEN:
            if len(stack) >= _MAX_BRACKET_STACK:
                break
            stack.append((_CANON.get(_OPEN[ch], _OPEN[ch]), k))
        elif ch in _CLOSE:
            want = _CANON.get(ch, ch)
            for s in range(len(stack) - 1, -1, -1):
                if stack[s][0] == want:
                    pairs.append((stack[s][1], k))
                    del stack[s:]
                    break
    pairs.sort()

    def strong(x):
        return "R" if x in ("R", "EN", "AN") else ("L" if x == "L" else None)
    for o, c in pairs:
        inside = [strong(t[q]) for q in range(o + 1, c)]
        inside = [x for x in inside if x]
        new = None
        if e in inside:
            new = e
        elif inside:
            ctx = next((strong(t[q]) for q in range(o - 1, -1, -1) if strong(t[q])), sos)
            new = ctx                           # opposite context: that direction; else e
        if new:
            for q in (o, c):
                t[q] = new
                r = q + 1
                while r < m and types[seq[r]] == "NSM" and cls[seq[r]] == "NSM":
                    t[r] = new
                    r += 1
    # N1 / N2
    k = 0
    while k < m:
        if t[k] in _NI:
            j = k
            while j < m and t[j] in _NI:
                j += 1
            before = sos if k == 0 else ("R" if t[k - 1] in ("R", "EN", "AN") else t[k - 1])
            after = eos if j == m else ("R" if t[j] in ("R", "EN", "AN") else t[j])
            fill = before if before == after else e
            for q in range(k, j):
                t[q] = fill
            k = j
        else:
            k += 1
    # I1 / I2
    for k, i in enumerate(seq):
        x = t[k]
        if lvl & 1 == 0:
            levels[i] = lvl + (1 if x == "R" else 2 if x in ("AN", "EN") else 0)
        else:
            levels[i] = lvl + (1 if x in ("L", "EN", "AN") else 0)


_D = "0-9٠-٩۰-۹"
_PHONE_SPACE = " \u00a0\u202f\u2007"                    # a phone's groups may be joined by a no-break space
_PHONE_CHAIN = re.compile(rf"(?<![\w+.,٫٬/])\+?[{_D}]+(?:[{_PHONE_SPACE}\-–][{_D}]+)*")
_PHONE_GROUP = re.compile(rf"\+?[^{_PHONE_SPACE}\-–]+")
_ZEROS = "0٠۰"


_YEAR = re.compile(r"(?:19|20|١٩|٢٠|۱۹|۲۰)[0-9٠-٩۰-۹]{2}")


def _droppable_tail(text: str, groups: list[tuple[int, int]], en: int, glued_end: bool, all_short: bool) -> bool:
    """`groups[en:]`, the groups after a phone, are not part of it: short numbers («24 ساعة», «24/7»; `all_short`), a
    year («2024»), or the next phone (≤ 4 groups). A long group glued to more text («5678/9») is the phone's own last
    group, never a tail."""
    if all_short:
        return True
    if len(groups) - en > 4 or glued_end:
        return False
    gs = [text[x:y] for x, y in groups[en:]]
    if len(gs) == 1 and _YEAR.fullmatch(gs[0]):
        return True
    return gs[0][:1] in _ZEROS and len(gs) > 1 and all(len(g) >= 3 for g in gs[1:]) and \
        7 <= sum(len(g) for g in gs) <= 12


def _value_list(gs: list[str]) -> bool:
    """«05 250 500», «090 120 140», «+150 250 350», «05 500 250 125»: doses, readings and scores, not a phone. Two
    or more groups after the head, each of exactly 3 digits and round (a multiple of 10 or 25), all rising or all
    falling, and the head smaller than every one of them. A phone's groups are not round («0555 123 456», «+966 512
    600 789») or end in 4+ digits («02 2400 1100», «+1 800 300 2000»). The cost, on random digits: about 1 in 70
    numbers of the shape 0X XXX XXX (Lebanese landlines: «05 250 500» is a valid one, and also a dose list; the
    rule reads it as the list), about 1 in 300 of the shape 0XXX XXX XXX, and about 1 in 2,000 written with a
    country code in 3-digit groups. Left as phones: a list whose values reach 4 digits («05 250 500 1000») or that
    turns («010 500 250 750»)."""
    tail = gs[1:]
    if len(tail) < 2 or any(len(g) != 3 for g in tail):
        return False
    vals = [int(g) for g in tail]
    if any(v % 10 and v % 25 for v in vals):
        return False
    rising = all(a <= b for a, b in zip(vals, vals[1:]))
    falling = all(a >= b for a, b in zip(vals, vals[1:]))
    return (rising or falling) and int(gs[0].lstrip("+")) < min(vals)


def phone_spans(text: str) -> list[tuple[int, int]]:
    """Phone numbers, as dialled: 7–15 digits in groups joined by single spaces (a no-break space too) or hyphens, and
    either
    - «+» and a country code («+20 100 123 4567», «+966 5 1234 5678», «+201001234567»), or
    - a leading zero in a first group of 2+ digits, groups of 3+ digits after it and at most 12 digits («010 1234
      5678», «02 2345 6789», «٠١٠ ١٢٣٤ ٥٦٧٨»; not «0 250 500» or «٠ ١٠٠ ٢٠٠٠»),
    and not a list of values («05 250 500», «05 100 200 300», «+120 140 160»; see _value_list).
    Numbers set off by a space before or after it are not part of it («اتصل 3 010 1234 5678», «010 1234 5678 24/7»,
    «010 1234 5678 2024»); two phones in a row are two. Not phones: lists («2020 2021 2022», «05 10 15 20»), dates
    («01-02-2024»), times, decimals, a number glued to a letter, «%», «/» or a hyphenated tail («010 1234 5678/9»,
    «010 1234 5678-9»). A number may stand right before a sentence mark or right after a colon («رقمي:010 1234
    5678.»). Linear in the text: a phone has at most 15 groups."""
    out = []
    for m in _PHONE_CHAIN.finditer(text):
        groups = [(g.start() + m.start(), g.end() + m.start()) for g in _PHONE_GROUP.finditer(m.group())]
        seps = [" " if text[x - 1] in _PHONE_SPACE else text[x - 1] for x, _ in groups]   # before group k ≥ 1
        nxt = text[m.end():m.end() + 2]
        short_from = [True] * (len(groups) + 1)            # short_from[k]: every group from k on has < 3 digits
        for k in range(len(groups) - 1, -1, -1):
            short_from[k] = short_from[k + 1] and groups[k][1] - groups[k][0] < 3
        glued_end = bool(nxt[:1]) and (re.match(r"[\w%٪]", nxt[:1]) is not None
                                       or (nxt[:1] in ".,٫٬/:" and nxt[1:2].isdigit()))

        def valid(st, en):
            if st and seps[st] != " ":
                return False                                # «5678-010…»: a hyphenated head belongs to something else
            if en == len(groups):
                if glued_end:
                    return False                            # glued to more text
            elif seps[en] != " " or (en + 1 < len(groups) and seps[en + 1] != " "):
                return False                                # «… 5678-9»: the tail is hyphenated to the phone or itself
            elif not _droppable_tail(text, groups, en, glued_end, short_from[en]):
                return False
            gs = [text[x:y] for x, y in groups[st:en]]
            digits = sum(len(g.lstrip("+")) for g in gs)
            if _value_list(gs):
                return False
            if gs[0].startswith("+"):
                return (len(gs) == 1 or len(gs[-1]) >= 3) and 7 <= digits <= 15
            return gs[0][:1] in _ZEROS and len(gs[0]) >= 2 and len(gs) > 1 and all(len(g) >= 3 for g in gs[1:]) \
                and 7 <= digits <= 12

        st = 0
        while st < len(groups):
            en = next((e for e in range(min(len(groups), st + 15), st, -1) if valid(st, e)), None)
            if en is None:
                st += 1
                continue
            out.append((groups[st][0], groups[en - 1][1]))
            st = en
    return out


def paragraph(text: str, base: int | None = None, force_rtl: bool = False, hl1: bool = True) -> Paragraph:
    """Resolve one paragraph's levels (X1–I2). `base` (0/1) is a direction already decided for the whole caption.
    HL3 (with HL1): in a right-to-left paragraph a phone number is laid out as if inside LRO … PDF, so its digit
    groups and its «+» read left to right as dialled («010 1234 5678», never «5678 1234 010»). An override, not an
    isolate: Arabic-Indic digits are AN, and AN groups would still reverse inside an LRI."""
    if base is None:
        base = direction(text, force_rtl=force_rtl, hl1=hl1)
    elif base not in (0, 1):
        raise ValueError("base must be 0 or 1")
    explicit_controls = any(_cls(c) in _INVISIBLE for c in text)      # host text: the author's own controls rule
    spans = phone_spans(text) if hl1 and base == 1 and not explicit_controls else []
    if spans:
        starts, ends = {a for a, _ in spans}, {b for _, b in spans}
        work, where = [], []
        for i in range(len(text) + 1):
            if i in ends:
                work.append("\u202c")                   # PDF
            if i in starts:
                work.append("\u202d")                   # LRO
            if i < len(text):
                where.append(len(work))
                work.append(text[i])
        wp = paragraph("".join(work), base=base, hl1=False)
        return Paragraph(text, base, [wp.levels[i] for i in where], [_cls(c) for c in text],
                         [wp.removed[i] for i in where])
    cls = [_cls(c) for c in text]
    match = _matching_pdi(cls)
    levels, types = _explicit(cls, base, match)
    removed = [c in _REMOVED for c in cls]
    explicit = list(levels)
    for seq in _sequences(explicit, cls, removed, match):
        _resolve_sequence(seq, text, cls, types, levels, explicit, removed, base)
    # X9-removed characters (ZWNJ/ZWJ are BN: they must stay with their letter) take the level of the character before
    last = None
    for i in range(len(text)):
        if removed[i]:
            if last is not None:
                levels[i] = last
        else:
            last = levels[i]
    first = next((levels[i] for i in range(len(text)) if not removed[i]), base)
    for i in range(len(text)):
        if removed[i]:
            levels[i] = first
        else:
            break
    return Paragraph(text, base, levels, cls, removed)


# --------------------------------------------------------------------------- per-line order
@dataclass(frozen=True)
class Run:
    text: str          # logical order, invisible controls left out
    start: int         # logical range in the paragraph
    end: int
    level: int

    @property
    def rtl(self) -> bool:
        return bool(self.level & 1)

    @property
    def dir(self) -> str:
        return "rtl" if self.rtl else "ltr"


def _line_levels(par: Paragraph, start: int, end: int) -> list[int]:
    """L1 on one line: segment/paragraph separators and the whitespace (with isolate controls and removed characters)
    before them and at the line end take the paragraph level."""
    lv = par.levels[start:end]
    cls = par.classes[start:end]
    trailing = True
    for k in range(len(lv) - 1, -1, -1):
        c = cls[k]
        if c in ("S", "B"):
            lv[k] = par.base
            trailing = True
        elif trailing and (c in ("WS", "FSI", "LRI", "RLI", "PDI") or par.removed[start + k]):
            lv[k] = par.base
        else:
            trailing = False
    return lv


def reorder(levels: list[int]) -> list[int]:
    """L2: logical indices in visual (left-to-right) order for one line's levels."""
    order = list(range(len(levels)))
    if not levels:
        return order
    hi = max(levels)
    lo_odd = min(x for x in levels) | 1
    for lv in range(hi, lo_odd - 1, -1):
        k = 0
        while k < len(order):
            if levels[order[k]] >= lv:
                j = k
                while j < len(order) and levels[order[j]] >= lv:
                    j += 1
                order[k:j] = order[k:j][::-1]
                k = j
            else:
                k += 1
    return order


def _drawn(par: Paragraph, i: int) -> bool:
    return par.classes[i] not in _INVISIBLE and par.text[i] not in _MARKS


def line_runs(par: Paragraph, start: int = 0, end: int | None = None) -> list[Run]:
    """The runs of one line in visual left-to-right order. Each run's text is in logical order: shape it in its
    direction (`run.rtl`) and lay the runs out left to right."""
    end = len(par.text) if end is None else end
    if not 0 <= start <= end <= len(par.text):
        raise ValueError("line range outside the paragraph")
    lv = _line_levels(par, start, end)
    vis = [k for k in reorder(lv) if _drawn(par, start + k)]
    groups: list[list[int]] = []
    for k in vis:
        if groups:
            g = groups[-1]
            step = -1 if lv[k] & 1 else 1
            between = range(min(g[-1], k) + 1, max(g[-1], k))
            if lv[g[-1]] == lv[k] and (k - g[-1]) * step > 0 and \
                    all(not _drawn(par, start + q) for q in between):
                g.append(k)
                continue
        groups.append([k])
    out = []
    for g in groups:
        idx = sorted(g)
        out.append(Run("".join(par.text[start + q] for q in idx), start + idx[0], start + idx[-1] + 1, lv[g[0]]))
    return out


def logical_runs(par: Paragraph, start: int = 0, end: int | None = None) -> list[Run]:
    """The same line's runs in LOGICAL order (maximal stretches of one level; invisible controls left out)."""
    end = len(par.text) if end is None else end
    if not 0 <= start <= end <= len(par.text):
        raise ValueError("line range outside the paragraph")
    lv = _line_levels(par, start, end)
    out: list[list] = []
    for k in range(end - start):
        if not _drawn(par, start + k):
            continue
        if out and out[-1][3] == lv[k]:
            out[-1][0] += par.text[start + k]
            out[-1][2] = start + k + 1
        else:
            out.append([par.text[start + k], start + k, start + k + 1, lv[k]])
    return [Run(*r) for r in out]


@dataclass(frozen=True)
class Piece:
    word: int | None   # index into the caller's word list; None = a joining space
    text: str          # logical order
    level: int

    @property
    def rtl(self) -> bool:
        return bool(self.level & 1)


def word_pieces(words: list[str], force_rtl: bool = False, base: int | None = None) -> tuple[bool, list[Piece]]:
    """A caption line held as words (Typesetter.line, kinetic units, thumbnail highlights): (rtl, pieces in visual
    left-to-right order). The words are joined with one space and ordered as one line. A piece is part of one word
    (`word` = its index) or one joining space (`word` None). Lay the pieces out left to right as they come: a word can
    be split («بالـMRI scan»: «MRI scan» reads as one Latin phrase left of «بالـ»; «٤٠٪» is «٪» + «٤٠»), and a moved
    punctuation mark has no space before it («complete … test.» in an Arabic block shows «.complete … test»)."""
    words = [str(w) for w in words]
    text = " ".join(words)
    if base is None:
        base = direction(text, force_rtl=force_rtl)
    par = paragraph(text, base=base)
    owner: list[int | None] = []
    for i, w in enumerate(words):
        owner += [i] * len(w) + ([None] if i < len(words) - 1 else [])
    pieces: list[Piece] = []
    for r in line_runs(par):
        chunks: list[list] = []                 # the run split at word boundaries, logical order
        for q in range(r.start, r.end):
            if not _drawn(par, q):
                continue
            if chunks and chunks[-1][0] == owner[q] and owner[q] is not None:
                chunks[-1][1] += text[q]
            else:
                chunks.append([owner[q], text[q]])
        if r.rtl:
            chunks.reverse()                    # a right-to-left run shows its words right to left
        pieces += [Piece(w, t, r.level) for w, t in chunks]
    return bool(base), pieces


def line_pieces(line) -> list[Piece]:
    """The pieces (as word_pieces) of a line from lay_out(): split from `line.runs`, the runs it is drawn with, so a
    wrapped line keeps the levels of its whole paragraph (W7, N0 and N1 see across the break). `word` indexes
    `line.text.split(" ")`."""
    owner, k = [], 0
    for ch in line.text:
        if ch == " ":
            owner.append(None)
            k += 1
        else:
            owner.append(k)
    drawn = [i for i, ch in enumerate(line.text) if _cls(ch) not in _INVISIBLE and ch not in _MARKS]
    runs = sorted(line.runs, key=lambda r: r.start)
    at, pos = {}, 0                                         # (run, offset in its text) -> index in line.text
    for r in runs:
        for q in range(len(r.text)):
            at[id(r), q] = drawn[pos]
            pos += 1
    pieces: list[Piece] = []
    for r in line.runs:
        chunks: list[list] = []
        for q, ch in enumerate(r.text):
            w = owner[at[id(r), q]]
            if chunks and chunks[-1][0] == w and w is not None:
                chunks[-1][1] += ch
            else:
                chunks.append([w, ch])
        if r.rtl:
            chunks.reverse()
        pieces += [Piece(w, t, r.level) for w, t in chunks]
    return pieces


def host_text(source, base: int | None = None, start: int = 0, end: int | None = None) -> str:
    """One line for a renderer that runs its own UAX #9 (macOS CoreText; the hosts are measured in M2-T2), spelled so
    that any conforming engine draws this module's order. `source` is a Line from lay_out() (a wrapped line), a
    Paragraph with the line's `start`/`end`, or a whole one-line paragraph as text (`base`, else HL1).

    The levels come from the WHOLE paragraph: a line handed to the host on its own would lose W2, W7, N0 and N1 across
    the break («Vitamin D 1000 - 2000 وحدة» wrapped before «1000» reverses the range, on the Mac only) and could look
    like a phone the paragraph rejected. So every logical run is wrapped in embeddings up to its level, the last one an
    override of the run's direction (LRO/RLO … PDF): the host's W/N rules have nothing left to decide, and its L2 gives
    our order. The levels are renumbered from the base up, keeping their order and parity (the same L2 order; a run
    at the base level needs base + 2 to take an override); the host's own L1 resets trailing whitespace and tabs to
    the base, as ours did. A paragraph mark (RLM/LRM) comes first, so the host's P2/P3 finds the base.
    Every character L2 sees stays, at its level: a directional mark as itself, an isolate control as a mark (it is
    never drawn, but it splits a reversal: «٥٠٠ RLM ٢٥٠», «LRI ٥٠٠ PDI LRI mg PDI»); the author's embeddings,
    overrides and PDFs are left out (X9 removes them; their effect is in the levels); joiners stay in their run for
    the shaper. ValueError for a paragraph separator inside the line (one line per call: lay_out splits them), and
    when the renumbered levels pass the host's depth limit (125: only text built from dozens of nested controls)."""
    if isinstance(source, Line):
        if source.par is None:
            raise ValueError("a Line from lay_out() carries its paragraph; build one with lay_out()")
        if base is not None and base != int(source.rtl):
            raise ValueError("base differs from the line's")
        par, start, end = source.par, source.par_start, source.par_end
    else:
        par = paragraph(source, base=base) if isinstance(source, str) else source
        if base is not None and base != par.base:
            raise ValueError("base differs from the paragraph's")
    end = len(par.text) if end is None else end
    if not 0 <= start <= end <= len(par.text):
        raise ValueError("line range outside the paragraph")
    if any(c == "B" for c in par.classes[start:end]):
        raise ValueError("a paragraph separator inside the line: lay the text out with lay_out() first")
    base, lv = par.base, _line_levels(par, start, end)
    runs: list[list] = []                                    # [level, text], logical order
    for k in range(end - start):
        i = start + k
        c = par.classes[i]
        if c in _EMBED or c == "PDF":
            continue
        ch = par.text[i]
        if c in _ISO_INIT or c == "PDI":
            ch = "\u200f" if lv[k] & 1 else "\u200e"
        if runs and runs[-1][0] == lv[k]:
            runs[-1][1] += ch
        else:
            runs.append([lv[k], ch])
    remap, prev = {}, base
    for lvl in sorted({r[0] for r in runs}):
        prev = remap[lvl] = prev + 1 if (prev + 1) % 2 == lvl % 2 else prev + 2
    if prev > MAX_DEPTH:
        raise ValueError("the line nests deeper than a host engine resolves (125 levels)")
    out = ["\u200f" if base else "\u200e"]
    for level, text in runs:
        target, lvl, opened = remap[level], base, 0
        while lvl < target:
            lvl = lvl + 2 if lvl + 2 == target else lvl + 1      # embeddings one level at a time, the override last
            if lvl == target:
                out.append("\u202e" if lvl & 1 else "\u202d")    # RLO / LRO
            else:
                out.append("\u202b" if lvl & 1 else "\u202a")    # RLE / LRE
            opened += 1
        out.append(text + "\u202c" * opened)
    return "".join(out)


def visual(par: Paragraph, start: int = 0, end: int | None = None, mirror: bool = True) -> str:
    """The line as one string in visual order (L4 when `mirror`: the paired brackets and «» ‹› <> ≤≥ of
    right-to-left runs; the shapers mirror every Bidi_Mirrored character themselves)."""
    out = []
    for r in line_runs(par, start, end):
        s = r.text[::-1] if r.rtl else r.text
        if r.rtl and mirror:
            s = "".join(_MIRROR.get(c, c) for c in s)
        out.append(s)
    return "".join(out)


# --------------------------------------------------------------------------- line breaking
_BREAK_SPACE = re.compile(r"[ \t\u1680\u2000-\u2006\u2008-\u200a\u205f\u3000]+")   # never U+00A0, U+2007, U+202F
_LATIN_UNITS = {
    "mg", "g", "kg", "mcg", "µg", "μg", "ug", "ml", "l", "dl", "cl", "km", "m", "cm", "mm", "%", "iu", "mmol",
    "mmol/l", "mg/dl", "mmhg", "bpm", "kcal", "cal", "hz", "khz", "kb", "mb", "gb", "tb", "x", "h", "hr", "hrs",
    "min", "mins", "sec", "s", "ms", "k", "egp", "usd", "sar", "aed", "kwd", "qar", "eur", "gbp", "units", "unit",
    "$", "€", "£", "¥", "mg/kg", "ml/kg", "mcg/kg", "g/dl", "units/kg", "km/h", "mg/l", "g/l", "ml/h",
    "ng", "pg", "ng/ml", "pg/ml", "mg/ml", "mcg/ml", "µg/ml", "iu/kg", "iu/ml", "units/ml", "meq", "meq/l",
    "mmol/mol", "µmol/l", "umol/l", "ml/min", "mm/h", "°", "°c", "°f", "℃", "℉", "tablet", "tablets", "tab", "tabs",
    "capsule", "capsules", "cap", "caps", "dose", "doses", "drop", "drops", "puff", "puffs", "times", "lbs", "lb",
    "cc", "tsp", "tbsp", "cm2", "cm3", "cm²", "cm³", "mm2", "mm3", "mm²", "mm³", "m2", "m3", "m²", "m³", "ampoule",
    "ampoules", "amp", "amps", "patch", "patches", "sachet", "sachets", "vial", "vials",
}
# compared after _fold: no harakat, «أ إ آ» -> «ا», «ة» -> «ه», «ى» -> «ي» (Whisper writes «دقيقه», «وحده», «مره»)
_ARABIC_UNITS = {
    "٪", "مجم", "ملجم", "ملغ", "مغ", "مل", "ملل", "مللي", "ملي", "مليجرام", "ميكروجرام", "جم", "جرام", "جرامات",
    "غرام", "غرامات", "كجم", "كيلو", "كيلوجرام", "كم", "سم", "مم", "لتر", "سيسي",
    "جنيه", "جنيهات", "ج.م", "دولار", "ريال", "درهم", "يورو", "دينار", "ساعة", "ساعات", "دقيقة", "دقايق", "دقائق",
    "ثانية", "ثواني", "سنة", "سنين", "سنوات", "يوم", "أيام", "شهر", "شهور", "أشهر", "أسبوع", "أسابيع",
    "مرة", "مرات", "حباية", "حبايات", "حبة", "حبات", "حبوب", "قرص", "أقراص", "كبسولة", "كبسولات", "حقنة", "حقن",
    "ملعقة", "معلقة", "ملاعق", "معالق", "كوب", "كوباية", "أكواب", "فنجان", "بخة", "بخات", "جرعة", "جرعات",
    "أمبول", "أمبولة", "أمبولات", "لزقة", "لزقات", "كيس", "أكياس", "ظرف", "أظرف", "فيال", "غ", "مجم/كجم", "مل/كجم",
    "ملجم/كجم", "وحدة/كجم", "سم٣", "سم٢", "مم٣", "م٢", "م٣",
    "نقطة", "نقط", "سعر", "سعرة", "سعرات", "كالوري", "وحدة", "وحدات", "مليون", "ألف", "آلاف", "مليار",
    "بالمية", "بالمئة", "درجة", "درجات",
}
_CURRENCY_BEFORE = {"$", "€", "£", "¥", "us$", "e£", "egp", "usd", "sar", "aed", "eur", "gbp", "ج.م"}
_NUM = re.compile(r"^[+\-−]?[$€£]?\d+(?:[.,٫٬:/\-–]\d+)*[%٪]?$")
_DASH = {"-", "–", "—", "−"}
_PUNCT_EDGE = "\"'«»‹›“”‘’„()[]{}.,،؛؟!?:;…"


def _is_open(tok: str) -> bool:
    return bool(tok) and all(c in _OPEN or unicodedata.category(c) in ("Ps", "Pi") or c in "«\"'„‹" for c in tok)


def _is_close(tok: str) -> bool:
    return bool(tok) and all(unicodedata.category(c).startswith("P") and c not in _OPEN and c not in "«„‹"
                             and unicodedata.category(c) not in ("Ps", "Pi") for c in tok)


def _arabic_letters(tok: str) -> bool:
    return any(unicodedata.bidirectional(c) in ("AL", "R") and unicodedata.category(c).startswith("L") for c in tok)


def _latin_letters(tok: str) -> bool:
    return any(unicodedata.bidirectional(c) == "L" and unicodedata.category(c).startswith("L") for c in tok)


def _core(tok: str) -> str:
    return tok.strip(_PUNCT_EDGE)


def _is_num(tok: str) -> bool:
    return bool(_NUM.match(_core(tok) or tok))


_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})


def _fold(word: str) -> str:
    """An Arabic word for the unit list: harakat (and the dagger alef) dropped, the alef, tah marbuta and alef
    maqsura spellings folded."""
    return "".join(c for c in word if not ("\u064b" <= c <= "\u065f" or c == "\u0670")).translate(_FOLD)


_ARABIC_UNITS_FOLDED = {_fold(u) for u in _ARABIC_UNITS}


def _is_unit(tok: str) -> bool:
    c = _core(tok) or tok
    return c.casefold() in _LATIN_UNITS or _fold(c) in _ARABIC_UNITS_FOLDED or tok in ("%", "٪")


def _al_prefix(tok: str) -> bool:
    """«الـ», «بالـ», «والـ»: an Arabic word ending in a tatweel, or the bare article «ال»."""
    return (tok.endswith("ـ") and _arabic_letters(tok)) or tok == "ال"


def _latin_word(tok: str) -> bool:
    return _latin_letters(tok) and not _arabic_letters(tok)


def _gap_rule(left: str, right: str) -> str:
    """"never" or "ok" for the space between two tokens (the short-Latin-run rule is applied by the caller)."""
    rcore = right.lstrip("\"'«“‘„‹([{")
    if _al_prefix(left) and (_latin_letters(rcore) or rcore[:1].isdigit()) and not _arabic_letters(rcore):
        return "never"
    if _is_num(left) and _is_unit(right):
        return "never"
    if (left.casefold() in _CURRENCY_BEFORE or left in _CURRENCY_BEFORE) and _is_num(right):
        return "never"
    if _is_open(left) or _is_close(right):
        return "never"
    return "ok"


def _tokens(text: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """(tokens, gaps) as index ranges; gaps[k] lies between tokens[k] and tokens[k + 1]."""
    toks, gaps = [], []
    pos = 0
    for m in _BREAK_SPACE.finditer(text):
        if m.start() > pos:
            toks.append((pos, m.start()))
        if toks and m.end() < len(text) and m.start() > 0:
            gaps.append((m.start(), m.end()))
        pos = m.end()
    if pos < len(text):
        toks.append((pos, len(text)))
    gaps = gaps[:max(0, len(toks) - 1)]
    return toks, gaps


def _gap_kinds(words: list[str]) -> list[str]:
    kinds = [_gap_rule(words[k], words[k + 1]) for k in range(len(words) - 1)]
    # ranges: a dash between two numbers binds both sides
    for k in range(1, len(words) - 1):
        if words[k] in _DASH and _is_num(words[k - 1]) and _is_num(words[k + 1]):
            kinds[k - 1] = kinds[k] = "never"
    # short Latin runs: a run of Latin words (a number right after a Latin word joins it) of 2–3 words
    k = 0
    while k < len(words):
        if _latin_word(words[k]):
            j = k + 1
            while j < len(words) and (_latin_word(words[j]) or (_is_num(words[j]) and not _arabic_letters(words[j]))):
                j += 1
            if 2 <= j - k <= 3:
                for g in range(k, j - 1):
                    if kinds[g] == "ok":
                        kinds[g] = "avoid"
            k = j
        else:
            k += 1
    return kinds


def _phone_bound(text: str, gaps: list[tuple[int, int]], kinds: list[str]) -> list[str]:
    """A gap inside a phone number is "never". The spans and the gaps both come in text order: one sweep."""
    spans, out, q = phone_spans(text), [], 0
    for (g0, g1), k in zip(gaps, kinds):
        while q < len(spans) and spans[q][1] <= g1:
            q += 1
        out.append("never" if q < len(spans) and spans[q][0] < g0 and g1 < spans[q][1] else k)
    return out


def word_breaks(words: list[str]) -> list[str]:
    """For each gap between consecutive words: "never", "avoid" (inside a short Latin run) or "ok". For caption
    grouping (Task 23) and kinetic units (K-T5), which hold the words as a list."""
    words = [str(w).strip() for w in words]
    gaps, pos = [], 0
    for w in words[:-1]:
        pos += len(w)
        gaps.append((pos, pos + 1))
        pos += 1
    return _phone_bound(" ".join(words), gaps, _gap_kinds(words))


def breaks(text: str) -> list[tuple[int, int, str]]:
    """The break opportunities of a paragraph: (space start, space end, "ok" | "avoid"); a forbidden gap is absent."""
    toks, gaps = _tokens(text)
    kinds = _phone_bound(text, gaps, _gap_kinds([text[a:b] for a, b in toks]))
    return [(s, e, k) for (s, e), k in zip(gaps, kinds) if k != "never"]


BALANCE_MAX_BREAKS = 120     # above this many break opportunities `balanced` keeps the greedy lines (O(k · n²))


def wrap(text: str, max_width: float, measure=len, balanced: bool = False) -> list[tuple[int, int]]:
    """Line breaking: [(start, end)] per line, the breaking spaces left out. Greedy: the last "ok" break that fits
    wins; an "avoid" break is used only when no "ok" break fits; when nothing fits, the first "ok" break (else the
    first break), so a unit wider than `max_width` stays whole on its own line. `measure` must not shrink when the
    text grows (a width), so a line's candidates are measured only until one does not fit. `balanced` (graphics,
    AE-style titles): the same number of lines, with the breaks moved so the lines are as even as possible (see
    _balance); a paragraph with more than BALANCE_MAX_BREAKS break opportunities keeps the greedy lines."""
    if not max_width or max_width <= 0:
        raise ValueError("max_width must be positive")
    a = len(text) - len(text.lstrip(" \t"))
    z = len(text.rstrip(" \t"))
    if a >= z:
        return []
    opps = [o for o in breaks(text) if a < o[0] and o[1] <= z]
    next_ok = [len(opps)] * (len(opps) + 1)         # next_ok[q]: the first "ok" break at or after q
    for q in range(len(opps) - 1, -1, -1):
        next_ok[q] = q if opps[q][2] == "ok" else next_ok[q + 1]
    lines, start, nxt = [], a, 0                    # opps[nxt:] lie after `start`
    while True:
        last_ok = last_fit = None
        k = nxt
        while k < len(opps) and measure(text[start:opps[k][0]]) <= max_width:
            last_fit = k
            if opps[k][2] == "ok":
                last_ok = k
            k += 1
        if k == len(opps) and measure(text[start:z]) <= max_width:
            lines.append((start, z))
            break
        if nxt == len(opps):
            lines.append((start, z))                # nothing left to break at: the rest stays whole
            break
        if last_ok is not None:
            pick = last_ok
        elif last_fit is not None:
            pick = last_fit
        else:
            pick = next_ok[nxt] if next_ok[nxt] < len(opps) else nxt
        lines.append((start, opps[pick][0]))
        start, nxt = opps[pick][1], pick + 1
    if balanced and 1 < len(lines) and len(opps) <= BALANCE_MAX_BREAKS:
        lines = _balance(text, a, z, opps, len(lines), max_width, measure)
    return lines


def _balance(text, a, z, opps, k, max_width, measure):
    """The `k` lines with the best (overflowing lines, "avoid" breaks, overflow, sum of squared widths): the greedy
    breaks are one candidate, so the result never overflows on more lines or uses more "avoid" breaks than greedy, and
    among equals it is the most even. Dynamic programming over the break opportunities, O(k · n²) measures."""
    n = len(opps)
    starts = [a] + [o[1] for o in opps]                     # line start i: after break i-1 (0 = the text start)
    ends = [o[0] for o in opps] + [z]                       # line end j: at break j (n = the text end)
    memo: dict = {}

    def line(i, j):
        if (i, j) not in memo:
            w = float(measure(text[starts[i]:ends[j]]))
            over = max(0.0, w - max_width)
            memo[i, j] = (1 if over else 0, 0, over, w * w)
        return memo[i, j]

    def add(x, y, avoid=0):
        return (x[0] + y[0], x[1] + y[1] + avoid, x[2] + y[2], x[3] + y[3])
    best = {(1, j): (add(line(0, j), (0, 0, 0.0, 0.0), opps[j][2] == "avoid"), None) for j in range(n)}
    for m in range(2, k):
        for j in range(m - 1, n):
            cands = [(add(best[m - 1, i][0], line(i + 1, j), opps[j][2] == "avoid"), i)
                     for i in range(m - 2, j) if (m - 1, i) in best]
            if cands:
                best[m, j] = min(cands)
    finals = [(add(best[k - 1, i][0], line(i + 1, n)), i) for i in range(n) if (k - 1, i) in best]
    _, i = min(finals)
    cuts, m = [], k - 1
    while i is not None:
        cuts.append(i)
        i = best[m, i][1]
        m -= 1
    cuts.reverse()
    spans, st = [], 0
    for c in cuts:
        spans.append((starts[st], ends[c]))
        st = c + 1
    spans.append((starts[st], z))
    return spans


@dataclass(frozen=True)
class Line:
    text: str
    start: int
    end: int
    rtl: bool
    runs: list
    # the resolved hard segment the line was cut from, and the line's range in it (host_text needs the levels of the
    # characters that are never drawn too)
    par: Paragraph | None = field(default=None, repr=False, compare=False)
    par_start: int = field(default=0, repr=False, compare=False)
    par_end: int = field(default=0, repr=False, compare=False)


# hard breaks: the UAX #9 paragraph separators (class B: LF, CR, FS, GS, RS, NEL, PS), LS, and VT/FF (UAX #14 BK)
_HARD = re.compile(r"\r\n|[\n\r\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")


def lay_out(text: str, max_width: float | None = None, measure=len, force_rtl: bool = False,
            balanced: bool = False) -> list[Line]:
    """A caption or graphic paragraph as lines: the direction is decided once for the whole text (hard line breaks
    included), each hard segment is resolved with it, broken (when `max_width` is given), then each line reordered.
    A blank hard line stays one empty line. `max_width` None = no wrapping; 0 or less is refused, as in wrap()."""
    base = direction(text, force_rtl=force_rtl)
    out = []
    for seg_text, off in _hard_segments(text):
        par = paragraph(seg_text, base=base)
        spans = (wrap(seg_text, max_width, measure, balanced) if max_width is not None
                 else [(0, len(seg_text))]) or [(0, 0)]
        for s, e in spans:
            out.append(Line(seg_text[s:e], off + s, off + e, bool(base), line_runs(par, s, e), par, s, e))
    return out


def _hard_segments(text: str):
    pos = 0
    for m in _HARD.finditer(text):
        yield text[pos:m.start()], pos
        pos = m.end()
    yield text[pos:], pos


# --------------------------------------------------------------------------- digits and punctuation
_WEST, _ARAB, _PERS = "0123456789", "٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹"
_DG = "0-9٠-٩۰-۹"
_NUMBER = re.compile(rf"[{_DG}]{{1,3}}(?:[,٬][{_DG}]{{3}})+(?:[.٫][{_DG}]+)?[%٪]?|[{_DG}]+(?:[.٫][{_DG}]+)?[%٪]?")
_VERSION = re.compile(rf"(?<![{_DG}])[{_DG}]+(?:\.[{_DG}]+){{2,}}")      # starts at a digit run: linear
_GLUED_UNIT = re.compile(rf"^([(\[«\"']*)([{_DG}.,٫٬\-–]+)([A-Za-zµμ/]+)([.,;:!?)\]»\"'،؛؟]*)$")
_TO_AR = str.maketrans({**{w: a for w, a in zip(_WEST, _ARAB)}, **{p: a for p, a in zip(_PERS, _ARAB)},
                        ".": "٫", ",": "٬", "%": "٪"})
_TO_W = str.maketrans({**{a: w for w, a in zip(_WEST, _ARAB)}, **{p: w for w, p in zip(_WEST, _PERS)},
                       "٫": ".", "٬": ",", "٪": "%"})
_URLISH = re.compile(r"://|www\.|@|\.(com|net|org|io|ai|eg|sa|ae)\b", re.I)


def set_digits(text: str, style: str) -> str:
    """The client's digits (`style.json` `digits`): "western" (0-9) or "arabic" (٠-٩), with the number's decimal and
    thousands separators («1,500» ↔ «١٬٥٠٠») and percent sign. A number glued to a Latin unit converts («500mg» →
    «٥٠٠mg», so one line never mixes digits); a number that is part of a Latin name («COVID-19», «H1N1», «MP4»), a
    version («3.0.1»), a URL or an e-mail address keeps its characters. A comma that does not group thousands («5,6,7»)
    stays a comma. Idempotent."""
    if style not in ("western", "arabic"):
        raise ValueError("digits must be 'western' or 'arabic'")
    table = _TO_AR if style == "arabic" else _TO_W
    out, pos = [], 0
    for m in re.finditer(r"\S+", text):
        tok = m.group()
        out.append(text[pos:m.start()])
        g = _GLUED_UNIT.match(tok)
        if _VERSION.search(tok):
            out.append(tok)
        elif g and g.group(3).casefold() in _LATIN_UNITS:
            out.append(g.group(1) + _convert(g.group(2), table) + g.group(3) + g.group(4))
        elif _latin_letters(tok) or _URLISH.search(tok):
            out.append(tok)
        else:
            out.append(_convert(tok, table))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def _convert(tok: str, table) -> str:
    return _NUMBER.sub(lambda n: n.group().translate(table), tok)


_AR_PUNCT = {"،": ",", "؛": ";", "؟": "?"}
_LAT_PUNCT = {v: k for k, v in _AR_PUNCT.items()}


def punctuation_findings(text: str) -> list[dict]:
    """Arabic punctuation (، ؛ ؟) belongs to Arabic context only: findings for «،» in a Latin context and for «,» «;»
    «?» right after an Arabic word. Detect only; the text is never rewritten (the transcript is the editor's)."""
    out = []
    for i, ch in enumerate(text):
        if ch not in _AR_PUNCT and ch not in _LAT_PUNCT:
            continue
        if ch == "," and 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit():
            continue                                        # 1,000
        prev = next((c for c in reversed(text[:i]) if unicodedata.bidirectional(c) in ("L", "R", "AL")), None)
        arabic_before = prev is not None and unicodedata.bidirectional(prev) in ("R", "AL")
        if ch in _AR_PUNCT and prev is not None and not arabic_before and direction(text) == 0:
            out.append({"index": i, "char": ch, "suggest": _AR_PUNCT[ch], "why": "Arabic punctuation in a Latin line"})
        elif ch in _LAT_PUNCT and arabic_before:
            out.append({"index": i, "char": ch, "suggest": _LAT_PUNCT[ch], "why": "Latin punctuation after Arabic"})
    return out


_OVERRIDES = {"LRO", "RLO"}


def control_findings(text: str) -> list[dict]:
    """Explicit bidi controls in transcript or caption text (LRE, RLE, LRO, RLO, PDF, LRI, RLI, FSI, PDI): a pasted
    or hostile control silently changes what the viewer reads («خد [RLO]500 mg[PDF]» draws the dose as «gm 005»). The
    module honours them (X1–X10), so each one is a finding for the editor: an override (LRO, RLO) "reverses the text
    after it", the others "change the order". The directional marks (LRM, RLM, ALM) are not findings. Detect only; the
    text is never rewritten (the transcript is the editor's)."""
    out = []
    for i, ch in enumerate(text):
        c = _cls(ch)
        if c in _INVISIBLE:
            out.append({"index": i, "char": ch, "name": unicodedata.name(ch),
                        "why": "bidi override: reverses the text after it" if c in _OVERRIDES
                        else "bidi control: changes the order of the text around it"})
    return out
