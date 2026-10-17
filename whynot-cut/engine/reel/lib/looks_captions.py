# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Caption looks (R-4.1, Phase 4 Task 23): the words become on-screen captions in a caption look.

Text core: digits follow the client's digit set inside Arabic runs only, the spoken words are grouped (word, phrase
or line), the protected pairs stay whole (a Latin run, a number and its unit, «ال» + a Latin term), the emphasised
words are marked, and words a graphic already shows are never captioned twice.
Spec: docs/superpowers/specs/addendum-h/source-r-specs/R-4.1-caption-looks.md.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import looks
from .common import fmt_ts
from .looks_type import (CTEngine, HBEngine, Typesetter, floor_px, font_chain, hb_available, house_faces,  # noqa: F401
                         pick_engine, safe_width)
from .looks_paint import CaptionPainter, step_to_contrast  # noqa: F401
from .motion_layout import UNITS, _latin, _NUMBER

# --------------------------------------------------------------------------- digits
_AR_LETTER = re.compile("[ء-يٮ-ۓۺ-ۿݐ-ݿࢠ-ࣿ]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
_WEST_TO_AI = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_AI_TO_WEST = str.maketrans("٠١٢٣٤٥٦٧٨٩"
                            "۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ANY_DIGIT = re.compile("[0-9٠-٩۰-۹]")
# a number as written in speech captions: digits with . , as separators and an optional percent sign
_NUM_TOKEN = re.compile("^([(\\[«\"']*)([0-9٠-٩۰-۹]+(?:[.,٫٬][0-9٠-٩۰-۹]+)*)"
                        "([%٪]?)([)\\]»\"'.,:;!?،؛؟…]*)$")


def _strong(tok: str) -> str | None:
    """'R' for a token with Arabic letters, 'L' for one with Latin letters (or a handle, URL, address), else None."""
    if _LATIN_LETTER.search(tok) or "@" in tok or "/" in tok or "_" in tok:
        return "L"
    if _AR_LETTER.search(tok):
        return "R"
    return None


def _convert_number(core: str, pct: str, digits: str) -> str:
    if digits == "arabic_indic":
        out = core.translate(_WEST_TO_AI)
        out = re.sub("(?<=[٠-٩])\\.(?=[٠-٩])", "٫", out)      # decimal point ٫
        out = re.sub("(?<=[٠-٩]),(?=[٠-٩])", "٬", out)        # thousands ٬
        return out + ("٪" if pct else "")
    out = core.translate(_AI_TO_WEST).replace("٫", ".").replace("٬", ",")
    return out + ("%" if pct else "")


def localize_digits(text: str, digits: str | None) -> str:
    """Digits in the client's digit set ("arabic_indic" or "western"), converted ONLY inside Arabic runs: a number
    token whose neighbouring strong tokens are Arabic (none on one side is fine). A number beside a Latin term
    ("iPhone 15 Pro"), and every Latin run, model or product name, handle, URL, e-mail address, file name and version
    string keep their digits. With Arabic-Indic digits: ٫ decimal point, ٬ thousands, and the percent sign ٪ stored
    after the digits ("40%" → U+0664 U+0660 U+066A). A line with no Arabic never changes."""
    if digits not in ("arabic_indic", "western") or not text or not _AR_LETTER.search(text):
        return text
    toks = text.split(" ")
    strong = [_strong(t) for t in toks]
    out = list(toks)
    for i, tok in enumerate(toks):
        m = _NUM_TOKEN.match(tok)
        if not m or strong[i] is not None:
            continue
        prev = next((s for s in reversed(strong[:i]) if s), None)
        nxt = next((s for s in strong[i + 1:] if s), None)
        if "L" in (prev, nxt) or not (prev == "R" or nxt == "R"):
            continue
        lead, core, pct, trail = m.groups()
        if core.count(".") + core.count("٫") > 1:      # 3.0.1: a version string, never a number
            continue
        out[i] = lead + _convert_number(core, pct, digits) + trail
    return " ".join(out)


# --------------------------------------------------------------------------- glue
_SENT_END = (".", "?", "!", "؟", "…", "۔")
_CLAUSE = (",", "،", "؛", ";", ":") + _SENT_END
_PUNCT_STRIP = "()[]«»\"'.,:;!?،؛؟…۔"


def _bare(tok: str) -> str:
    return tok.strip(_PUNCT_STRIP)


def _units() -> set:
    extra = (looks.caption_catalog().get("glue") or {}).get("units_extra") or []
    return {u.lower() for u in UNITS} | {str(u).lower() for u in extra}


LATIN_RUN_MAX = 3          # a Latin TERM inside Arabic speech ("insulin resistance"); a longer run is a sentence


def glued(words: list[dict], arabic: bool | None = None) -> list[list[dict]]:
    """The words in groups that are never split across captions or lines: a number and its unit, «ال» / «الـ» + a
    Latin term, and, in Arabic speech, a Latin term of up to LATIN_RUN_MAX words (the motion_layout.glue rules, plus
    the catalog's extra units). Never across punctuation; an English transcript glues numbers and units only
    (`arabic` overrides that test, e.g. for one cue of an Arabic transcript). Words carry "word" (or "text").
    Empty words are dropped."""
    units = _units()
    tok_of = lambda w: str(w.get("word", w.get("text")) or "").strip()
    if arabic is None:
        arabic = any(_AR_LETTER.search(tok_of(w)) for w in words)
    out: list[list[dict]] = []
    for w in words:
        tok = tok_of(w)
        if not tok:
            continue
        if out:
            raw_prev = tok_of(out[-1][-1])
            prev, cur = _bare(raw_prev), _bare(tok)
            after_punct = raw_prev != raw_prev.rstrip(_PUNCT_STRIP)
            grp = [_bare(tok_of(x)) for x in out[-1]]
            n_latin = sum(1 for x in grp if _latin(x))
            term = n_latin > 0 and all(_latin(x) or _NUMBER.match(x) or x in ("ال", "الـ") for x in grp)
            # a Latin term (a model number inside it too: "iPhone 15 Pro Max") of up to LATIN_RUN_MAX Latin words
            latin_run = (arabic and _latin(cur) and term and (_latin(prev) or bool(_NUMBER.match(prev)))
                         and n_latin < LATIN_RUN_MAX)
            name_number = (arabic and _latin(prev) and bool(_NUMBER.match(cur)) and term
                           and not any(_NUMBER.match(x) for x in grp))
            # a unit on its number, a name before it too: "covid 19 سنة" and "Pro Max 15 سنة" stay whole (nothing
            # tells the two apart; gluing never makes a wrong split, fit-or-fail handles the longer run)
            unit = bool(_NUMBER.match(prev)) and cur.lower() in units
            if not after_punct and (latin_run or name_number or unit or (prev in ("ال", "الـ") and _latin(cur))):
                out[-1].append(w)
                continue
        out.append([w])
    return out


# --------------------------------------------------------------------------- grouping
def _cue(groups: list[list[dict]]) -> dict:
    ws = [w for g in groups for w in g]
    return {"start_ms": int(ws[0]["start_ms"]), "end_ms": int(ws[-1]["end_ms"]),
            "words": [{"id": w.get("id"), "text": str(w["word"]).strip(), "start_ms": int(w["start_ms"]),
                       "end_ms": int(w["end_ms"])} for w in ws],
            "text": " ".join(str(w["word"]).strip() for w in ws), "emphasis": []}


def _spans(groups: list[list[dict]], pause_ms: int, clause: bool) -> list[list[list[dict]]]:
    """Runs of glued groups between hard breaks: a pause of at least `pause_ms`, a sentence end, a new transcript
    segment, and (clause=True) clause punctuation, Arabic marks included."""
    spans, cur = [], []
    for g in groups:
        if cur:
            gap = g[0]["start_ms"] - cur[-1][-1]["end_ms"]
            seg = g[0].get("segment_id") is not None and g[0].get("segment_id") != cur[-1][-1].get("segment_id")
            if gap >= pause_ms or seg:
                spans.append(cur)
                cur = []
        cur.append(g)
        last = str(g[-1]["word"]).rstrip("\"'»)]")
        if last.endswith(_SENT_END) or (clause and last.endswith(_CLAUSE)):
            spans.append(cur)
            cur = []
    if cur:
        spans.append(cur)
    return spans


def _partition(span: list[list[dict]], max_words: int) -> list[list[list[dict]]]:
    """Split a span of glued groups into the fewest chunks of at most `max_words` words (a glued group longer than
    that is a chunk of its own), as balanced as possible (no orphan word when it can be helped)."""
    sizes = [len(g) for g in span]
    n = len(span)
    best: dict = {n: (0, 0, max_words, [])}     # i -> (chunks, largest, smallest, cuts) for span[i:]
    for i in range(n - 1, -1, -1):
        opts, total = [], 0
        for j in range(i + 1, n + 1):
            total += sizes[j - 1]
            if total > max_words and j > i + 1:
                break
            k, mx, mn, cuts = best[j]
            opts.append((k + 1, max(mx, total), min(mn, total), [j] + cuts))
        best[i] = min(opts, key=lambda o: (o[0], o[1], -o[2]))
    out, i = [], 0
    for j in best[0][3]:
        out.append(span[i:j])
        i = j
    return out


def _min_ms(grouping: str, cat: dict) -> int:
    return int((cat["groupings"].get(grouping) or {}).get("min_ms", 300))


def _hold(cues: list[dict], grouping: str, cat: dict) -> list[dict]:
    """Hold a short cue to the grouping's minimum time, never into the next cue; never move a start."""
    m = _min_ms(grouping, cat)
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start_ms"] if i + 1 < len(cues) else None
        if c["end_ms"] - c["start_ms"] < m:
            c["end_ms"] = c["start_ms"] + m if nxt is None else min(c["start_ms"] + m, nxt)
        if nxt is not None and c["end_ms"] > nxt:
            c["end_ms"] = nxt
    return cues


def group_words(words: list[dict], grouping: str, cat: dict | None = None) -> list[dict]:
    """On-screen caption cues from timed words (sequence clock), in spoken (logical) order:
    word = one glued group per cue; phrase = 2-4 words, never across a pause of `pause_break_ms` or a sentence end,
    broken at clause punctuation; line = a clause (broken at clause punctuation and at a pause of `pause_break_ms`;
    a line wider than the safe width is re-grouped by fit()). -> [{start_ms, end_ms, words, text, emphasis}]."""
    cat = cat or looks.caption_catalog()
    if grouping not in cat["groupings"]:
        raise looks.LookError(f"unknown caption grouping {grouping!r}")
    cfg = cat["groupings"][grouping]
    groups = glued(sorted((w for w in words if str(w.get("word") or "").strip()), key=lambda w: w["start_ms"]))
    if not groups:
        return []
    if grouping == "word":
        cues = [_cue([g]) for g in groups]
    elif grouping == "phrase":
        cues = [_cue(chunk) for span in _spans(groups, int(cfg.get("pause_break_ms", 250)), clause=True)
                for chunk in _partition(span, int(cfg.get("max_words", 4)))]
    else:
        max_ms = int(cfg.get("max_ms") or 0)
        cues = [_cue(part) for span in _spans(groups, int(cfg.get("pause_break_ms", 350)), clause=True)
                for part in _split_long(span, max_ms)]
    return _hold(cues, grouping, cat)


def _split_long(span: list[list[dict]], max_ms: int) -> list[list[list[dict]]]:
    """A line longer than `max_ms` split at its longest pause (the middle when the pauses are even), until each part
    fits the time or is one glued group."""
    if not max_ms or len(span) < 2 or span[-1][-1]["end_ms"] - span[0][0]["start_ms"] <= max_ms:
        return [span]
    gaps = [(span[k][0]["start_ms"] - span[k - 1][-1]["end_ms"], -abs(2 * k - len(span)), k) for k in range(1, len(span))]
    k = max(gaps)[2]
    return _split_long(span[:k], max_ms) + _split_long(span[k:], max_ms)


# --------------------------------------------------------------------------- emphasis, hidden ranges, lead-in
def _norm(s: str) -> str:
    from .plan import norm
    return norm(s)


def mark_emphasis(cues: list[dict], highlights: list[str]) -> list[dict]:
    """Mark the words of each cue that a highlight phrase names (normalised, contiguous words) in cue["emphasis"]
    (word indices into cue["words"])."""
    phrases = [p.split() for p in (_norm(h) for h in highlights or []) if p]
    for c in cues:
        toks = [_norm(w["text"]) for w in c["words"]]
        marked = set()
        for ph in phrases:
            k = len(ph)
            for i in range(len(toks) - k + 1):
                if toks[i:i + k] == ph:
                    marked.update(range(i, i + k))
        c["emphasis"] = sorted(marked)
    return cues


def apply_hidden(cues: list[dict], hidden_ms: list, grouping: str, cat: dict | None = None,
                 min_keep_ms: int = 250) -> list[dict]:
    """Drop the words a graphic already shows: a word whose middle falls inside a hidden range is not captioned, and a
    cue split by a hidden range becomes two cues; times are kept out of the hidden ranges. Cues shorter than
    `min_keep_ms` after that are dropped (as today)."""
    cat = cat or looks.caption_catalog()
    ranges = sorted((int(a), int(b)) for a, b in hidden_ms or [] if b > a)
    if not ranges:
        return cues

    def hidden(w):
        mid = (w["start_ms"] + w["end_ms"]) / 2
        return any(a <= mid < b for a, b in ranges)
    out = []
    for c in cues:
        parts, part = [], []                          # runs of shown word indices
        for i, w in enumerate(c["words"]):
            if hidden(w):
                if part:
                    parts.append(part)
                part = []
            else:
                part.append(i)
        if part:
            parts.append(part)
        last = len(c["words"]) - 1
        for idx in parts:
            p = [c["words"][i] for i in idx]
            n = dict(c, words=p, text=" ".join(w["text"] for w in p), start_ms=p[0]["start_ms"],
                     end_ms=c["end_ms"] if idx[-1] == last else p[-1]["end_ms"],
                     emphasis=[idx.index(i) for i in c.get("emphasis", []) if i in idx])
            for a, b in ranges:
                if a <= n["start_ms"] < b:
                    n["start_ms"] = b
                elif n["start_ms"] < a < n["end_ms"]:
                    n["end_ms"] = a
            out.append(n)
    out = _hold(out, grouping, cat)
    for i, n in enumerate(out):                       # a hold never runs into a hidden range
        for a, b in ranges:
            if n["start_ms"] < a < n["end_ms"]:
                n["end_ms"] = a
    return [n for n in out if n["end_ms"] - n["start_ms"] >= min_keep_ms]


def apply_lead_in(cues: list[dict], lead_ms: int, hidden: list | None = None) -> list[dict]:
    """A caption may appear up to `lead_ms` before its first word, never over the previous caption and never back
    into a hidden range (a graphic that shows the words). New cue dicts."""
    out, prev_end = [], 0
    for c in cues:
        n = dict(c)
        if lead_ms:
            s = max(prev_end, c["start_ms"] - int(lead_ms), 0)
            for a, b in hidden or []:
                if a <= s < b <= c["start_ms"]:
                    s = b
            n["start_ms"] = s
        prev_end = n["end_ms"]
        out.append(n)
    return out


# --------------------------------------------------------------------------- fit-or-fail
def _sub(c: dict, idx: list[int], first: bool, last: bool) -> dict:
    ws = [c["words"][i] for i in idx]
    return dict(c, words=ws, text=" ".join(w["text"] for w in ws),
                start_ms=c["start_ms"] if first else ws[0]["start_ms"], end_ms=c["end_ms"] if last else ws[-1]["end_ms"],
                emphasis=[idx.index(i) for i in c.get("emphasis", []) if i in idx])


def fit_cues(cues: list[dict], look: str, chain: dict, frame_w: int, safe_w: float, engine=None, cat: dict | None = None,
             heavy: dict | None = None, emphasis_mode: str | None = None,
             arabic: bool | None = None) -> tuple[list[dict], list[dict]]:
    """Fit-or-fail (R-4.1 §6): every caption is measured with the client's real fonts against the safe width.
    1. re-group: a caption too wide is split at the best word boundary (after clause punctuation, then before a
       conjunction, then at the longest pause of at least `regroup_pause_ms`, then where the two halves balance),
       never inside a glued run, until each part fits or is one glued run;
    2. shrink: that run's size drops in steps of `shrink_step_px` down to the floor (floor_px);
    3. hide and report: still too wide at the floor, that one caption is hidden (its words stay in the transcript).
    Characters no font can draw are reported (U+XXXX with the cue time). -> (cues with size and hidden, notices)."""
    cat = cat or looks.caption_catalog()
    lk = cat["looks"][looks.legacy_look(look, cat)]
    fit = cat.get("fit") or {}
    scale = frame_w / 1080
    size0 = int(round(lk["size"] * scale))
    floor = floor_px(lk["size"], frame_w)
    step = float(fit.get("shrink_step_px", 2))
    pause_min = int(fit.get("regroup_pause_ms", 150))
    conj = {str(x).lower() for x in ((cat["groupings"].get("line") or {}).get("conjunctions") or [])}
    tag = (cat.get("emphasis") or {}).get("tag") or {}
    tag_pad, tag_em = float(tag.get("pad_x_px", 10)), tag.get("pad_em")
    if arabic is None:
        arabic = any(_AR_LETTER.search(w["text"]) for c in cues for w in c["words"])
    setters: dict = {}

    def ts(size):
        if size not in setters:
            setters[size] = Typesetter(chain, size, engine=engine, heavy=heavy, tag_pad_px=tag_pad, scale=scale,
                                       tag_pad_em=tag_em)
        return setters[size]

    def width(c, idx, size):
        texts = [c["words"][i]["text"] for i in idx]
        emph = {idx.index(i) for i in c.get("emphasis", []) if i in idx}
        return ts(size).line(texts, emphasis=emph, mode=emphasis_mode)["w"]

    def regroup(c, groups):
        idx = [i for g in groups for i in g]
        if len(groups) < 2 or width(c, idx, size0) <= safe_w:
            return [idx]
        cands = []
        for k in range(1, len(groups)):
            left_last = c["words"][groups[k - 1][-1]]["text"].rstrip("\"'»)]")
            right_first = _bare(c["words"][groups[k][0]]["text"]).lower()
            gap = c["words"][groups[k][0]]["start_ms"] - c["words"][groups[k - 1][-1]]["end_ms"]
            cls = 0 if left_last.endswith(_CLAUSE) else 1 if right_first in conj else 2 if gap >= pause_min else 3
            cands.append((cls, k, gap))
        best_cls = min(x[0] for x in cands)
        pool = [x for x in cands if x[0] == best_cls]
        if best_cls == 2:
            top = max(x[2] for x in pool)
            pool = [x for x in pool if x[2] == top]

        def balance(k):
            a = [i for g in groups[:k] for i in g]
            b = [i for g in groups[k:] for i in g]
            return max(width(c, a, size0), width(c, b, size0))
        k = min(pool, key=lambda x: (balance(x[1]), x[1]))[1]
        return regroup(c, groups[:k]) + regroup(c, groups[k:])

    out, notes = [], []
    for c in cues:
        ln = ts(size0).line([w["text"] for w in c["words"]])
        for m in ln["missing"]:
            notes.append({"kind": "missing_glyph", "char": m, "at_ms": c["start_ms"], "text": c["text"],
                          "message": f"caption at {fmt_ts(c['start_ms'], '.')}: {m} is in no caption font (it is "
                                     f"left out): add a font that has it to the client's fonts"})
        wrapped = [{"text": w["text"], "_i": i} for i, w in enumerate(c["words"])]
        groups = [[x["_i"] for x in g] for g in glued(wrapped, arabic=arabic)]
        parts = regroup(c, groups)
        if len(parts) > 1:
            notes.append({"kind": "regrouped", "at_ms": c["start_ms"], "text": c["text"], "parts": len(parts),
                          "message": f"caption at {fmt_ts(c['start_ms'], '.')} split into {len(parts)} to fit the safe "
                                     "width"})
        for k, idx in enumerate(parts):
            part = _sub(c, idx, k == 0, k == len(parts) - 1)
            if k < len(parts) - 1:                     # the next part takes over at once: no blank frames between
                part["end_ms"] = c["words"][parts[k + 1][0]]["start_ms"]
            size = float(size0)
            fits = width(c, idx, size) <= safe_w
            while not fits and size - step >= floor - 1e-9:
                size -= step
                fits = width(c, idx, size) <= safe_w
            part["size"] = int(size) if size.is_integer() else size
            if fits and size != size0:
                notes.append({"kind": "shrunk", "at_ms": part["start_ms"], "text": part["text"], "from": size0,
                              "to": part["size"], "message": f"caption at {fmt_ts(part['start_ms'], '.')} drawn at "
                                                              f"{part['size']} px instead of {size0} px to fit"})
            if not fits:
                part["hidden"] = True
                notes.append({"kind": "hidden", "at_ms": part["start_ms"], "text": part["text"],
                              "message": f"caption at {fmt_ts(part['start_ms'], '.')} is too long for one line and "
                                         "was hidden: choose `word` grouping or a narrower look"})
            out.append(part)
    return out, notes


# --------------------------------------------------------------------------- the clip's words on the sequence clock
def seq_words(paths, spec: dict) -> list[dict]:
    """The clip's spoken words on the SEQUENCE clock: `02_transcription/words-seq.json` when the plan wrote it, else
    words.json mapped through the spec's time map (pause removal, word cuts; removed and cut words dropped), else
    words.json as it is. Each mapped word keeps its source times (src_start_ms / src_end_ms)."""
    from .common import read_json
    seq = read_json(paths.p("02_transcription/words-seq.json"))
    if seq and seq.get("words") is not None:
        return [w for w in seq["words"] if str(w.get("word") or "").strip()]
    doc = read_json(paths.p("02_transcription/words.json"), {}) or {}
    words = [dict(w, src_start_ms=w["start_ms"], src_end_ms=w["end_ms"]) for w in doc.get("words") or []
             if str(w.get("word") or "").strip()]
    tm = (spec or {}).get("time_map")
    if not tm:
        return words
    from .timemap import TimeMap
    tmap = TimeMap(tm["keep_ms"])
    cut = {c.get("word_id") for c in tm.get("words_cut") or []}
    return [dict(w, start_ms=round(tmap.ms(w["start_ms"])), end_ms=round(tmap.ms(w["end_ms"]))) for w in words
            if w.get("id") not in cut and not tmap.removed(w["start_ms"], w["end_ms"])]


def _tidy(cue: dict, digits: str | None, strip: str | None) -> dict:
    """The cue's words as shown: the client's digit set (inside Arabic runs only) and the punctuation the client's
    caption style removes ("..." becomes "…" first, as in previews.caption_text). Words left empty are dropped."""
    texts = [w["text"] for w in cue["words"]]
    loc = localize_digits(" ".join(texts), digits).split(" ")
    if len(loc) == len(texts):
        texts = loc
    keep, emph, new_i = [], [], {}
    for i, (w, t) in enumerate(zip(cue["words"], texts)):
        if strip:
            t = "".join(ch for ch in t.replace("...", "…") if ch not in strip)
        if not t.strip():
            continue
        new_i[i] = len(keep)
        keep.append(dict(w, text=t))
    emph = [new_i[i] for i in cue.get("emphasis", []) if i in new_i]
    return dict(cue, words=keep, text=" ".join(w["text"] for w in keep), emphasis=emph)


def _frame_source(paths, spec: dict, size: tuple, needed: bool):
    """frame_at(cue) -> the source frame behind a caption (for the contrast checks), taken at the caption's own middle
    (source time; at most one grab per 500 ms, captions in the same 500 ms share it), None when there is no footage or
    the look does not need it. Only the latest frame is kept (a full frame is megabytes: G10 on small machines)."""
    if not needed:
        return lambda cue: None
    try:
        from .common import spec_footage
        main = spec_footage(paths, spec)
    except Exception:  # noqa: BLE001  no footage named: contrast against the plate only
        return lambda cue: None
    if not Path(main).exists():
        return lambda cue: None
    from .previews import grab_frame
    cache: dict = {}
    offset = int(spec.get("source_in_ms") or 0)

    def frame_at(cue):
        ws = cue["words"]
        src = [w.get("src_start_ms", w["start_ms"]) for w in ws] + [w.get("src_end_ms", w["end_ms"]) for w in ws]
        mid = (min(src) + max(src)) // 2 if src else cue["start_ms"]
        key = mid // 500
        if key not in cache:
            cache.clear()
            cache[key] = None                 # the old frame is let go before the next grab
            try:
                cache[key] = grab_frame(main, mid + offset, size)
            except Exception:  # noqa: BLE001  an unreadable frame: no frame check for this caption
                cache[key] = None
        return cache[key]
    return frame_at


def _t42_highlight(spec: dict) -> tuple | None:
    """The client's (or the reel's) highlight colour as `reel plan` resolved it (T4.2: the compiled spec's
    style.highlight.hex, there only when it is not the brand default); None = the brand highlight."""
    style = (spec or {}).get("style")
    hl = style.get("highlight") if isinstance(style, dict) else None
    hx = str(hl.get("hex") or "") if isinstance(hl, dict) else ""
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", hx):
        return tuple(int(hx[i:i + 2], 16) for i in (1, 3, 5))
    return None


def _caption_fonts(paths, emphasis: str | None) -> tuple[dict, dict | None]:
    from .common import read_json
    typ = read_json(paths.client_db / "branding/typography.json", {}) or {}
    chain = font_chain(typ, "caption")
    step = int(((looks.caption_catalog().get("emphasis") or {}).get("weight") or {}).get("step_weight", 200))
    heavy = font_chain(typ, "caption", weight_step=step) if emphasis == "weight" else None
    return chain, heavy


def _localized(words: list[dict], digits: str | None) -> list[dict]:
    """The words with the client's digit set, judged on the whole transcript (a one-word caption still knows it sits
    in Arabic speech)."""
    if digits not in ("arabic_indic", "western") or not words:
        return words
    toks = [str(w.get("word") or "").strip() for w in words]
    loc = localize_digits(" ".join(toks), digits).split(" ")
    if len(loc) != len(toks):
        return words
    return [dict(w, word=t) if t != o else w for w, t, o in zip(words, loc, toks)]


UNAVAILABLE = ("caption looks need a text engine and a caption font (HarfBuzz, or CoreText on a Mac, and the client's "
               "or a house font): today's captions are used for this clip")


def _available(chain: dict) -> bool:
    from .looks_type import hb_available
    from . import ct_text
    return bool(chain.get("arabic") or chain.get("latin")) and (hb_available() or ct_text.AVAILABLE)


def _fitted(paths, spec: dict, resolved: dict, hidden_ms: list, cat: dict, W: int):
    """The clip's caption cues in the resolved look, grouped, emphasised, trimmed, tidied and fitted (no drawing).
    -> (cues, notices, chain, heavy)."""
    from .common import load_config
    grouping, emphasis = resolved["grouping"], resolved["emphasis"]
    tpl = (load_config("graphics-templates.json").get("templates") or {}).get("highlight_caption") or {}
    cues = group_words(_localized(seq_words(paths, spec), resolved.get("digits")), grouping, cat)
    mark_emphasis(cues, [h.get("text", "") for h in spec.get("caption_highlights", [])])
    cues = apply_lead_in(apply_hidden(cues, hidden_ms, grouping, cat), int(tpl.get("lead_in_ms") or 0), hidden_ms)
    cues = [c for c in (_tidy(c, None, tpl.get("strip_punctuation")) for c in cues) if c["words"]]
    chain, heavy = _caption_fonts(paths, emphasis)
    notices = [{"kind": "font", "message": n} for n in chain.get("notes", []) + (heavy or {}).get("notes", [])]
    cues, fit_notes = fit_cues(cues, resolved["look"], chain, W, safe_width(W), cat=cat, heavy=heavy,
                               emphasis_mode=emphasis)
    return cues, notices + fit_notes, chain, heavy


def plan_check(paths, spec: dict, resolved: dict, hidden_ms: list | None = None) -> list[str]:
    """For `reel plan` (R-4.1 §6): the fit-or-fail notices of the clip's captions in the resolved look (hidden
    captions, shrunk or split ones, characters no font has, as U+XXXX with the cue time), measured with the client's
    real fonts, without drawing anything. [] when the look is None (today's captions)."""
    if not resolved or not resolved.get("look"):
        return []
    from .common import frame_size
    W, _ = frame_size(paths)
    if not _available(_caption_fonts(paths, None)[0]):
        return [UNAVAILABLE]
    _, notices, _, _ = _fitted(paths, spec, resolved, hidden_ms or [], looks.caption_catalog(), W)
    out = []
    for n in notices:
        if n["message"] not in out:
            out.append(n["message"])
    return out


def render_captions(paths, resolved: dict, hidden_ms: list, avoid: list | None = None,
                    warnings: list | None = None) -> list[dict]:
    """The caption stills of one clip in its resolved caption look (looks.resolve), on the SEQUENCE clock, into
    03_broll/captions (as today's captions): per caption CAP_###_fg.png (text and static emphasis), CAP_###_plate.png
    (every look) and CAP_###_band.png + word spans (highlight), and captions-manifest.json with the look, the
    motion and the fit-or-fail notices. Words a graphic shows (hidden_ms) are not captioned; `avoid` moves a caption
    off a card. The notices also go to `warnings`. Nothing is written when the look is None (today's captions: []),
    and None comes back (with a warning) when no text engine or caption font is available, so the caller draws
    today's captions instead (G10: never a build without captions)."""
    if not resolved or not resolved.get("look"):
        return []
    from .common import frame_size, now_iso, write_json
    from .previews import save_still
    from .stamps import read_compiled
    spec = read_compiled(paths.p("01_analysis/timeline-spec.json")) or {}
    cat = looks.caption_catalog()
    look, emphasis = resolved["look"], resolved["emphasis"]
    W, H = frame_size(paths)
    if not _available(_caption_fonts(paths, None)[0]):
        if warnings is not None and UNAVAILABLE not in warnings:
            warnings.append(UNAVAILABLE)
        return None
    cues, notices, chain, heavy = _fitted(paths, spec, resolved, hidden_ms, cat, W)
    painter = CaptionPainter(look, chain, looks.palette(paths.client_db), (W, H), heavy=heavy, emphasis=emphasis,
                             cat=cat, entrance=(resolved.get("motion") or {}).get("entrance"),
                             highlight=_t42_highlight(spec))
    motion = painter.motion(float(spec.get("fps") or 30))
    frame_at = _frame_source(paths, spec, (W, H), painter.look["presentation"] != "boxed")
    out_dir = paths.p("03_broll/captions")
    out_dir.mkdir(parents=True, exist_ok=True)
    items = []
    shown = [k for k in cues if not k.get("hidden")]
    # pass 1: what each caption needs, keeping only the strip colours behind it (never the frames)
    meas = [painter.scrim_for(c, frame=frame_at(c), avoid=avoid) for c in shown]
    # the scrim is steady: each caption takes the strongest one any caption within steady_ms needs (no pumping)
    sc = ((painter.pres.get("drop_plate") or {}).get("scrim") or {})
    steady = int(sc.get("steady_ms", 4000))
    steady_op = [max((m["scrim"] for d, m in zip(shown, meas) if abs(d["start_ms"] - c["start_ms"]) <= steady),
                     default=0.0) for c in shown]
    if painter.look["presentation"] == "highlight":
        # the foot's colour is decided once for the clip: a colour flipping between captions would pump
        painter.fixed_foot, note = painter.pick_foot(
            [painter.foot_backgrounds(m["behind_foot"], op) for m, op in zip(meas, steady_op) if m["behind_foot"]])
        if note:
            notices.append({"kind": "contrast", "at_ms": shown[0]["start_ms"] if shown else 0, "message": note})
    for c, m, op in zip(shown, meas, steady_op):
        cid = f"CAP_{len(items) + 1:03d}"
        lay = painter.layers(c, avoid=avoid, min_scrim=op, behind=m["behind"], behind_foot=m["behind_foot"])
        item = {"id": cid, "fg": str(save_still(lay["fg"], out_dir / f"{cid}_fg.png")), "start_ms": c["start_ms"],
                "end_ms": c["end_ms"], "text": c["text"], "look": look, "emphasis": emphasis,
                "emphasis_words": list(c.get("emphasis") or []), "highlight": bool(c.get("emphasis")),
                "size": lay["size"], "box": [round(v, 1) for v in lay["box"]], "motion": motion,
                "scrim": lay["colors"]["plate_opacity"] if lay["colors"].get("scrim") else 0.0}
        if lay["colors"].get("underlay"):
            item["foot"] = "#%02X%02X%02X" % tuple(lay["colors"]["underlay"][:3])
        if lay["plate"] is not None:
            item["plate"] = str(save_still(lay["plate"], out_dir / f"{cid}_plate.png"))
        if lay["underlay"] is not None:
            item["band"] = str(save_still(lay["underlay"], out_dir / f"{cid}_band.png"))
            item["spans"] = lay["spans"]
        for n in lay["notes"]:
            if not any(x.get("message") == n for x in notices):
                notices.append({"kind": "contrast", "at_ms": c["start_ms"], "message": n})
        items.append(item)
    public = {k: resolved.get(k) for k in ("look", "grouping", "presentation", "emphasis", "sources", "source",
                                           "reason", "digits")}
    write_json(out_dir / "captions-manifest.json", {"generated": now_iso(), "look": public, "captions": items,
                                                    "notices": notices})
    if warnings is not None:
        warnings += [n["message"] for n in notices if n["message"] not in warnings]
    return items


# --------------------------------------------------------------------------- the gallery (Task 16) and pick
SAMPLE_AR = "النهارده هنتكلم عن ٣ حاجات مهمة جدا في الصحة"


def _sample(words: list[dict]) -> list[dict]:
    """A stretch of 4-8 of the clip's words around its middle (the editor sees the looks on their own speech), else
    a built-in Arabic sample with even timing."""
    ws = [w for w in words if str(w.get("word") or "").strip()]
    if len(ws) >= 4:
        mid = len(ws) // 2
        a = max(0, mid - 3)
        return ws[a:a + 7]
    out, t = [], 0
    for i, tok in enumerate(SAMPLE_AR.split()):
        out.append({"id": i, "word": tok, "start_ms": t, "end_ms": t + 280})
        t += 340
    return out


def _gallery_frames(paths, spec: dict, size: tuple, pal: dict) -> list:
    """Two frames of the clip (a third and two thirds in), else a dark and a bright neutral frame in the brand's ink
    and paper (the looks must hold on both)."""
    from PIL import Image
    frames = []
    try:
        from .common import spec_footage
        from .previews import grab_frame
        main = spec_footage(paths, spec)
        dur = int(spec.get("duration_ms") or 0)
        if Path(main).exists() and dur > 0:
            for k in (1, 2):
                fr = grab_frame(main, dur * k // 3 + int(spec.get("source_in_ms") or 0), size)
                if fr is not None:
                    frames.append(fr)
    except Exception:  # noqa: BLE001  no footage: neutral frames below
        frames = []
    if len(frames) < 2:      # dark: ink lifted toward white, so an ink plate still shows on it
        dark = tuple(int(round(c * 0.7 + 255 * 0.3 * 0.5)) for c in pal["ink"])
        frames = [Image.new("RGBA", size, dark + (255,)), Image.new("RGBA", size, tuple(pal["paper"]) + (255,))]
    return frames[:2]


def _sheet(tiles: list[tuple[str, str]], out, size: tuple, label_face: dict | None):
    from PIL import Image, ImageDraw, ImageFont
    W, H = size
    tw = 270
    th = round(tw * H / W)
    lab = 34
    cols = 4
    rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (tw * cols, rows * (th + lab)), (24, 24, 24))
    d = ImageDraw.Draw(sheet)

    def font_for(label: str):
        """The label's font: 20 px, smaller (down to 11) until it fits its tile; the default font is cut instead."""
        for size in range(20, 10, -1):
            try:
                f = ImageFont.truetype(label_face["file"], size) if label_face and label_face.get("file") else None
            except OSError:
                f = None
            if f is None:
                break
            if d.textlength(label, font=f) <= tw - 16:
                return f, label
        f = ImageFont.load_default() if f is None else f
        while label and d.textlength(label + "…", font=f) > tw - 16:
            label = label[:-1]
        return f, (label + "…") if label else label
    for k, (png, label) in enumerate(tiles):
        x, y = (k % cols) * tw, (k // cols) * (th + lab)
        with Image.open(png) as im:
            sheet.paste(im.convert("RGB").resize((tw, th)), (x, y))
        font, text = font_for(label)
        d.text((x + 8, y + th + 6), text, fill=(235, 235, 235), font=font)
    sheet.save(out)
    return out


def render(paths, looks_: list[str] | None = None, frames: list | None = None, emphasis: str | None = None,
           budget_s: float | None = None, sheet: bool = True, **kw) -> dict:
    """`reel caption-looks`: every caption look (or `looks`, Task 16 names too) on two frames of this clip, plus one
    sheet, in 08_quality_control/previews/caption-looks/ (never 03_broll: the real caption stills are not touched).
    The editor picks by sight, then `pick`. Over the time budget (catalog gallery_budget_s, 20 s) is a warning.
    -> {looks: [{name, png, pngs, emphasis}], sheet, elapsed_s, warnings, dir}."""
    import time
    from .common import frame_size, load_config, read_json
    from .stamps import read_compiled
    t0 = time.monotonic()
    looks_ = kw.pop("looks", looks_)
    cat = looks.caption_catalog()
    names = list(dict.fromkeys(looks.legacy_look(n, cat) for n in (looks_ or cat["looks"])))
    W, H = frame_size(paths)
    out = paths.p("08_quality_control/previews/caption-looks")
    out.mkdir(parents=True, exist_ok=True)
    spec_p = paths.p("01_analysis/timeline-spec.json")
    spec = (read_compiled(spec_p) if spec_p.exists() else None) or {}
    words = seq_words(paths, spec) if spec else [w for w in (read_json(paths.p("02_transcription/words.json"), {}) or {})
                                                  .get("words", []) if str(w.get("word") or "").strip()]
    pal = looks.palette(paths.client_db)
    frames = list(frames or _gallery_frames(paths, spec, (W, H), pal))[:2]
    digits = ((load_config("style.json").get("captions") or {}).get("digits")) or "western"
    sample = _localized(_sample(words), digits)
    warnings, res, tiles = [], [], []
    chains: dict = {}
    for name in names:
        lk = cat["looks"][name]
        emph = looks.combine(lk["grouping"], lk["presentation"],
                             emphasis or (cat.get("auto") or {}).get("emphasis", "colour"), cat)["emphasis"]
        if emph not in chains:
            chains[emph] = _caption_fonts(paths, emph)
        chain, heavy = chains[emph]
        cues = group_words(sample, lk["grouping"], cat)
        cue = max(cues, key=lambda c: len(c["words"]))
        cue["emphasis"] = [max(range(len(cue["words"])), key=lambda i: len(cue["words"][i]["text"]))]
        cue = _tidy(cue, None, None)
        parts, notes = fit_cues([cue], name, chain, W, safe_width(W), cat=cat, heavy=heavy, emphasis_mode=emph)
        shown_parts = [p for p in parts if not p.get("hidden")]
        part = next((p for p in shown_parts if p.get("emphasis")), shown_parts[0] if shown_parts else None)
        state = (part.get("emphasis") or [0])[0] if part else 0      # the band sits on the emphasised word
        if part and emph == "tag" and len(part["words"]) > 1:
            # a tag hides the band under it: the band sits on the word beside the tag, so both show
            state = state + 1 if state + 1 < len(part["words"]) else state - 1
        asked = emphasis or (cat.get("auto") or {}).get("emphasis", "colour")
        label = f"{name} · {emph}" if asked == emph else f"{name} · {asked} → {emph}"
        painter = CaptionPainter(name, chain, pal, (W, H), heavy=heavy, emphasis=emph, cat=cat,
                                 highlight=_t42_highlight(spec))
        pngs = []
        for k, fr in enumerate(frames):
            p = out / f"{name}_{k + 1}.png"
            if part is None:
                fr.convert("RGB").save(p)
            else:
                lay = painter.layers(part, frame=fr)
                painter.composite(lay, state=state, background=fr).convert("RGB").save(p)
                for n in lay["notes"]:
                    line = f"{name} on frame {k + 1}: {n}"
                    if "boxed look" in n and line not in warnings:
                        warnings.append(line)
            pngs.append(str(p))
            tiles.append((str(p), label))
        warnings += [n["message"] for n in notes if n["kind"] in ("hidden", "missing_glyph")]
        ew = part["words"][part["emphasis"][0]]["text"] if part and part.get("emphasis") else None
        res.append({"name": name, "png": pngs[0], "pngs": pngs, "emphasis": emph, "label": label,
                    "shown": part["text"] if part else "", "emphasised": ew,
                    "band_word": part["words"][state]["text"] if part and lk["presentation"] == "highlight" else None})
    label_face = (chains[next(iter(chains))][0]["latin"] or [None])[0] if chains else None
    # sheet=False (the recommender's stills): the editor's own gallery sheet is left as it is
    sheet = _sheet(tiles, out / "caption-looks-sheet.png", (W, H), label_face) if sheet else None
    elapsed = time.monotonic() - t0
    budget = float(cat.get("gallery_budget_s", 20) if budget_s is None else budget_s)
    if elapsed > budget:
        warnings.append(f"the caption-look gallery took {elapsed:.1f} s, over its {budget:.0f} s budget on this "
                        "computer (a starting budget: the looks are still right)")
    return {"looks": res, "sheet": str(sheet) if sheet else None, "elapsed_s": round(elapsed, 2), "warnings": warnings,
            "dir": str(out)}


def pick(paths, look: str, yes: bool = False, emphasis: str | None = None) -> dict:
    """Make `look` this client's fixed caption choice (Task 16's `pick`): the diff first, written to the client's
    reel-profile/style.json only with yes=True (looks.pick_preference). -> {look, diff, written, file}."""
    from .common import Context, current_context, use_context
    cur = current_context()
    if cur.root and Path(cur.root) == Path(paths.root).resolve():
        return looks.pick_preference(look, emphasis=emphasis, yes=yes)
    with use_context(Context(paths.root, cur.profile, cur.engine_home)):
        return looks.pick_preference(look, emphasis=emphasis, yes=yes)
