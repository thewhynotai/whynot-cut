# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Burned-in caption detection (Phase 4 Task 24, R-4.2): captions already burned into the footage are found without
OCR, so our own caption track can be hidden by default (the words stay for cuts and the transcript) and the editor
is told in one line.

Input: frames at one per second and the clip's words. A single clip gets its own pass at 640x360 (`decode_frames`;
small subtitles, 3 % of the frame, still have strokes there); an episode reuses the 320x180 thumbnails its overlay
scan already decoded (`band_track`, kept per second so a reel window picked later is judged without a second decode,
`detect_track(start_s=, end_s=)`). Numpy only.
  1. Per frame, text-band candidates in the upper 20 % and the lower 45 % of the frame: rows dense in SHORT vertical
     strokes (a horizontal luminance step of EDGE_T or more), well above the rest of that region (a texture is dense
     everywhere), BAND_MIN-BAND_MAX of the frame height per line (up to three lines merge), strokes spread over at
     least MIN_COLS of the width, and a high-contrast core (light text with a dark rim, or dark text on a plate). The
     strongest band of a region gets a small stroke signature (SIG_ROWS x SIG_COLS) for the content comparisons.
  2. Per region, is the band caption-like? Its content is REPLACED often during the speech (>= MIN_CHANGES
     replacements while it stays on screen, >= MIN_RATE per on-screen second; a super that comes and goes is never
     "replaced"), it rarely holds still (a lower-third / name super holds for STILL_RUN_S or
     more), it is not sliding sideways (a ticker: the next second's strokes match this second's shifted), its stroke mass
     sits near the horizontal centre (supers and logos sit to one side; captions aligned to one side are missed), and, when the clip has long pauses, it is off screen in
     most of them (a ticker or a watermark stays).
  3. Speech-linked evidence to ACT on: the band is off screen in the clip's long pauses, or its changes follow our
     cue starts (Pearson >= MIN_R, best of a lag of -1/0/+1 s, over >= RHYTHM_MIN_S speech seconds; the spec's test).
     At one sample per second, continuous speech hides the cue rhythm (pauses under a second are not seen), so the
     spec's Pearson test alone misses ordinary captions, and without either evidence centred rotating text cannot be
     told from captions: such a clip only gets the question ("maybe"), never a silent hide (a design deviation from
     the spec's mandatory Pearson, recorded in the lane report for the executor).
  4. Verdict: coverage = speech seconds with a caption-like band / speech seconds. >= 0.60 with that evidence "yes"
     (without evidence "maybe"), >= 0.25 "maybe", else "no"; under MIN_SPEECH_S speech seconds a band gives "maybe";
     an unfinished scan is always "maybe" (spec). Only "yes" ever hides our captions.
Numbers here are OUR starting values (Source-R publishes none), measured on the synthetic fixtures in
tests/fixtures/burned_captions/ (make_fixtures.py), including continuous speech, karaoke, long two-line cues, small
vertical text, swapping supers and tickers. Not verified on client footage. Captions in the middle of the frame (20-55
% of the height) are not searched (spec). Nothing here raises for a real user (G10): `run` turns a failure into
verdict "unknown" with the reason and changes nothing.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

VERSION = 2
STEP_S = 1.0
TOP_FRAC, LOW_FRAC = 0.20, 0.45          # searched: the upper 20 % and the lower 45 % of the frame (spec)
EDGE_T = 40                              # a horizontal luminance step (0-255) that makes a stroke-side pixel
ROW_MIN = 0.035                          # a text row: at least this share of the row's pixels are stroke sides
ROW_X_BASE = 3.0                         # ... and this many times the median row of its region
BAND_MIN, BAND_MAX = 0.02, 0.12          # band height per line, share of the frame height
LINE_GAP = 0.025                         # caption lines this close (share of the height) are one band
MAX_LINES = 3
MIN_COLS = 0.05                          # stroke columns spread over at least this share of the width
CONTRAST = 100                           # p97 - p3 luminance inside the band
SIG_ROWS, SIG_COLS = 4, 80               # the stroke signature of a band: stroke density per cell (0-15)
CHANGE_T = 0.12                          # content replaced: L1 difference / total density (unchanged text 0.00-0.05,
                                         # a new cue 0.17-0.30 on the fixtures)
SCROLL_MAX_SHIFT = 20                    # signature columns tried for a sideways slide (a quarter of the width)
SCROLL_GAIN = 0.5                        # a slide explains a change when the shifted difference is under half of it
SCROLL_SHARE_MAX = 0.5
CENTER_MAX = 0.15                        # median band centre within 15 % of the frame width from the middle
MIN_CHANGES = 2                          # content REPLACEMENTS during the speech (appear / disappear do not count)
MIN_RATE = 0.10                          # replacements per on-screen second (one in 10 s at the least: long cues)
STILL_RUN_S = 6                          # a band unchanged this long is "still" (two-line cues last up to ~5 s)
STILL_SHARE_MAX = 0.3
MIN_R = 0.4                              # Pearson, band changes vs cue starts (spec)
PAUSE_S = 2.0                            # a long pause: no word for at least this long
PAUSE_PRESENT_MAX = 0.5
SPEECH_MARGIN_S = 0.25
YES_AT, MAYBE_AT = 0.60, 0.25            # coverage thresholds (spec)
MIN_SPEECH_S = 4                         # fewer speech seconds: a band can only make the verdict "maybe"
RHYTHM_MIN_S = 10                        # the cue-rhythm correlation counts as evidence only over this much speech
                                         # (best of 6 correlations on a few samples is often >= 0.4 by chance)
BUDGET_S = 20.0                          # wall time of a single clip's own pass (spec)
CHUNK_S = 10.0
CLIP_SIZE = (640, 360)
SHEET_TILES = 6

NOTICE = {"ar": "الفيديو فيه ترجمة محروقة في الصورة، فخبّينا الكابشن بتاعنا عشان ميبقاش فيه اتنين. الكلام لسه موجود للقص.",
          "en": "The footage already has burned-in subtitles, so our captions are hidden to avoid showing two. The words "
                "are still there for cutting."}
ASK = {"ar": "لقينا ترجمة محروقة في الفيديو؛ تحب نخبّي الكابشن بتاعنا؟",
       "en": "The footage seems to have burned-in subtitles; hide our captions?"}


# --------------------------------------------------------------------------- per-frame bands
def _luma(img: np.ndarray) -> np.ndarray:
    return img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114


def strokes(img: np.ndarray) -> np.ndarray:
    """bool (H, W): stroke-side pixels (a horizontal luminance step of EDGE_T or more)."""
    g = _luma(img.astype(np.float32))
    e = np.zeros(g.shape, dtype=bool)
    e[:, 1:] = np.abs(np.diff(g, axis=1)) >= EDGE_T
    return e


def _regions(h: int) -> list:
    return [("top", 0, int(round(h * TOP_FRAC))), ("bottom", int(round(h * (1 - LOW_FRAC))), h)]


def _bands(img: np.ndarray, e: np.ndarray) -> list:
    h, w = img.shape[:2]
    g = _luma(img.astype(np.float32))
    k = max(3, int(round(h / 60)) | 1)
    sm = np.convolve(e.mean(axis=1), np.ones(k) / k, mode="same")
    out = []
    for name, a, b in _regions(h):
        reg = sm[a:b]
        if reg.size == 0:
            continue
        cand = reg >= max(ROW_MIN, ROW_X_BASE * float(np.median(reg)))
        runs, y = [], 0
        while y < len(cand):
            if cand[y]:
                s = y
                while y < len(cand) and cand[y]:
                    y += 1
                runs.append([s + a, y + a, 1])
            y += 1
        merged, gap = [], max(2, int(round(h * LINE_GAP)))
        for r in runs:                                   # the lines of one caption merge
            if merged and r[0] - merged[-1][1] <= gap and merged[-1][2] < MAX_LINES:
                merged[-1][1], merged[-1][2] = r[1], merged[-1][2] + 1
            else:
                merged.append(r)
        for y0, y1, lines in merged:
            ht = (y1 - y0) / h
            if ht < BAND_MIN or ht > BAND_MAX * lines:
                continue
            cols = np.flatnonzero(e[y0:y1].any(axis=0))
            if cols.size < MIN_COLS * w:
                continue
            x0, x1 = int(cols[0]), int(cols[-1]) + 1
            core = g[y0:y1, x0:x1]
            if float(np.percentile(core, 97) - np.percentile(core, 3)) < CONTRAST:
                continue
            mass = np.cumsum(e[y0:y1].sum(axis=0))          # the centre of the stroke mass, not of the extent:
            cm = int(np.searchsorted(mass, mass[-1] / 2))     # a logo at the edge of the same rows barely moves it
            out.append({"region": name, "y0": int(y0), "y1": int(y1), "x0": x0, "x1": x1,
                        "cm": round(cm / w, 4), "score": round(float(e[y0:y1].mean()), 4)})
    return out


def frame_bands(img: np.ndarray) -> list:
    """Text-band candidates of one RGB frame: [{region, y0, y1, x0, x1, score}] (pixels, y1/x1 exclusive)."""
    if not isinstance(img, np.ndarray) or img.ndim != 3 or img.shape[0] < 20 or img.shape[1] < 20:
        return []
    return _bands(img, strokes(img))


def _signature(e: np.ndarray, y0: int, y1: int) -> np.ndarray:
    """uint8 (SIG_ROWS, SIG_COLS): the stroke density of each cell of the band rows x the full width, 0-15."""
    band = e[y0:y1].astype(np.float32)
    h, w = band.shape
    rows = np.linspace(0, h, SIG_ROWS + 1).astype(int)
    cols = np.linspace(0, w, SIG_COLS + 1).astype(int)
    sig = np.zeros((SIG_ROWS, SIG_COLS), dtype=np.uint8)
    for i in range(SIG_ROWS):
        r = band[rows[i]:max(rows[i + 1], rows[i] + 1)]
        for j in range(SIG_COLS):
            c = r[:, cols[j]:max(cols[j + 1], cols[j] + 1)]
            sig[i, j] = int(round(float(c.mean()) * 15)) if c.size else 0
    return sig


def _hex(sig: np.ndarray) -> str:
    return "".join("%x" % v for v in sig.ravel())


def _unhex(s) -> np.ndarray | None:
    try:
        v = np.array([int(c, 16) for c in s], dtype=np.uint8)
        return v.reshape(SIG_ROWS, SIG_COLS) if v.size == SIG_ROWS * SIG_COLS else None
    except (TypeError, ValueError):
        return None


def band_track(frames, step_s: float = STEP_S, base_s: float = 0.0) -> dict:
    """The per-second band results of a run of frames (JSON-able; an episode keeps it for its reel windows)."""
    frames = frames if isinstance(frames, np.ndarray) and frames.ndim == 4 else np.zeros((0, 180, 320, 3), np.uint8)
    secs = []
    for f in frames:
        e = strokes(f)
        bl = _bands(f, e)
        sig = {}
        for region in ("top", "bottom"):
            bs = [b for b in bl if b["region"] == region]
            if bs:
                best = max(bs, key=lambda b: (b["y1"] - b["y0"]) * b["score"])
                sig[region] = _hex(_signature(e, best["y0"], best["y1"]))
        secs.append({"bands": bl, "sig": sig})
    h, w = (frames.shape[1], frames.shape[2]) if len(frames) else (180, 320)
    return {"version": VERSION, "step_s": step_s, "base_s": base_s, "size": [int(w), int(h)], "seconds": secs}


# --------------------------------------------------------------------------- speech, cues
def _words(words) -> list:
    out = []
    for x in words or []:
        if isinstance(x, dict) and isinstance(x.get("start_ms"), (int, float)) and isinstance(x.get("end_ms"), (int, float)):
            if x["end_ms"] >= x["start_ms"] >= 0:
                out.append(x)
    return sorted(out, key=lambda x: x["start_ms"])


def _times(n, step_s, base_s):
    return [base_s + k * step_s for k in range(n)]


def speech_seconds(words: list, n: int, step_s: float = STEP_S, base_s: float = 0.0) -> np.ndarray:
    """bool (n,): sample k (at base_s + k*step_s) falls inside a word or a gap shorter than PAUSE_S between words."""
    ws, spans = _words(words), []
    for x in ws:
        a, b = x["start_ms"] / 1000, x["end_ms"] / 1000
        if spans and a - spans[-1][1] < PAUSE_S:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    return np.array([any(a - SPEECH_MARGIN_S <= t <= b + SPEECH_MARGIN_S for a, b in spans)
                     for t in _times(n, step_s, base_s)], dtype=bool)


def pause_seconds(words: list, n: int, step_s: float = STEP_S, base_s: float = 0.0) -> np.ndarray:
    """bool (n,): sample k is well inside a long pause (>= PAUSE_S without words, 0.5 s margins)."""
    ws = _words(words)
    gaps = [(p["end_ms"] / 1000, q["start_ms"] / 1000) for p, q in zip(ws, ws[1:])
            if (q["start_ms"] - p["end_ms"]) / 1000 >= PAUSE_S]
    return np.array([any(a + 0.5 <= t <= b - 0.5 for a, b in gaps) for t in _times(n, step_s, base_s)], dtype=bool)


def cue_starts(words: list, n: int, step_s: float = STEP_S, base_s: float = 0.0) -> list:
    """[bool (n,)] per cue grouping (our subtitles and our short captions): a cue starts within half a step of k."""
    ws = [dict(x, id=x.get("id", i + 1)) for i, x in enumerate(_words(words))]
    if not ws:
        return []
    try:
        from .transcribe import caption_cues
        groups = caption_cues(ws)
    except Exception:  # noqa: BLE001  no style config (a bare home): one grouping, by pauses of 250 ms
        groups = ([{"start_ms": x["start_ms"]} for i, x in enumerate(ws)
                   if i == 0 or x["start_ms"] - ws[i - 1]["end_ms"] >= 250],)
    out = []
    for cues in groups:
        b = np.zeros(n, dtype=bool)
        for c in cues or []:
            s = c.get("start_ms") if isinstance(c, dict) else None
            if isinstance(s, (int, float)):
                k = int(round((s / 1000 - base_s) / step_s))
                if 0 <= k < n:
                    b[k] = True
        out.append(b)
    return out


def pearson(x, y) -> float | None:
    """Pearson r of two equal-length series; None when either is constant (no usable correlation)."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if x.size < 3 or x.size != y.size or x.std() == 0 or y.std() == 0:
        return None
    r = float(np.corrcoef(x, y)[0, 1])
    return r if math.isfinite(r) else None


def _shift(b: np.ndarray, lag: int) -> np.ndarray:
    if lag == 0:
        return b
    out = np.zeros_like(b)
    if lag > 0:
        out[lag:] = b[:-lag]
    else:
        out[:lag] = b[-lag:]
    return out


# --------------------------------------------------------------------------- the region test
def _diff(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.astype(np.int16), b.astype(np.int16)
    u = int((a + b).sum())
    return float(np.abs(a - b).sum() / u) if u else 0.0


def _slid(prev: np.ndarray, cur: np.ndarray, d0: float) -> bool:
    """True when cur is prev slid sideways (a ticker), not replaced."""
    best = d0
    for s in range(1, SCROLL_MAX_SHIFT + 1):
        for a, b in ((prev[:, s:], cur[:, :-s]), (prev[:, :-s], cur[:, s:])):
            best = min(best, _diff(a, b))
    return best < d0 * SCROLL_GAIN


def _region(track: dict, region: str):
    secs = track["seconds"]
    w, h = track["size"]
    n = len(secs)
    present = np.zeros(n, dtype=bool)
    change = np.zeros(n, dtype=bool)
    slide = np.zeros(n, dtype=bool)
    rows, cx, sigs = [None] * n, np.full(n, np.nan), [None] * n
    for k, sec in enumerate(secs):
        bs = [b for b in sec.get("bands", []) if b.get("region") == region]
        if bs and sec.get("sig", {}).get(region):
            best = max(bs, key=lambda b: (b["y1"] - b["y0"]) * b["score"])
            present[k], rows[k] = True, (best["y0"], best["y1"])
            cx[k] = best["cm"] if isinstance(best.get("cm"), (int, float)) else (best["x0"] + best["x1"]) / 2 / w
            sigs[k] = _unhex(sec["sig"][region])
    for k in range(1, n):
        if present[k] != present[k - 1]:
            change[k] = True
        elif present[k] and sigs[k] is not None and sigs[k - 1] is not None:
            d = _diff(sigs[k], sigs[k - 1])
            if d > CHANGE_T:
                change[k] = True
                slide[k] = _slid(sigs[k - 1], sigs[k], d)
    gap_rep = np.zeros(n, dtype=bool)          # a cue gap seen as one empty sample: new text after it is a replacement
    for k in range(2, n):
        if present[k] and present[k - 2] and not present[k - 1] and sigs[k] is not None and sigs[k - 2] is not None:
            gap_rep[k] = _diff(sigs[k], sigs[k - 2]) > CHANGE_T
    return present, change, slide, rows, cx, h, gap_rep


def still_share(present, change) -> float:
    """Share of the on-screen seconds that sit in runs of STILL_RUN_S or more seconds without a content change."""
    n, still, run = len(present), 0, 0
    for k in range(n + 1):
        if k < n and present[k] and run and not change[k]:
            run += 1
            continue
        if run >= STILL_RUN_S:
            still += run
        run = 1 if k < n and present[k] else 0
    on = int(np.sum(present))
    return round(still / on, 3) if on else 0.0


def rhythm(present, change, slide, starts: list, pauses, speech, cx=None, gap_rep=None) -> dict:
    """Is one region's band caption-like? {r, lag, pause_present, changes, rate, still_share, scroll_share,
    center_offset, passes, evidence_rhythm, evidence_pauses}."""
    present, change, speech = np.asarray(present, bool), np.asarray(change, bool), np.asarray(speech, bool)
    slide = np.asarray(slide, bool) if len(slide) == len(present) else np.zeros(len(present), bool)
    pauses = np.asarray(pauses, bool) if len(pauses) == len(present) else np.zeros(len(present), bool)
    idx = np.flatnonzero(speech)
    best, lag_best = None, 0
    if idx.size:
        lo, hi = int(idx[0]), int(idx[-1]) + 1
        for st in starts:
            for lag in (-1, 0, 1):
                r = pearson(change[lo:hi], _shift(st, lag)[lo:hi])
                if r is not None and (best is None or r > best):
                    best, lag_best = r, lag
    on = int(present.sum())
    content = change & present & np.r_[False, present[:-1]]          # replaced while on screen (not appear/disappear)
    nch = int((change & speech).sum())
    if gap_rep is not None and len(gap_rep) == len(present):         # new text after a one-sample cue gap in speech
        content = content | (np.asarray(gap_rep, bool) & np.r_[False, speech[:-1]])
    nrep = int((content & speech).sum())                              # a super that comes and goes is never "replaced"
    rate = round(nrep / on, 3) if on else 0.0
    nslide = int((slide & content).sum())
    scroll = round(nslide / int(content.sum()), 3) if content.sum() else 0.0
    off = None
    if cx is not None:
        vals = np.asarray(cx, float)[present]
        vals = vals[np.isfinite(vals)]
        off = round(float(abs(np.median(vals) - 0.5)), 3) if vals.size else None
    pp = float(present[pauses].mean()) if pauses.any() else None
    ss = still_share(present, change)
    ok = (nrep >= MIN_CHANGES and rate >= MIN_RATE and ss <= STILL_SHARE_MAX and scroll <= SCROLL_SHARE_MAX
          and (off is None or off <= CENTER_MAX) and (pp is None or pp <= PAUSE_PRESENT_MAX))
    return {"r": None if best is None else round(best, 3), "lag": lag_best,
            "pause_present": None if pp is None else round(pp, 3), "changes": nch, "replacements": nrep, "rate": rate,
            "still_share": ss,
            "scroll_share": scroll, "center_offset": off, "passes": bool(ok),
            "evidence_rhythm": bool(best is not None and best >= MIN_R),
            "evidence_pauses": bool(pp is not None and pp <= PAUSE_PRESENT_MAX)}


def _bands_out(present, rows, h, step_s, base_s) -> list:
    out, k, n = [], 0, len(present)
    while k < n:
        if not present[k]:
            k += 1
            continue
        s = k
        while k < n and present[k]:
            k += 1
        ys = [rows[j] for j in range(s, k) if rows[j]]
        out.append({"y0": round(float(np.median([y[0] for y in ys])) / h, 4),
                    "y1": round(float(np.median([y[1] for y in ys])) / h, 4),
                    "from_ms": int(round((base_s + s * step_s) * 1000)), "to_ms": int(round((base_s + k * step_s) * 1000))})
    return out


def _window(track: dict, start_s, end_s) -> dict:
    if start_s is None and end_s is None:
        return track
    step, base = track.get("step_s", STEP_S), track.get("base_s", 0.0)
    n = len(track["seconds"])
    a = max(0, int(math.floor(((start_s if start_s is not None else base) - base) / step + 1e-9)))
    b = min(n, int(math.ceil(((end_s if end_s is not None else base + n * step) - base) / step - 1e-9)))
    return dict(track, base_s=base + a * step, seconds=track["seconds"][a:max(a, b)])


def detect_track(track: dict, words, *, start_s: float | None = None, end_s: float | None = None,
                 complete: bool = True) -> dict:
    """The verdict for a clip, or a window [start_s, end_s) of an episode, from its per-second band results."""
    tr = _window(track, start_s, end_s)
    step, base = tr.get("step_s", STEP_S), tr.get("base_s", 0.0)
    n = len(tr["seconds"])
    res = {"version": VERSION, "verdict": "no", "coverage": 0.0, "bands": [], "complete": bool(complete),
           "sheet": None, "samples": n, "speech_seconds": 0, "regions": {}, "evidence": False, "reason": None,
           "basis": "OCR-free text bands + caption-like change pattern; starting thresholds measured on synthetic "
                    "fixtures, not verified on client footage"}
    if n == 0:
        res.update(reason="no frames", complete=False)
        res["_strong"], res["_segments"] = [], []
        return res
    speech = speech_seconds(words, n, step, base)
    pauses = pause_seconds(words, n, step, base)
    starts = cue_starts(words, n, step, base)
    sp = int(speech.sum())
    res["speech_seconds"] = sp
    passing, any_band = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    segments, strong, evidence = [None] * n, [], False
    for region in ("top", "bottom"):
        present, change, slide, rows, cx, h, gap_rep = _region(tr, region)
        any_band |= present
        rh = rhythm(present, change, slide, starts, pauses, speech, cx, gap_rep)
        rh["present_seconds"] = int(present.sum())
        res["regions"][region] = rh
        if rh["passes"]:
            passing |= present
            evidence |= (rh["evidence_rhythm"] and sp >= RHYTHM_MIN_S) or rh["evidence_pauses"]
            res["bands"] += _bands_out(present, rows, h, step, base)
            seg = 0
            for k in range(n):
                if present[k]:
                    if change[k]:
                        seg += 1
                    segments[k] = f"{region}{seg}"
                    sc = max((b["score"] for b in tr["seconds"][k]["bands"] if b["region"] == region), default=0)
                    strong.append((sc, k))
    picked, seen = [], set()
    for _, k in sorted(strong, reverse=True):          # the contact sheet: one tile per caption cue
        if segments[k] not in seen:
            seen.add(segments[k])
            picked.append(k)
        if len(picked) == SHEET_TILES:
            break
    res["_strong"], res["_segments"] = picked, segments
    res["evidence"] = bool(evidence)
    if sp == 0:
        res.update(verdict="no", reason="no speech")
        return res
    cov = float((passing & speech).sum()) / sp
    res["coverage"] = round(cov, 3)
    if sp < MIN_SPEECH_S:
        res["verdict"] = "maybe" if (any_band & speech).any() else "no"
        res["reason"] = "too short to judge"
    elif cov >= YES_AT:
        res["verdict"] = "yes" if evidence else "maybe"
        if not evidence:
            res["reason"] = "caption-like text, but too little speech to act on"
    else:
        res["verdict"] = "maybe" if cov >= MAYBE_AT else "no"
    if not complete:
        res.update(verdict="maybe", reason=res["reason"] or "the scan did not finish (time budget)")
    return res


def detect(frames, words, *, step_s: float = STEP_S, base_s: float = 0.0, complete: bool = True) -> dict:
    """The verdict for one clip from its frames and words (pure)."""
    return detect_track(band_track(frames, step_s, base_s), words, complete=complete)


# --------------------------------------------------------------------------- decoding and the whole run
def decode_frames(src, start_s: float, length_s: float, lane: str = "cpu", size=CLIP_SIZE) -> np.ndarray:
    """(n, h, w, 3) uint8: one frame per second of src at `size` (a clip's own pass; the episode uses the overlay
    scan's 320x180 thumbnails). `lane`: the decoder's lane; a GPU failure decodes once more on the CPU."""
    import subprocess
    from . import accel
    from .common import ffmpeg_exe
    from .media_util import ff_timeout
    w, h = size

    def build(ln):
        return [ffmpeg_exe(), "-nostdin", "-v", "error", *accel.decode_args(ln), "-ss", f"{max(0.0, start_s):.3f}",
                "-i", str(src), "-t", f"{length_s:.3f}", "-an", "-sn", "-vf",
                f"fps=1,scale={w}:{h}:flags=area,format=rgb24", "-f", "rawvideo", "-"]
    res, _lane = accel.run_ff(build, lane, runner=lambda cmd: subprocess.run(cmd, capture_output=True, check=False,
                                                                              timeout=ff_timeout(cmd)))
    raw = res.stdout or b""
    fs = w * h * 3
    n = len(raw) // fs
    return np.frombuffer(raw[:n * fs], dtype=np.uint8).reshape(n, h, w, 3)


def scan_clip(src, duration_s: float, words, *, decode=None, clock=time.monotonic, budget_s: float = BUDGET_S,
              chunk_s: float = CHUNK_S, lane: str = "cpu") -> tuple:
    """(result, frames): a single clip's own 1 fps pass in short chunks (the budget is checked before each one after
    the first). A short chunk is padded to one frame per second (later frames keep their times); an empty chunk ends
    the scan as incomplete. This helper never takes a GPU slot itself: the calling verb passes its lane."""
    if decode is None:
        def decode(s, a, b):
            return decode_frames(s, a, b, lane=lane)
    t0, parts, c0, complete = clock(), [], 0.0, True
    dur = max(0.0, float(duration_s or 0))
    while c0 < dur - 1e-6:
        if c0 > 0 and clock() - t0 > budget_s:
            complete = False
            break
        c1 = min(dur, c0 + chunk_s)
        want = max(1, int(math.ceil(c1 - c0 - 1e-6)))
        fr = decode(src, c0, c1 - c0)
        if not (isinstance(fr, np.ndarray) and fr.ndim == 4 and len(fr)):
            complete = False
            break
        fr = fr[:want]
        if len(fr) < want:
            fr = np.concatenate([fr, np.zeros((want - len(fr), *fr.shape[1:]), fr.dtype)])
        parts.append(fr)
        c0 = c1
    frames = np.concatenate(parts) if parts else np.zeros((0, CLIP_SIZE[1], CLIP_SIZE[0], 3), np.uint8)
    res = detect(frames, words, complete=complete)
    res["scanned_s"] = round(min(c0, dur), 1)
    res["elapsed_s"] = round(clock() - t0, 1)
    return res, frames


def contact_sheet(frames, keys: list, out: Path) -> str | None:
    """A sheet of up to SHEET_TILES of the strongest frames, one per caption cue (3 x 2 tiles of 320x180), PNG."""
    keys = [k for k in keys if 0 <= k < len(frames)][:SHEET_TILES]
    if not keys:
        return None
    from PIL import Image
    tw, th = 320, 180
    sheet = Image.new("RGB", (tw * 3, th * ((len(keys) + 2) // 3)), (0, 0, 0))
    for i, k in enumerate(sorted(keys)):
        sheet.paste(Image.fromarray(frames[k]).resize((tw, th)), ((i % 3) * tw, (i // 3) * th))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return str(out)


def _source(src) -> dict | None:
    try:
        st = Path(src).stat()
        return {"path": str(src), "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    except (OSError, TypeError, ValueError):
        return None


def write_result(paths, res: dict, frames=None, src=None) -> Path:
    """01_analysis/burned-in-captions.json (+ the contact sheet in 08_quality_control/); never NaN in the JSON."""
    from .common import write_json
    keys = res.pop("_strong", [])
    res.pop("_segments", None)
    res.setdefault("detected_at", time.time())
    if src is not None:
        res["source"] = _source(src)
    if frames is not None and res.get("bands"):
        try:
            res["sheet"] = contact_sheet(frames, keys, paths.p("08_quality_control/burned-in-captions-sheet.png"))
        except Exception:  # noqa: BLE001  the sheet is evidence only
            res["sheet"] = None
    json.dumps(res, allow_nan=False)
    f = paths.p("01_analysis/burned-in-captions.json")
    write_json(f, res)
    return f


def run(paths, src, duration_s: float, *, words=None, lane: str = "cpu", decode=None, clock=time.monotonic,
        budget_s: float = BUDGET_S) -> dict:
    """Scan a clip, write the result, return it. Never raises (G10): a failure is verdict "unknown" with the reason
    and no effect. `words`: default the project's 02_transcription/words.json."""
    try:
        if words is None:
            from .common import read_json
            words = (read_json(paths.p("02_transcription/words.json"), {}) or {}).get("words") or []
        res, frames = scan_clip(src, duration_s, words, decode=decode, clock=clock, budget_s=budget_s, lane=lane)
        write_result(paths, res, frames, src=src)
        return res
    except Exception as e:  # noqa: BLE001
        return {"version": VERSION, "verdict": "unknown", "error": f"{type(e).__name__}: {str(e)[:200]}",
                "bands": [], "complete": False, "coverage": 0.0, "sheet": None}


# --------------------------------------------------------------------------- effects (the wiring is in hooks)
def policy(res: dict, *, plan_compiled: bool = False, language: str = "ar") -> dict:
    """What to do with a verdict: {"hide": bool, "notice": one line | None}. yes -> hide our captions (only when the
    verdict exists before the plan is compiled; later: the editor gets the one-switch question, nothing changes);
    maybe -> the question, nothing changes; no / unknown -> nothing."""
    lang = "en" if language == "en" else "ar"
    v = res.get("verdict") if isinstance(res, dict) else None
    if v == "yes" and not plan_compiled:
        return {"hide": True, "notice": NOTICE[lang]}
    if v in ("yes", "maybe"):
        return {"hide": False, "notice": ASK[lang]}
    return {"hide": False, "notice": None}


def avoid_zones(res: dict) -> list:
    """The detected caption bands as frame-fraction rectangles [x0, y0, x1, y1] with their times, for graphics
    placement (a statement bar must not cover the burned text)."""
    out = []
    for b in ((res or {}).get("bands") or []) if isinstance(res, dict) else []:
        if isinstance(b, dict) and all(isinstance(b.get(k), (int, float)) for k in ("y0", "y1", "from_ms", "to_ms")):
            out.append({"rect": [0.0, b["y0"], 1.0, b["y1"]], "from_ms": b["from_ms"], "to_ms": b["to_ms"]})
    return out


def intake_line(res: dict, language: str = "ar") -> str | None:
    """The one line for the intake warnings (T4.8): the notice on yes, the question on maybe, else nothing."""
    return policy(res, language=language)["notice"]


def _read(f):
    """(dict, ok): the JSON object in f; ({}, True) when f does not exist, ({}, False) when it cannot be used."""
    f = Path(f)
    if not f.exists():
        return {}, True
    try:
        d = json.loads(f.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}, False
    return (d, True) if isinstance(d, dict) else ({}, False)


def captions_hidden(paths) -> bool:
    """Should the build hide OUR caption track? The editor's switch (edit-decisions captions.visible) wins; otherwise
    a "yes" verdict on the CURRENT footage (same size and modification time as when it was scanned) hides them, only
    when it existed before the plan was compiled (timeline-spec.json), never by a late result. The cue files and the
    words are never touched. Never raises."""
    try:
        cap = _read(paths.p("01_analysis/edit-decisions.json"))[0].get("captions")
        vis = cap.get("visible") if isinstance(cap, dict) else None
        if isinstance(vis, bool):
            return not vis
        res = _read(paths.p("01_analysis/burned-in-captions.json"))[0]
        if res.get("verdict") != "yes":
            return False
        src = res.get("source")
        if isinstance(src, dict):
            now = _source(src.get("path"))
            if now is None or (now["size"], now["mtime_ns"]) != (src.get("size"), src.get("mtime_ns")):
                return False                              # the footage changed (or is gone): the verdict is stale
        spec = paths.p("01_analysis/timeline-spec.json")
        if not spec.exists():
            return True
        at = res.get("detected_at")
        return isinstance(at, (int, float)) and at <= spec.stat().st_mtime
    except Exception:  # noqa: BLE001  G10
        return False


def set_captions(paths, mode: str) -> None:
    """The editor's one switch: "on" shows our captions, "off" hides them, "auto" follows the detection again
    (edit-decisions captions.visible; every other key is kept). An edit-decisions file that cannot be read is never
    overwritten (ValueError)."""
    if mode not in ("on", "off", "auto"):
        raise ValueError(f"captions must be on, off or auto (got {mode!r})")
    from .common import write_json
    f = paths.p("01_analysis/edit-decisions.json")
    ed, ok = _read(f)
    if not ok:
        raise ValueError(f"{f} is not a readable JSON object: not changed")
    cap = dict(ed.get("captions") or {}) if isinstance(ed.get("captions"), dict) else {}
    if mode == "auto":
        cap.pop("visible", None)
    else:
        cap["visible"] = mode == "on"
    ed["captions"] = cap
    write_json(f, ed)
