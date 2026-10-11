"""Scene timing for motion videos (spec §4.1 "Scene anchors" and "Timing"). Pure functions.

Scenes are anchored in SOURCE ms (the sliced transcript's clock) by the verbatim words spoken when they start, then
mapped through the TimeMap (pause removal) to sequence frames. Cue frames are word starts; the hero frame is the moment
every element of the scene is on screen.
"""
from __future__ import annotations

import math

from .common import ms_to_frame
from .plan import norm


def _flat(words: list[dict]) -> list[tuple[str, int]]:
    out = []
    for i, w in enumerate(words):
        out += [(t, i) for t in norm(w.get("word", "")).split()]
    return out


def _find(flat: list[tuple[str, int]], toks: list[str], start_word: int) -> int | None:
    """Word index where `toks` occur contiguously, at or after start_word."""
    n = len(toks)
    for k in range(len(flat) - n + 1):
        if flat[k][1] < start_word:
            continue
        if [t for t, _ in flat[k:k + n]] == toks:
            return flat[k][1]
    return None


def anchor_scenes(scenes: list[dict], words: list[dict], cfg: dict) -> tuple[list[dict], list[str]]:
    flat = _flat(words)
    lead, outro_ms = int(cfg.get("scene_lead_ms", 150)), int(cfg.get("outro_ms", 2500))
    end_of_speech = words[-1]["end_ms"] if words else 0
    total = int(cfg.get("total_ms") or end_of_speech)
    out, errs, prev_word, prev_start = [], [], -1, -1
    for sc in scenes:
        sid, at = sc.get("id"), sc.get("at")
        rec = {"id": sid, "outro": False}
        if at == "@start":
            rec.update(start_ms=0, word_idx=0)
        elif at == "@end":
            rec.update(start_ms=end_of_speech, word_idx=None, outro=True)
        else:
            toks = norm(at or "").split()
            i = _find(flat, toks, prev_word + 1) if toks else None
            if i is None:
                anywhere = _find(flat, toks, 0) if toks else None
                errs.append(f"{sid}: its `at` words «{at}» " + ("come before the previous scene's start (scenes must be "
                            "in spoken order)" if anywhere is not None else "are not in this window's transcript"))
                continue
            rec.update(start_ms=max(0, words[i]["start_ms"] - lead, prev_start + 1), word_idx=i)
            prev_word = i
        prev_start = rec["start_ms"]
        out.append(rec)
    for k, rec in enumerate(out):
        if rec["outro"]:
            rec["end_ms"] = rec["start_ms"] + outro_ms
        elif k + 1 < len(out):
            rec["end_ms"] = out[k + 1]["start_ms"]
        else:
            rec["end_ms"] = max(total, rec["start_ms"] + 1)
    return out, errs


def scene_word_indexes(words: list[dict], start_ms: int, end_ms: int, slack_ms: int = 0) -> list[int]:
    return [i for i, w in enumerate(words) if w["start_ms"] >= start_ms - slack_ms and w["end_ms"] <= end_ms + slack_ms]


def _frame(ms: float, tmap, fps: float) -> int:
    return tmap.frame(ms) if tmap is not None else ms_to_frame(int(round(ms)), fps)


def cue_frames(word_idx: list[int], words: list[dict], tmap, fps: float) -> list[int]:
    return [_frame(words[i]["start_ms"], tmap, fps) for i in word_idx]


def reveal_frames(fps: float, reveal_ms: int) -> int:
    return int(math.ceil(reveal_ms * fps / 1000 - 1e-9))


def hero_frame(last_cue: int, end_frame: int, next_transition: int, fps: float, reveal_ms: int) -> int:
    return min(last_cue + reveal_frames(fps, reveal_ms) + 6, end_frame - next_transition - 1)


def frame_scenes(anchored: list[dict], tmap, fps: float, cfg: dict,
                 transitions: list[int]) -> tuple[list[dict], list[str]]:
    """Adds start_frame, end_frame, cue_frames and hero_frame. transitions[k] = frames of the NEXT scene's transition
    (it plays over the end of scene k). A scene whose last cue comes after the scene starts leaving is too short (in
    continuous speech the last word may still be fading in at the cut; the hero frame is then the last frame before it)."""
    reveal_ms = int(cfg.get("word_reveal_ms", 180))
    out, errs = [], []
    for k, sc in enumerate(anchored):
        rec = dict(sc)
        a = _frame(sc["start_ms"], tmap, fps)
        if sc.get("outro"):
            b = a + ms_to_frame(sc["end_ms"] - sc["start_ms"], fps)       # past the audio: keep its own length
        else:
            b = _frame(sc["end_ms"], tmap, fps)
        cues = [_frame(ms, tmap, fps) for ms in sc.get("cues_ms") or []]
        nxt = transitions[k] if k < len(transitions) else 0
        rec.update(start_frame=a, end_frame=b, cue_frames=cues)
        if b <= a:
            errs.append(f"{sc['id']}: too short for its content (no frames left after pause removal)")
            out.append(rec)
            continue
        last = max(cues) if cues else a
        if last > b - nxt - 1:
            errs.append(f"{sc['id']}: too short for its content (its last cue at frame {last} comes after frame "
                        f"{b - nxt - 1}, where the scene is already leaving): give it more time or move words on")
        rec["hero_frame"] = max(a, min(max(last, hero_frame(last, b, nxt, fps, reveal_ms)), b - 1))
        out.append(rec)
    return out, errs
