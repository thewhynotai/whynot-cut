# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported unchanged from the owner's Kalam engine (kalam/captions.py); see adobe/tools/README.md
"""Pack phrases into captions: at most max_lines lines of max_line chars, voice-exact starts, no gaps."""
from .phrases import end_punct, make_phrase
from .similar import align_tokens, tokens as _norm_tokens
from .units import SOFT, is_whole_unit, touches_unit

MAX_LINE, MAX_LINES, MAX_DUR, STOP_PAUSE, TAIL = 32, 2, 4.5, 0.6, 0.3


def wrap(text: str, max_line: int = MAX_LINE, max_lines: int = MAX_LINES):
    """balanced line breaks, or None when the text cannot fit (a single over-long word gets its own line)"""
    words = text.split(" ")
    if len(text) <= max_line or len(words) == 1:
        return text
    if max_lines < 2:
        return None
    best = None
    for j in range(1, len(words)):
        a, b = " ".join(words[:j]), " ".join(words[j:])
        if len(a) <= max_line and len(b) <= max_line:
            cost = abs(len(a) - len(b)) + (40 if _latin(words[j - 1]) and _latin(words[j]) else 0)
            if best is None or cost < best[0]:
                best = (cost, a + "\n" + b)
    return best[1] if best else None


def _latin(word: str) -> bool:
    return any("A" <= c <= "Z" or "a" <= c <= "z" for c in word)


def fits(text: str, dur: float, max_line=MAX_LINE, max_lines=MAX_LINES, max_dur=MAX_DUR) -> bool:
    return dur <= max_dur and wrap(text, max_line, max_lines) is not None


def split_long(phrases: list, max_line=MAX_LINE, max_lines=MAX_LINES, max_dur=MAX_DUR) -> list:
    """split phrases that cannot be one caption at their biggest internal gap (ties: most balanced)"""
    out = []
    todo = list(phrases)
    while todo:
        p = todo.pop(0)
        ws = p["words"]
        if len(ws) < 2 or fits(p["text"], p["e"] - p["s"], max_line, max_lines, max_dur):
            out.append(p)
            continue
        total = len(p["text"])

        def key(j):
            left = len(" ".join(w["w"] for w in ws[:j]))
            bonus = {".": 0.2, ",": 0.1}.get(end_punct(ws[j - 1]["w"]), 0.0)
            return (round(ws[j]["s"] - ws[j - 1]["e"] + bonus, 2), -abs(2 * left - total))
        j = max(range(1, len(ws)), key=key)
        todo[0:0] = [make_phrase(ws[:j]), make_phrase(ws[j:])]
    return out


_ARTICLE_END = chr(0x640)   # "الـ" style article written before an English term


def _split_cost(tw: list, k: int, raw: list, r: int) -> float:
    """cost of breaking the (corrected) words tw before index k, which maps to raw word r"""
    cost = 0.0
    if _latin(tw[k - 1]) and _latin(tw[k]):
        cost += 40.0                                   # inside an English term
    if tw[k - 1].endswith(_ARTICLE_END):
        cost += 40.0                                   # "الـ | Fracture"
    if 0 < r < len(raw):
        cost -= 30.0 * max(0.0, raw[r]["s"] - raw[r - 1]["e"])   # real pauses are the best places
        cost -= {".": 3.0, ",": 1.5}.get(end_punct(raw[r - 1]["w"]), 0.0)
    return cost


def fit_phrases(phrases: list, max_line=MAX_LINE, max_lines=MAX_LINES, max_dur=MAX_DUR) -> list:
    """split phrases (whose text may have been corrected) so each part fits one caption.
    All breaks of a phrase are chosen together (fewest parts, best places: sentence ends, commas, real pauses),
    never inside an English term, and every part starts at the onset of the spoken word it begins with."""
    out = []
    for p in phrases:
        tw, raw = p["text"].split(" "), p.get("words") or []
        has_units = bool(p.get("unit_breaks"))
        if len(tw) < 2 or len(raw) < 2 or (not has_units and fits(p["text"], p["e"] - p["s"], max_line, max_lines, max_dur)):
            out.append(p)
            continue
        out.extend(_split_phrase(p, tw, raw, max_line, max_lines, max_dur))
    return out


