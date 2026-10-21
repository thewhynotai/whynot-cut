"""SRT parsing / writing and word-timed cue building (RTL-safe: no text reordering)."""
from __future__ import annotations

import re
from pathlib import Path

from .common import fmt_ts, parse_ts, ms_to_frame

_ARROW = re.compile(r"\s*-->\s*")
# Characters after which a cue may end naturally (Latin + Arabic punctuation)
_SENT_END = ("." , "?", "!", "؟", "…", "۔")
_CLAUSE_END = (",", "،", "؛", ";", ":")


def read_srt(path: Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.split("\n") if l.strip() != ""]
        if len(lines) < 2:
            continue
        i = 1 if "-->" not in lines[0] else 0
        if "-->" not in lines[i]:
            continue
        try:
            a, b = _ARROW.split(lines[i].strip())[:2]
            start, end = parse_ts(a), parse_ts(b.split()[0])
        except (IndexError, ValueError):       # review 91b6b44 P3-2: name the file and the cue, never "list index"
            from .errors import FileFormatError
            line = next((k for k, t in enumerate(text.split("\n"), 1) if t.strip() == lines[i].strip()), 1)
            raise FileFormatError(path, line, 1,
                                  f"cue {len(cues) + 1}: the time line {lines[i].strip()!r} is not like "
                                  "'00:00:01,000 --> 00:00:02,500'") from None
        cues.append({"index": len(cues) + 1, "start_ms": start, "end_ms": end,
                     "text": "\n".join(lines[i + 1:]).strip()})
    return cues


def write_srt(path: Path, cues: list[dict]) -> Path:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{fmt_ts(c['start_ms'])} --> {fmt_ts(c['end_ms'])}\n{c['text']}\n")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return Path(path)


def validate_cues(cues: list[dict], media_ms: int | None = None) -> list[str]:
    errs = []
    for a in cues:
        if a["end_ms"] <= a["start_ms"]:
            errs.append(f"cue {a['index']}: end <= start")
        if not a["text"].strip():
            errs.append(f"cue {a['index']}: empty text")
        if media_ms is not None and a["end_ms"] > media_ms + 500:
            errs.append(f"cue {a['index']}: ends after media")
    for a, b in zip(cues, cues[1:]):
        if b["start_ms"] < a["end_ms"]:
            errs.append(f"cue {a['index']}->{b['index']}: overlap {a['end_ms'] - b['start_ms']}ms")
    return errs


def _wrap(words: list[str], max_chars: int, max_lines: int) -> str | None:
    lines, cur = [], ""
    for w in words:
        cand = (cur + " " + w).strip()
        if len(cand) <= max_chars or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        return None
    # balance two lines (prevents a single orphan word on line 2)
    if len(lines) == 2 and len(words) >= 3:
        best, best_diff = None, 10 ** 9
        for k in range(1, len(words)):
            l1, l2 = " ".join(words[:k]), " ".join(words[k:])
            if len(l1) <= max_chars and len(l2) <= max_chars:
                d = abs(len(l1) - len(l2))
                if d < best_diff:
                    best, best_diff = (l1, l2), d
        if best:
            lines = list(best)
    return "\n".join(lines)


def build_cues_from_words(words: list[dict], max_chars=32, max_lines=2, max_dur_ms=4000,
                          min_dur_ms=700, max_words: int | None = None, gap_break_ms=600,
                          orphan_slack: int = 6) -> list[dict]:
    """Group timed words into cues. Breaks on sentence punctuation, pauses, length, duration.
    Word order is kept exactly as spoken (logical order) — RTL display is the renderer's job."""
    cues, cur = [], []

    def flush():
        if not cur:
            return
        text = _wrap([w["word"] for w in cur], max_chars, max_lines) or " ".join(w["word"] for w in cur)
        cues.append({"start_ms": cur[0]["start_ms"], "end_ms": cur[-1]["end_ms"], "text": text,
                     "word_ids": [w["id"] for w in cur]})
        cur.clear()

    for w in words:
        if not w["word"]:
            continue
        if cur:
            gap = w["start_ms"] - cur[-1]["end_ms"]
            trial = [x["word"] for x in cur] + [w["word"]]
            too_long = _wrap(trial, max_chars, max_lines) is None
            too_slow = w["end_ms"] - cur[0]["start_ms"] > max_dur_ms
            too_many = max_words is not None and len(cur) >= max_words
            new_seg = w.get("segment_id") is not None and w.get("segment_id") != cur[-1].get("segment_id")
            if gap >= gap_break_ms or too_long or too_slow or too_many or new_seg:
                flush()
        cur.append(w)
        if w["word"].endswith(_SENT_END):
            flush()
        elif max_words and w["word"].endswith(_CLAUSE_END):
            flush()
    flush()

    # merge orphan single-word cues (e.g. a lone "كريم؟") into the previous cue when contiguous
    merged = []
    for c in cues:
        if (merged and len(c["word_ids"]) == 1 and c["start_ms"] - merged[-1]["end_ms"] < 150
                and len(merged[-1]["text"].replace("\n", " ") + " " + c["text"]) <= max_chars + orphan_slack):
            prev = merged[-1]
            prev["text"] = (prev["text"].replace("\n", " ") + " " + c["text"]) if max_lines == 1 else \
                (_wrap((prev["text"].replace("\n", " ") + " " + c["text"]).split(), max_chars, max_lines)
                 or prev["text"] + " " + c["text"])
            prev["end_ms"] = c["end_ms"]
            prev["word_ids"] += c["word_ids"]
        else:
            merged.append(c)
    cues = merged

    # enforce min duration without creating overlaps; never move a start time
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["start_ms"] if i + 1 < len(cues) else None
        if c["end_ms"] - c["start_ms"] < min_dur_ms:
            target = c["start_ms"] + min_dur_ms
            c["end_ms"] = min(target, nxt) if nxt is not None else target
        if nxt is not None and c["end_ms"] > nxt:
            c["end_ms"] = nxt
    for i, c in enumerate(cues, 1):
        c["index"] = i
        c["start_frame"] = ms_to_frame(c["start_ms"])
        c["end_frame"] = ms_to_frame(c["end_ms"])
    return cues