def _split_phrase(p, tw, raw, max_line, max_lines, max_dur):
    n = len(tw)
    # which raw (spoken) word each corrected word came from, so breaks and times follow the voice
    link = align_tokens([(_norm_tokens(t) or [t])[0] for t in tw], [(_norm_tokens(w["w"]) or [w["w"]])[0] for w in raw])

    def raw_index(k):
        before = [j for j in link[:k] if j is not None]
        r = before[-1] + 1 if before else int(round(k * len(raw) / float(n)))
        return min(len(raw) - 1, max(1, r))
    start = [0] + [raw_index(k) for k in range(1, n)]          # raw word that corrected word k starts on

    def seg_time(i, j):
        s = p["s"] if i == 0 else raw[start[i]]["s"]
        e = p["e"] if j == n else raw[start[j] - 1]["e"]
        return s, max(e, s + 0.05)
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for i in range(n):
        if best[i] == float("inf"):
            continue
        for j in range(i + 1, n + 1):
            text = " ".join(tw[i:j])
            s, e = seg_time(i, j)
            line = int(max_line * SOFT) if (is_whole_unit(p, i, j, n) or touches_unit(p, i, j, n)) else max_line
            if j > i + 1 and not fits(text, e - s, line, max_lines, max_dur * SOFT):
                if len(text) > int(max_line * SOFT) * max_lines:
                    break
                continue
            cost = 2.0 + (1.5 if len(text) < 10 else 0.0) + (12.0 if len(text) <= 3 else 0.0)
            if j < n:
                cost += _split_cost(tw, j, raw, start[j])
                if p.get("unit_end") is not None:
                    cost += -6.0 if j in (p.get("unit_breaks") or set()) else 8.0
            if best[i] + cost < best[j]:
                best[j], back[j] = best[i] + cost, i
    cuts, j = [], n
    while j > 0:
        cuts.append((back[j], j))
        j = back[j]
    parts = []
    for i, j in reversed(cuts):
        s, e = seg_time(i, j)
        r0, r1 = (0 if i == 0 else start[i]), (len(raw) if j == n else start[j])
        b = p.get("unit_breaks") or set()
        parts.append({"text": " ".join(tw[i:j]), "s": s, "e": e, "words": raw[r0:r1],
                      "punct": p.get("punct", "") if j == n else end_punct(raw[r1 - 1]["w"]),
                      "unit_breaks": set(), "unit_end": None if p.get("unit_end") is None else (p["unit_end"] if j == n else j in b)})
    return parts


def _split_text_by_time(p: dict, max_line: int, max_lines: int) -> list:
    """a (corrected) phrase too long for one caption: cut its text at the most balanced word, time by char ratio"""
    words = p["text"].split(" ")
    total = len(p["text"])
    j = min(range(1, len(words)), key=lambda k: abs(2 * len(" ".join(words[:k])) - total))
    a, b = " ".join(words[:j]), " ".join(words[j:])
    t = p["s"] + (p["e"] - p["s"]) * (len(a) + 1) / (total + 1)
    parts = [{"text": a, "s": p["s"], "e": t, "words": []}, {"text": b, "s": t, "e": p["e"], "words": []}]
    out = []
    for q in parts:
        if wrap(q["text"], max_line, max_lines) is None and " " in q["text"]:
            out.extend(_split_text_by_time(q, max_line, max_lines))
        else:
            out.append(q)
    return out


def pack(phrases: list, max_line=MAX_LINE, max_lines=MAX_LINES, max_dur=MAX_DUR,
         stop_pause=STOP_PAUSE, tail=TAIL) -> list:
    items = []
    for p in phrases:
        whole = p.get("unit_end") is True and not p.get("unit_breaks")
        limit = int(max_line * SOFT) if whole else max_line
        if wrap(p["text"], limit, max_lines) is None:
            items.extend(_split_text_by_time(p, max_line, max_lines))
        else:
            items.append(p)
    groups = _best_groups(items, max_line, max_lines, max_dur, stop_pause)
    caps = []
    for k, g in enumerate(groups):
        end = groups[k + 1]["s"] if k + 1 < len(groups) else g["e"] + tail
        text = wrap(g["text"], max_line, max_lines) or wrap(g["text"], int(max_line * SOFT), max_lines) or g["text"]
        caps.append({"text": text, "s": g["s"], "e": end})
    return caps


def _break_cost(p: dict, gap: float, stop_pause: float) -> float:
    """cost of ending a caption after phrase p: sentence ends are good, breaths inside a sentence are bad"""
    if p.get("unit_end") is True:
        return -4.0                                    # a meaning unit ends here
    if p.get("unit_end") is False and gap < stop_pause:
        return 6.0                                     # the sentence goes on: keep it in one caption
    if gap >= stop_pause or p.get("punct") == ".":
        return -1.0
    if p.get("punct") == ",":
        return 0.5
    return 3.0 - min(2.5, gap * 5)


def _best_groups(items: list, max_line, max_lines, max_dur, stop_pause) -> list:
    """choose all caption breaks at once (dynamic programming) instead of filling captions greedily"""
    n = len(items)
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for i in range(n):
        if best[i] == float("inf"):
            continue
        text = ""
        for j in range(i, n):
            if j > i and items[j]["s"] - items[j - 1]["e"] >= stop_pause:
                break
            text = items[j]["text"] if j == i else text + " " + items[j]["text"]
            one_unit = j > i and items[j].get("unit_end") is True and all(x.get("unit_end") is False for x in items[i:j])
            line = int(max_line * SOFT) if one_unit else max_line
            if j > i and not fits(text, items[j]["e"] - items[i]["s"], line, max_lines, max_dur * (SOFT if one_unit else 1)):
                if len(text) > int(max_line * SOFT) * max_lines:
                    break
                continue
            cost = (1.5 if len(text) < 10 else 0.0) + (12.0 if len(text) <= 3 else 0.0)
            if j + 1 < n:
                cost += _break_cost(items[j], items[j + 1]["s"] - items[j]["e"], stop_pause)
            if best[i] + cost < best[j + 1]:
                best[j + 1], back[j + 1] = best[i] + cost, i
    groups, j = [], n
    while j > 0:
        i = back[j]
        groups.append({"text": " ".join(p["text"] for p in items[i:j]), "s": items[i]["s"], "e": items[j - 1]["e"]})
        j = i
    return groups[::-1]


def _tc(t: float) -> str:
    ms = int(round(t * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def to_srt(captions: list) -> str:
    return "\n".join("%d\n%s --> %s\n%s\n" % (i + 1, _tc(c["s"]), _tc(c["e"]), c["text"])
                     for i, c in enumerate(captions))
