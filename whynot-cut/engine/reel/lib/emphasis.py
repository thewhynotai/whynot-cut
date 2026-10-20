# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Emphasis punch-in candidates (3.0 Task 29, R-4.7): one signal for the story-editor, never an automatic edit.

Score per word: 0.6 × loudness_z (word RMS in dB against the 8 nearest words) + 0.2 × after_pause (a pause >= 300 ms
before it, or the first word) + boosts: a spoken number +0.3 (safety.numbers; «ست»/«ميت» only next to a unit or a time
word), a client name or product +0.2 (the glossary, the profile's name and people; clitic forms and one-letter
mishearings), the CTA keyword +0.2 (only when the CTA part is on), the statement's `key_word` +0.3. No pitch term.

Candidates: the top word of each phrase (phrases break at a gap >= 250 ms, sentence punctuation, a speaker turn); the
punch runs over that phrase, clamped to 1.2-4.0 s, inside one kept range (no pause or word cut, no pre-ticked cut
proposal) and one shot, never in the hook (first 1.5 s on the sequence clock, a hook_title), the ending (the first
ending card or the protected sign-off; with endings off the last 1.5 s), a cutaway, a full-screen card, a story camera
move or a recited verse. Placed greedily by score with `min_gap` between punch starts (6 s calm types, 4 s energetic,
6 s without a recipe) and at most the recipe's punch_ins_per_30s in any 30 s; an emotional reel gets none.

Face safety (one formula): s_max = the largest scale <= min(1.12, recipe max) that keeps the head envelope (the union of
the head boxes of every protected face in every face sample of the punch, plus the samples nearest its start, middle
and end) inside the frame (or the 4:5 window) with a 6 % margin, the zoom anchored on the head centre (offsets clamped
so the picture always covers the frame, on both axes), measured on the COMPOSED camera (the podcast shot layer through
shots.compose_camera, the 4:5 window as plan.apply_framing does). s_max < 1.05 drops it; else scale = 1.05 +
(s_max - 1.05) × r, r = 1 - (rank - 1)/(n - 1) on the dense score rank. No face measured -> centred on the window at
1.05, needs_review, unticked by default (default_keep false): the default build has no punch there.

Head box from a face box: R-6.4's starting guess (+45 % top, +15 % below, +20 % each side; motion.json head_from_face,
"not measured"). Face samples: 01_analysis/face-samples.json, written only here (`reel emphasis --faces`): one decode
pass at 4 fps in the "shots" GPU slot, at the source's own aspect (no padding), display size (rotation applied).

Writes only 01_analysis/emphasis.json and 01_analysis/face-samples.json; never edit-decisions.json or an approval.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path

SCHEMA = 1
FILE = "01_analysis/emphasis.json"
FACES_FILE = "01_analysis/face-samples.json"
PARTS = ("loudness_z", "after_pause", "number", "client", "cta", "key")
CALM = {"storytelling", "drama", "emotional"}
ENERGETIC = {"advice", "bold_opinion", "success_story", "comedy"}
# starting values of ours (R-4.7), measured on our reels later; config/defaults/emphasis.json may replace each one
DEFAULTS = {"w_loud": 0.6, "w_pause": 0.2, "boost_number": 0.3, "boost_client": 0.2, "boost_cta": 0.2, "boost_key": 0.3,
            "pause_ms": 300, "neighbours": 8, "phrase_gap_ms": 250, "min_len_ms": 1200, "max_len_ms": 4000,
            "hook_ms": 1500, "tail_ms": 1500, "s_min": 1.05, "s_cap": 1.12, "margin": 0.06, "gap_calm_s": 6,
            "gap_energetic_s": 4, "gap_default_s": 6, "quota_window_s": 30, "sample_fps": 4, "near_ms": 125,
            "presence": 0.5, "no_face_scale": 1.05}
BASIS = "R-4.7 starting value, not measured"
HEAD_DEFAULT = {"top": 0.45, "bottom": 0.15, "side": 0.20}
HEAD_BASIS = "R-6.4 starting guess, not measured"
SENT = re.compile(r"[.!?؟…]\s*$")
OVERLAYS = {"name_card", "statement_highlight", "glass_card"}
STORY_CAMERA = {"punch_in", "slow_push", "reframe", "punch_out"}
WHY = {"hook": ("في أول ثانية ونص أو تحت عنوان الهوك (الهوك له معالجته)", "in the hook (the first 1.5 s or a hook title)"),
       "ending": ("في النهاية المحمية", "in the protected ending"),
       "cutaway": ("على لقطة معروضة كاملة (كارت أو بي رول من الحلقة)", "on a shot shown whole (a cutaway)"),
       "full_screen": ("تحت كارت full-screen", "under a full-screen card"),
       "camera": ("فوق حركة كاميرا من الستوري إديتور", "over a story-editor camera move"),
       "verse": ("على آية (المونتير بيضيفها يدوي)", "on a recited verse (the editor adds it by hand)"),
       "cut_word": ("الكلمة دي متقصوصة", "the word is cut"),
       "proposed": ("مقترح للقص", "inside a pre-ticked cut proposal"),
       "removed": ("في سكتة متشالة", "inside a removed pause"),
       "short": ("أقصر من 1.2 ث", "shorter than 1.2 s"),
       "near": ("قريب من punch أقوى", "too close to a stronger punch"),
       "quota": ("حد الـ recipe", "the recipe's punch-in limit per 30 s"),
       "edge": ("الوش قريب من طرف الكادر", "the face is too near the frame edge (s_max < 1.05)"),
       "closeup": ("لقطة قريبة أصلاً", "already a close-up (s_max < 1)"),
       "black_edge": ("هيبان طرف الصورة", "a black edge would show"),
       "shot": ("الكلمة على تغيير لقطة", "the word sits across a shot change")}
SIDE = {"cut": ("على قطع", "at a cut"), "start": ("في أول الريل", "at the start of the reel"),
        "end": ("في آخر الريل", "at the end of the reel"), "shot": ("على لقطة تانية", "at another shot"),
        "short": ("المقطع قصير", "too short for an ease"), "move": ("جنب حركة كاميرا تانية", "next to another camera move")}
NO_FACE = ("مفيش وش متقاس هنا، راجعها بنفسك", "no face measured here: check it yourself")
NO_SAMPLES = ("مفيش عينات للوش: شغّل reel emphasis --faces", "no face samples: run reel emphasis --faces")
NOT_MEASURED = ("الوش ماتقاسش، راجعها بنفسك", "the face was not measured: check it yourself")


# --------------------------------------------------------------------------- settings
def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def settings(ctx=None) -> dict:
    """{"values", "basis"}: DEFAULTS <- config/defaults/emphasis.json `values` (a number, or {value, basis}). A value
    that is not a finite number >= 0 keeps the starting value; a damaged file means the defaults."""
    from .common import load_config
    try:
        cfg = load_config("emphasis.json", ctx)
    except Exception:  # noqa: BLE001
        cfg = {}
    vals, basis = dict(DEFAULTS), {k: BASIS for k in DEFAULTS}
    over = cfg.get("values") if isinstance(cfg, dict) else None
    for k, v in (over.items() if isinstance(over, dict) else []):
        val = v.get("value") if isinstance(v, dict) else v
        if k in DEFAULTS and _num(val) is not None and val >= 0:
            vals[k] = val
            basis[k] = str(v.get("basis") or "config") if isinstance(v, dict) else "config"
    return {"values": vals, "basis": basis}


def head_ratio(ctx=None) -> dict:
    """{"value": {top, bottom, side}, "basis"}: motion.json `head_from_face` (R-6.4), else its starting guess."""
    from .common import load_config
    try:
        h = load_config("motion.json", ctx).get("head_from_face")
    except Exception:  # noqa: BLE001
        h = None
    val, basis = dict(HEAD_DEFAULT), HEAD_BASIS
    if isinstance(h, dict) and all(_num(h.get(k)) is not None and h[k] >= 0 for k in HEAD_DEFAULT):
        val = {k: float(h[k]) for k in HEAD_DEFAULT}
        basis = str(h.get("basis") or "config")
    return {"value": val, "basis": basis}


def min_gap_ms(recipe, v: dict) -> int:
    t = (recipe or {}).get("type")
    s = v["gap_energetic_s"] if t in ENERGETIC else v["gap_calm_s"] if t in CALM else v["gap_default_s"]
    return int(round(s * 1000))


def cap_for(recipe, v: dict) -> float:
    mx = _num(((recipe or {}).get("camera") or {}).get("max_scale"))
    return round(min(v["s_cap"], mx) if mx else v["s_cap"], 4)


def quota_for(recipe):
    q = _num(((recipe or {}).get("camera") or {}).get("punch_ins_per_30s"))
    return int(q) if q and q > 0 else None


# --------------------------------------------------------------------------- words and audio
def clean_words(raw) -> tuple:
    """(usable words in time order, skipped [{index, why}]). A record needs an id, a non-empty word, finite start and
    end with end > start, and a finite probability when it has one."""
    out, skipped = [], []
    for k, w in enumerate(raw or []):
        why = None
        if not isinstance(w, dict):
            why = "not a record"
        elif w.get("id") is None or isinstance(w.get("id"), bool):
            why = "no id"
        elif not isinstance(w.get("word"), str) or not w["word"].strip():
            why = "no word"
        elif _num(w.get("start_ms")) is None or _num(w.get("end_ms")) is None or w["end_ms"] <= w["start_ms"]:
            why = "bad times"
        elif "probability" in w and w["probability"] is not None and _num(w["probability"]) is None:
            why = "bad probability"
        if why:
            skipped.append({"index": k, "why": why})
        else:
            out.append((w["start_ms"], w["end_ms"], k, w))
    return [x[3] for x in sorted(out, key=lambda x: x[:3])], skipped


def read_wav(path):
    """(mono float64 samples in -1..1, rate) of an integer PCM WAV (16/24/32 bit), or None."""
    import wave
    import numpy as np
    try:
        with wave.open(str(path), "rb") as w:
            ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (OSError, EOFError, wave.Error):
        return None
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float64) / 8388608.0
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / 2147483648.0
    else:
        return None
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def read_footage_audio(path, rng: dict | None, sr: int = 16000):
    """The footage's own audio over the reel's range, mono at `sr` (ffmpeg), or None."""
    import subprocess
    import numpy as np
    from .common import ffmpeg_exe, range_input_args
    ff = ffmpeg_exe()
    if not ff or not Path(path).exists():
        return None
    try:
        p = subprocess.run([ff, "-hide_banner", "-loglevel", "error", *range_input_args(rng or {}), "-i", str(path),
                            "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    return np.frombuffer(p.stdout, "<i2").astype(np.float64) / 32768.0, sr


def word_levels(words: list, samples, sr: int) -> list:
    """Each word's RMS in dB (20 log10(rms + 1e-9)) over its own samples."""
    import numpy as np
    out = []
    for w in words:
        a, b = int(w["start_ms"] * sr // 1000), int(w["end_ms"] * sr // 1000)
        seg = samples[max(0, a):max(0, b)]
        rms = float(np.sqrt(np.mean(np.square(seg)))) if len(seg) else 0.0
        out.append(20 * math.log10(rms + 1e-9))
    return out


def loudness_z(levels: list, n: int = 8) -> list:
    """z of each level against its n nearest neighbours by position (n/2 each side; at the edges the n nearest; with
    fewer than n + 1 words, all the others). A spread of 0 gives 0."""
    N = len(levels)
    out = []
    for i in range(N):
        if N <= n + 1:
            nb = [levels[j] for j in range(N) if j != i]
        else:
            lo = max(0, min(i - n // 2, N - n - 1))
            nb = [levels[j] for j in range(lo, lo + n + 1) if j != i]
        if not nb:
            out.append(0.0)
            continue
        mean = sum(nb) / len(nb)
        sd = math.sqrt(sum((x - mean) ** 2 for x in nb) / len(nb))
        out.append(0.0 if sd < 1e-9 else (levels[i] - mean) / sd)
    return out


def after_pause(words: list, pause_ms: int = 300) -> list:
    return [1 if i == 0 or w["start_ms"] - words[i - 1]["end_ms"] >= pause_ms else 0 for i, w in enumerate(words)]


def number_words(words: list) -> set:
    """Indexes of the words of every spoken number (safety.numbers); an ambiguous one («ست», «ميت», "one") only with a
    unit or a time word next to it."""
    from .safety.numbers import find_numbers, fold, is_time, is_unit
    toks = [fold(w["word"]) for w in words]
    out = set()
    for h in find_numbers(toks):
        if h.get("ambiguous"):
            nb = [toks[h["end"]]] if h["end"] < len(toks) else []
            nb += [toks[h["start"] - 1]] if h["start"] > 0 else []
            if not any(t and (is_unit(t) or is_time(t)) for t in nb):
                continue
        out.update(range(h["start"], h["end"]))
    return out


def client_words(words: list, terms: list) -> set:
    """Indexes of words that say a client term (folded terms): the word or its clitic-free stem equals the term, or is
    one letter away from a term of 5+ letters; a term of several words matches them in a row."""
    from .safety.lexicon import near
    from .safety.numbers import fold, stems
    toks = [fold(w["word"]) for w in words]
    single = [t for t in terms or [] if t and " " not in t]
    multi = [t.split() for t in terms or [] if t and " " in t]
    out = set()
    for i, tok in enumerate(toks):
        forms = stems(tok) if tok else []
        if any(f == t or (len(t) >= 5 and len(f) >= 4 and near(f, t)) for f in forms for t in single):
            out.add(i)
        for m in multi:
            if i + len(m) <= len(toks) and m[0] in forms and toks[i + 1:i + len(m)] == m[1:]:
                out.update(range(i, i + len(m)))
    return out


def _norm_tokens(text) -> list:
    from .cut_proposals import norm_word
    return [norm_word(x) for x in str(text or "").split() if norm_word(x)]


def phrase_words(words: list, phrase) -> set:
    """Indexes of the words of every place `phrase` is said (the shared normaliser: alef forms, taa marbuta, tatweel,
    harakat, Arabic-Indic digits, case)."""
    from .cut_proposals import norm_word
    q = _norm_tokens(phrase)
    toks = [norm_word(w["word"]) for w in words]
    out = set()
    for i in range(len(toks) - len(q) + 1):
        if q and toks[i:i + len(q)] == q:
            out.update(range(i, i + len(q)))
    return out


def key_words(words: list, statements) -> tuple:
    """(indexes, notes): the statement analysis' `key_word` of each statement, found among the words inside that
    statement's time. No file or no key_word field anywhere -> nothing and one note; a key word that is not in its
    statement's text (or not said there) -> ignored with a note naming the statement."""
    from .cut_proposals import norm_word
    from .plan import _try_ms
    notes = []
    sts = statements if isinstance(statements, list) else []
    if not any(isinstance(s, dict) and "key_word" in s for s in sts):
        return set(), [_note("no_key_word", "مفيش key_word في تحليل الجمل، فمفيش زيادة للكلمة المهمة",
                             "no key_word in transcript-semantic-analysis.json: the key-word boost is 0")]
    out = set()
    toks = [norm_word(w["word"]) for w in words]
    for s in sts:
        if not isinstance(s, dict) or not s.get("key_word"):
            continue
        sid = s.get("statement_id") or "?"
        q, text = _norm_tokens(s["key_word"]), _norm_tokens(s.get("text"))
        inside = any(text[i:i + len(q)] == q for i in range(len(text) - len(q) + 1)) if q else False
        a, b = _try_ms(s.get("start")), _try_ms(s.get("end"))
        hit = None
        if inside and a is not None and b is not None:
            idx = [i for i, w in enumerate(words) if w["start_ms"] >= a - 40 and w["end_ms"] <= b + 40]
            for k in range(len(idx) - len(q) + 1):
                if [toks[j] for j in idx[k:k + len(q)]] == q:
                    hit = idx[k:k + len(q)]
                    break
        if hit:
            out.update(hit)
        else:
            notes.append(_note("bad_key_word", f"{sid}: الكلمة المهمة «{s['key_word']}» مش في نص الجملة دي، فاتجاهلت",
                               f"{sid}: key_word '{s['key_word']}' is not in that statement's words: ignored"))
    return out, notes


def score_words(words, levels, numbers, clients, ctas, keys, v: dict) -> list:
    """Each word's score parts and total (rounded to 4 decimals): loudness_z (raw), after_pause (0/1), and the boosts
    as added. total = w_loud × loudness_z + w_pause × after_pause + number + client + cta + key."""
    z = loudness_z(levels, int(v["neighbours"])) if levels else [0.0] * len(words)
    ap = after_pause(words, v["pause_ms"])
    out = []
    for i in range(len(words)):
        zr = round(z[i], 4)
        s = {"loudness_z": zr, "after_pause": ap[i], "number": v["boost_number"] if i in numbers else 0.0,
             "client": v["boost_client"] if i in clients else 0.0, "cta": v["boost_cta"] if i in ctas else 0.0,
             "key": v["boost_key"] if i in keys else 0.0}
        s["total"] = round(v["w_loud"] * zr + v["w_pause"] * ap[i] + s["number"] + s["client"] + s["cta"] + s["key"], 4)
        out.append(s)
    return out


def phrases(words: list, gap_ms: int, turns=None) -> list:
    """[(first, last)] word indexes: a phrase breaks at a gap >= gap_ms, after sentence punctuation, at a speaker turn."""
    def who(w):
        m = (w["start_ms"] + w["end_ms"]) / 2
        return next((t.get("speaker") for t in turns or [] if isinstance(t, dict)
                     and _num(t.get("start_ms")) is not None and t["start_ms"] <= m < (t.get("end_ms") or 0)), None)
    out = []
    for i, w in enumerate(words):
        if i == 0:
            out.append([0, 0])
            continue
        p = words[i - 1]
        a, b = who(p), who(w)
        if w["start_ms"] - p["end_ms"] >= gap_ms or SENT.search(p["word"]) or (a and b and a != b):
            out.append([i, i])
        else:
            out[-1][1] = i
    return [tuple(x) for x in out]


def rank_order(cands: list) -> list:
    return sorted(cands, key=lambda c: (-c["score"]["total"], c["start_ms"], str(c["word_ids"][0])))


def rank_ratios(scores: list) -> list:
    """[(rank, r)] for scores in rank order: dense rank (a tie shares it), r = 1 - (rank - 1)/(n - 1), n = distinct."""
    distinct = sorted(set(scores), reverse=True)
    n = len(distinct)
    out = []
    for s in scores:
        rank = distinct.index(s) + 1
        out.append((rank, 1.0 if n == 1 else round(1 - (rank - 1) / (n - 1), 4)))
    return out


def scale_for(s_max: float, r: float, s_min: float = 1.05) -> float:
    return min(s_max, round(s_min + (s_max - s_min) * r, 4))


# --------------------------------------------------------------------------- geometry
def geometry(dw, dh, W=1080, H=1920, S=None, box=0.0, boy=0.0, window=None, layer=None, cutaways=()) -> dict:
    """The framing a punch is measured in: source display size, sequence size, base scale S (fraction; None = fit),
    base offsets, the viewport (the frame or the 4:5 window), k45 (the window's extra zoom), the podcast shot layer and
    the single-camera cutaways."""
    S = float(S) if S else min(W / dw, H / dh)
    view = (0.0, float(window["y"]), float(W), float(window["y"] + window["h"])) if window else (0.0, 0.0, float(W), float(H))
    k45 = max(window["w"] / dw, window["h"] / dh) / S if window else None
    return {"W": W, "H": H, "dw": dw, "dh": dh, "S": S, "box": float(box or 0.0), "boy": float(boy or 0.0), "view": view,
            "k45": k45, "window": window, "layer": list(layer) if layer else None,
            "cutaways": [(int(a), int(b)) for a, b in cutaways or ()]}


def geometry_from(pre: dict, main_file, base: dict, style: dict, size, speakers: dict, podcast: dict) -> dict | None:
    """geometry() as `reel plan` frames THIS video (build_camera + apply_framing): explicit base scale, preflight's
    auto-reframe and its cutaways, the per-shot layer of a podcast reel, the 4:5 window. None without preflight."""
    from .plan import main_video, same_footage_name, window_rect
    v = main_video(pre or {}, main_file)
    if not v:
        return None
    W, H = size
    dw, dh = v["display_width"], v["display_height"]
    base = base or {}
    bsp, box, boy = base.get("base_scale_percent"), base.get("base_offset_x"), base.get("base_offset_y")
    layer, cut = None, []
    if bsp in (None, "auto"):
        rf = next((r for k, r in ((pre or {}).get("reframe") or {}).items() if main_file and same_footage_name(k, main_file)),
                  None)
        if rf:
            bsp = rf["base_scale_percent"]
            box = rf["offset_x"] if box is None else box
            boy = rf["offset_y"] if boy is None else boy
            cut = rf.get("cutaways_ms") or []
        else:
            bsp = None
        shots = ((pre or {}).get("shots") or {}).get("shots")
        if shots:
            from .shots import frame_shots
            pc = podcast or {}
            layer = frame_shots(shots, speakers, dw, dh, W, H, pc.get("speaker_min_hold_ms", 1500),
                                (pc.get("shots") or {}).get("group_fit", 0.8))
            bsp, box, boy, cut = round(max(W / dw, H / dh) * 100, 3), 0.0, 0.0, []
    framing = str(base.get("framing") or (style or {}).get("framing") or "9:16")
    win = window_rect(framing, base.get("framing_window_y"), W, H)
    return geometry(dw, dh, W, H, (float(bsp) / 100) if bsp else None, box or 0.0, boy or 0.0, win, layer,
                    cut if bsp else [])


def shot_at(fr: dict, t) -> dict | None:
    return next((c for c in fr.get("layer") or [] if c["decision_id"] != "AUTO_CUTAWAY" and c["at_ms"] <= t < c["until_ms"]),
                None)


def compose(fr: dict, t, k, ox, oy) -> tuple:
    """(picture scale P, centre x, centre y) on screen of a story move (scale k, offsets ox, oy) at reel time t, through
    the same composition `reel plan` uses (shots.compose_camera over the shot layer, then the 4:5 window)."""
    sf, xo, yo = float(k), float(ox), float(oy)
    h = shot_at(fr, t)
    if h is not None:
        from .shots import compose_camera
        got = compose_camera([{"decision_id": "EMP", "type": "punch_in", "at_ms": t, "until_ms": t + 1, "scale_factor": sf,
                               "offset_x": xo, "offset_y": yo}], [h], fr["dw"], fr["dh"], fr["W"], fr["H"])
        e = next(x for x in got if x["decision_id"] == "EMP")
        sf, xo, yo = float(e["scale_factor"]), float(e["offset_x"]), float(e["offset_y"])
    if fr.get("k45"):
        xo = round((fr["box"] * sf + xo) * fr["k45"] - fr["box"], 2)
        sf = round(sf * fr["k45"], 5)
    return fr["S"] * sf, fr["W"] / 2 + fr["box"] + xo, fr["H"] / 2 + fr["boy"] + yo


def head_box(face, ratio: dict) -> list:
    """A face box (cx, cy, w, h; 0..1 of the source) -> the head box [x0, y0, x1, y1] by the head_from_face ratio."""
    cx, cy, w, h = (float(x) for x in face[:4])
    return [cx - w / 2 - ratio["side"] * w, cy - h / 2 - ratio["top"] * h, cx + w / 2 + ratio["side"] * w,
            cy + h / 2 + ratio["bottom"] * h]


def _screen(fr, box, P, cx, cy) -> tuple:
    return (cx + (box[0] - 0.5) * fr["dw"] * P, cy + (box[1] - 0.5) * fr["dh"] * P,
            cx + (box[2] - 0.5) * fr["dw"] * P, cy + (box[3] - 0.5) * fr["dh"] * P)


def visible_share(fr: dict, face, P, cx, cy) -> float:
    """The share of a face box inside the viewport at (P, cx, cy)."""
    cxf, cyf, w, h = (float(x) for x in face[:4])
    x0, y0, x1, y1 = _screen(fr, [cxf - w / 2, cyf - h / 2, cxf + w / 2, cyf + h / 2], P, cx, cy)
    V = fr["view"]
    iw, ih = max(0.0, min(x1, V[2]) - max(x0, V[0])), max(0.0, min(y1, V[3]) - max(y0, V[1]))
    area = (x1 - x0) * (y1 - y0)
    return iw * ih / area if area > 0 else 0.0


def _covers(fr, P, cx, cy) -> tuple:
    V, hw, hh = fr["view"], fr["dw"] * P / 2, fr["dh"] * P / 2
    return (cx - hw <= V[0] + 0.01 and cx + hw >= V[2] - 0.01, cy - hh <= V[1] + 0.01 and cy + hh >= V[3] - 0.01)


def evaluate(fr: dict, env, t, s: float, margin: float) -> dict:
    """The story move of scale s that keeps the anchor (the head envelope's centre, or the viewport's centre when env is
    None) where it is, its offsets clamped so the picture keeps covering the viewport, composed for real; ok when the
    head envelope stays inside the viewport with `margin` of its sides and no black edge shows."""
    P0, cx0, cy0 = compose(fr, t, 1.0, 0.0, 0.0)
    V = fr["view"]
    if env is not None:
        ax = cx0 + ((env[0] + env[2]) / 2 - 0.5) * fr["dw"] * P0
        ay = cy0 + ((env[1] + env[3]) / 2 - 0.5) * fr["dh"] * P0
    else:
        ax, ay = (V[0] + V[2]) / 2, (V[1] + V[3]) / 2
    cov_x, cov_y = _covers(fr, P0, cx0, cy0)
    cx1, cy1 = ax + (cx0 - ax) * s, ay + (cy0 - ay) * s
    hw, hh = fr["dw"] * P0 * s / 2, fr["dh"] * P0 * s / 2
    if cov_x:
        cx1 = min(max(cx1, V[2] - hw), V[0] + hw)
    if cov_y:
        cy1 = min(max(cy1, V[3] - hh), V[1] + hh)
    tx, ty = cx1 - fr["W"] / 2 - fr["box"], cy1 - fr["H"] / 2 - fr["boy"]
    h = shot_at(fr, t)
    sf_c = (float(h["scale_factor"]) if h else 1.0) * s
    xo = (tx + fr["box"]) / fr["k45"] - fr["box"] * sf_c if fr.get("k45") else tx
    ox = round(xo - float(h["offset_x"]) * s if h else xo, 2)
    oy = round(ty, 2)
    P, cx, cy = compose(fr, t, s, ox, oy)
    ex, ey = _covers(fr, P, cx, cy)
    edge_ok = (ex or not cov_x) and (ey or not cov_y)
    head_ok = True
    if env is not None:
        x0, y0, x1, y1 = _screen(fr, env, P, cx, cy)
        mx, my = margin * (V[2] - V[0]), margin * (V[3] - V[1])
        head_ok = x0 >= V[0] + mx - 1e-6 and x1 <= V[2] - mx + 1e-6 and y0 >= V[1] + my - 1e-6 and y1 <= V[3] - my + 1e-6
    return {"ok": edge_ok and head_ok, "why": None if edge_ok and head_ok else ("black_edge" if not edge_ok else "edge"),
            "offset_x": ox, "offset_y": oy, "P": P, "cx": cx, "cy": cy}


def s_max(fr: dict, env, t, cap: float, margin: float, step: float = 0.0005) -> dict:
    """{"s_max": the largest safe scale <= cap (floored to 4 decimals), or None below 1, "why": the failing reason}."""
    first = evaluate(fr, env, t, 1.0, margin)
    if not first["ok"]:
        P0, cx0, cy0 = compose(fr, t, 1.0, 0.0, 0.0)
        x0, y0, x1, y1 = _screen(fr, env, P0, cx0, cy0)
        V = fr["view"]
        big = (x1 - x0) > (1 - 2 * margin) * (V[2] - V[0]) or (y1 - y0) > (1 - 2 * margin) * (V[3] - V[1])
        return {"s_max": None, "why": "closeup" if big else first["why"]}
    lo, hi, why = 1.0, None, None
    k = 1
    while 1.0 + k * step <= cap + 1e-12:
        r = evaluate(fr, env, t, 1.0 + k * step, margin)
        if not r["ok"]:
            hi, why = 1.0 + k * step, r["why"]
            break
        lo = 1.0 + k * step
        k += 1
    if hi is None:
        if evaluate(fr, env, t, cap, margin)["ok"]:
            return {"s_max": round(cap, 4), "why": None}
        hi = cap
        why = evaluate(fr, env, t, cap, margin)["why"]
    for _ in range(30):
        mid = (lo + hi) / 2
        if evaluate(fr, env, t, mid, margin)["ok"]:
            lo = mid
        else:
            hi = mid
    return {"s_max": math.floor(lo * 10000 + 1e-9) / 10000, "why": why}


def protected(fr: dict, faces: list, t, speakers: dict | None, presence: float) -> list:
    """The faces of one sample a punch must keep inside: >= `presence` of the box visible in the unpunched viewport,
    plus the speaker the shot follows (its seating position)."""
    P0, cx0, cy0 = compose(fr, t, 1.0, 0.0, 0.0)
    keep = [f for f in faces if visible_share(fr, f, P0, cx0, cy0) >= presence]
    h = shot_at(fr, t)
    who = (h or {}).get("target")
    pos = (((speakers or {}).get("people") or {}).get(who) or {}).get("position") if who else None
    if pos and faces:
        srt = sorted(faces, key=lambda f: f[0])
        f = {"left": srt[0], "right": srt[-1], "center": min(srt, key=lambda f: abs(f[0] - 0.5))}.get(pos)
        if f is not None and f not in keep:
            keep.append(f)
    return keep


# --------------------------------------------------------------------------- time
class Clock:
    """Source ms <-> sequence ms over the kept ranges (continuous; the plan's TimeMap quantises to frames)."""

    def __init__(self, keep):
        self.keep = [(float(a), float(b)) for a, b in keep if b > a]
        self.total = sum(b - a for a, b in self.keep)

    def seq(self, t) -> float:
        s = 0.0
        for a, b in self.keep:
            if t <= a:
                return s
            if t < b:
                return s + (t - a)
            s += b - a
        return s

    def src(self, x) -> float:
        s = 0.0
        for a, b in self.keep:
            if x < s + (b - a):
                return a + max(0.0, x - s)
            s += b - a
        return self.keep[-1][1] if self.keep else x


def _note(code, ar, en) -> dict:
    return {"code": code, "ar": ar, "en": en}


def _ed_events(ed: dict) -> list:
    """The graphics of edit-decisions.json on the source clock (unreadable times are left to the plan to report)."""
    from .plan import _try_ms
    out = []
    for d in (ed or {}).get("decisions") or []:
        if not isinstance(d, dict):
            continue
        for g in d.get("graphics") or []:
            if not isinstance(g, dict):
                continue
            a, b = _try_ms(g.get("start", d.get("start"))), _try_ms(g.get("end", d.get("end")))
            if a is None or b is None or b <= a:
                continue
            out.append({"event_id": g.get("id"), "template": g.get("template"), "start_ms": a, "end_ms": b,
                        "params": {k: v for k, v in g.items() if k not in ("id", "template", "start", "end")}})
    return out


def _ed_camera(ed: dict) -> list:
    from .plan import _try_ms
    out = []
    for d in (ed or {}).get("decisions") or []:
        cam = d.get("camera") if isinstance(d, dict) else None
        if not isinstance(cam, dict) or cam.get("type") not in STORY_CAMERA:
            continue
        a = _try_ms(cam.get("at", d.get("start")))
        b = _try_ms(cam["until"]) if cam.get("until") else _try_ms(d.get("end"))
        if a is None or b is None or b <= a:
            continue
        out.append({"decision_id": d.get("decision_id"), "type": cam["type"], "at_ms": a, "until_ms": b,
                    "emphasis": isinstance(cam.get("emphasis"), dict)})
    return out


def _overlap(a, b, c, d) -> bool:
    return a < d and c < b


# --------------------------------------------------------------------------- ease prediction (T4.1)
def predict_ease(fr, a, b, keep, clock: Clock, ease_ms: int, fps, scale: float, moves=()) -> dict:
    """{"in", "out"}: "eased" or "hard: <why>", from camera_ease.ease_keys run on the pieces the plan will cut around
    the punch (a cut, the reel's start or end, another shot, a piece too short for an ease)."""
    from .camera_ease import ease_keys
    from .common import ms_to_frame
    if fr and fr.get("k45"):
        return {"in": "hard: 4:5 window", "out": "hard: 4:5 window"}
    if not ease_ms:
        return {"in": "hard: smooth zoom off", "out": "hard: smooth zoom off"}
    f = lambda t: ms_to_frame(int(round(clock.seq(t))), fps)          # noqa: E731
    f0, f1, fend = f(a), f(b), ms_to_frame(int(round(clock.total)), fps)
    ki = next((i for i, (x, y) in enumerate(keep) if x <= a and b <= y), 0)
    ka, kb = keep[ki] if keep else (0, clock.total)
    h = shot_at(fr, a) if fr else None
    sox = float(h["offset_x"]) if h else None
    punch = {"start_frame": f0, "end_frame": f1, "camera": "punch_in", "decision_id": "EMP", "scale_factor": scale,
             "offset_x": 0.0, "offset_y": 0.0, "keep_index": ki, "src_in_ms": a, "src_out_ms": b}
    if sox is not None:
        punch.update(shot_offset_x=sox, _shots=True)

    def nb(side):
        t, kt, f_ = (a, ka, f0) if side == "in" else (b, kb, f1)
        if (side == "in" and f_ <= 0) or (side == "out" and f_ >= fend):
            return None, "start" if side == "in" else "end"
        cut = f(kt) == f_ and ((side == "in" and ki > 0) or (side == "out" and ki < len(keep) - 1))
        other = None
        if fr and fr.get("layer"):
            other = next((c for c in fr["layer"] if (c["until_ms"] == (h or {}).get("at_ms") if side == "in"
                                                     else c["at_ms"] == (h or {}).get("until_ms"))), None)
            if other is not None and f(other["until_ms"] if side == "in" else other["at_ms"]) != f_:
                other = None
        seg = {"start_frame": f_ - 10 if side == "in" else f_, "end_frame": f_ if side == "in" else f_ + 10,
               "camera": "hold", "decision_id": "AUTO_SHOT" if sox is not None else None, "scale_factor": 1.0,
               "offset_x": sox or 0.0, "offset_y": 0.0, "keep_index": ki,
               "src_in_ms": (t - 400) if side == "in" else t, "src_out_ms": t if side == "in" else t + 400}
        if cut:
            seg.update(keep_index=ki - 1 if side == "in" else ki + 1,
                       src_out_ms=t - 1000 if side == "in" else seg["src_out_ms"],
                       src_in_ms=seg["src_in_ms"] if side == "in" else t + 1000)
            return seg, "cut"
        mv = next((m for m in moves or () if f(m["at_ms"] if side == "out" else m["until_ms"]) == f_), None)
        if mv is not None:                        # a story move right next to it: T4.1 decides between the two moves
            seg.update(decision_id=mv["decision_id"], camera=mv["type"], scale_factor=1.0 + 0.5)
            return seg, "move"
        if other is not None:
            seg.update(decision_id=other["decision_id"], offset_x=float(other["offset_x"]),
                       scale_factor=float(other["scale_factor"]))
            if other["decision_id"] == "AUTO_SHOT" and abs(float(other["offset_x"]) - (sox or 0.0)) <= 0.5:
                seg["offset_x"] = (sox or 0.0) + 1.0                      # another shot that frames the same column
            return seg, "shot"
        return seg, None
    prev, why_in = nb("in")
    nxt, why_out = nb("out")
    segs = [x for x in (prev, punch, nxt) if x is not None]
    runs = [r for r in ease_keys(segs, fps, ease_ms) if r["decision_id"] == "EMP"]
    ein = bool(runs and runs[0].get("ease_in"))
    eout = bool(runs and runs[0].get("ease_out"))
    return {"in": "eased" if ein else f"hard: {SIDE[why_in or 'short'][1]}",
            "out": "eased" if eout else f"hard: {SIDE[why_out or 'short'][1]}", "_why": (why_in, why_out)}


def _ease_words(ease: dict) -> tuple:
    if ease["in"] == "hard: 4:5 window":
        return "في شباك 4:5 الزوم حاد", "in the 4:5 window the zoom is hard"
    if ease["in"] == "hard: smooth zoom off":
        return "الزوم الناعم مقفول (camera.ease_ms 0): الزوم حاد", "the smooth zoom is off (camera.ease_ms 0): hard zoom"
    wi, wo = ease.get("_why") or (None, None)
    ar = ["الدخول ناعم" if ease["in"] == "eased" else f"الدخول حاد لأنه {SIDE[wi or 'short'][0]}",
          "الخروج ناعم" if ease["out"] == "eased" else f"الخروج حاد لأنه {SIDE[wo or 'short'][0]}"]
    en = ["eases in" if ease["in"] == "eased" else f"hard in ({SIDE[wi or 'short'][1]})",
          "eases out" if ease["out"] == "eased" else f"hard out ({SIDE[wo or 'short'][1]})"]
    return "، ".join(ar), "; ".join(en)


# --------------------------------------------------------------------------- the pure build
def build(inp: dict) -> dict:
    """emphasis.json from the gathered inputs (pure; see gather())."""
    from . import endings
    from .common import fmt_ts
    from .plan import subtract_ranges, union_ranges, word_cut_ranges
    v = inp["settings"]["values"]
    ratio = inp["head"]["value"]
    notes = []
    words, skipped = clean_words(inp.get("words"))
    if skipped:
        notes.append(_note("bad_words", f"في {len(skipped)} كلمة في words.json ناقصة أو بايظة ومش هتتحسب",
                           f"{len(skipped)} word record(s) in words.json skipped (no id, word or valid times): "
                           + ", ".join(f"#{s['index']} {s['why']}" for s in skipped[:8])))
    recipe = inp.get("recipe") or None
    rtype = (recipe or {}).get("type")
    cap, gap, quota = cap_for(recipe, v), min_gap_ms(recipe, v), quota_for(recipe)
    ed = inp.get("ed") if isinstance(inp.get("ed"), dict) else {}
    g = ed.get("global") if isinstance(ed.get("global"), dict) else {}
    levels = inp.get("levels")
    if levels is None or len(levels) != len(words):
        levels = None
        notes.append(_note("no_audio", "مفيش صوت متنضف، الترتيب بالكلام بس",
                           "no cleaned dialogue or footage audio: the ranking uses the words only (loudness 0)"))
    cfg = inp.get("endings") or endings.config({}, {})
    kw, kw_note = endings.cta_keyword(cfg, inp.get("lang") or "ar")
    if kw_note:
        notes.append(_note("cta_keyword", kw_note["ar"], kw_note["en"]))
    keys, key_notes = key_words(words, inp.get("statements"))
    notes += key_notes
    scores = score_words(words, levels, number_words(words), client_words(words, inp.get("terms") or []),
                         phrase_words(words, kw) if kw else set(), keys, v)
    fr = inp.get("frame")
    faces = inp.get("faces") or {"status": "missing", "doc": None}
    fdoc = faces.get("doc") if faces.get("status") == "ok" else None
    doc = {"schema": SCHEMA, "video_id": inp.get("video_id"), "inputs_sha1": inp.get("inputs_sha1"),
           "detector": (faces.get("doc") or {}).get("detector") if faces.get("status") == "ok" else None,
           "head_from_face": inp["head"],
           "settings": {"min_gap_ms": gap, "cap": cap, "quota_per_30s": quota, "recipe": rtype,
                        "remove_pauses": bool(inp.get("remove_pauses")), "ease_ms": inp.get("ease_ms"),
                        "audio": inp.get("audio_source") if levels is not None else None,
                        "framing": (fr or {}).get("window", {}).get("mode") if (fr or {}).get("window") else "9:16",
                        "values": v, "basis": inp["settings"]["basis"]},
           "candidates": [], "dropped": [], "notes": notes,
           "scored": [{"id": w["id"], "word": w["word"], "start_ms": w["start_ms"], "end_ms": w["end_ms"], "score": s}
                      for w, s in zip(words, scores)],
           "how": {"ar": "ده اقتراح بس: الستوري إديتور ينسخ «decision» بتاع اللي هيحتفظ بيه في edit-decisions.json، بعدين "
                         "reel plan وموافقة. ماينفعش تكبّر الزوم فوق s_max.",
                   "en": "suggestions only: the story-editor copies the `decision` of each one it keeps into "
                         "edit-decisions.json, then `reel plan` and an approval. Never raise the scale above s_max."}}
    if rtype == "emotional":
        notes.append(_note("emotional", "النوع ده زوم بطيء بس", "an emotional reel: slow push only, no punch-ins"))
        return doc
    if not words:
        notes.append(_note("none", "مفيش punch مقترح في الريل ده", "no punch-in proposed for this reel"))
        return doc
    dur = float(inp.get("media_end_ms") or words[-1]["end_ms"])
    # kept ranges: removed pauses (+ protected ones), accepted word cuts; a pre-ticked proposal only limits a span
    keep = [[0, dur]]
    pz = inp.get("pauses") if isinstance(inp.get("pauses"), dict) else None
    if inp.get("remove_pauses") and pz and isinstance(pz.get("keep_ms"), list):
        keep = [list(k) for k in pz["keep_ms"]]
        rp = g.get("remove_pauses")
        prot = [list(p) for p in (rp.get("protect") or [])] if isinstance(rp, dict) else []
        prot = [p for p in prot if isinstance(p, list) and len(p) == 2 and all(_num(x) is not None for x in p)]
        if prot:
            keep = union_ranges(keep, prot)
    wranges, wcut, _ = word_cut_ranges([w for w in words if isinstance(w["id"], int)], g.get("cut_words") or [], dur)
    cut_ids = {c["word_id"] for c in wcut}
    if wranges:
        keep = subtract_ranges(keep, wranges)
    keep = [tuple(k) for k in keep]
    clock = Clock(keep)
    props = [p for p in inp.get("proposals") or [] if isinstance(p, dict) and _num(p.get("start_ms")) is not None
             and _num(p.get("end_ms")) is not None]
    ticked = [p for p in props if p.get("default") == "proposed"]
    limits = subtract_ranges([list(k) for k in keep], [[p["start_ms"], p["end_ms"]] for p in ticked]) if ticked else keep
    limits = [tuple(k) for k in limits]
    # zones a punch never touches (source clock)
    events = _ed_events(ed)
    from .qc import FULL_SCREEN
    zones = [(e["start_ms"], e["end_ms"], "full_screen") for e in events if e["template"] in FULL_SCREEN]
    zones += [(e["start_ms"], e["end_ms"], "hook") for e in events if e["template"] == "hook_title"]
    moves = [c for c in _ed_camera(ed) if not c["emphasis"]]
    zones += [(c["at_ms"], c["until_ms"], "camera") for c in moves]
    zones += [(float(a), float(b), "verse") for a, b in inp.get("verse") or []]
    if fr:
        zones += [(a, b, "cutaway") for a, b in fr.get("cutaways") or []]
        zones += [(c["at_ms"], c["until_ms"], "cutaway") for c in fr.get("layer") or [] if c["decision_id"] == "AUTO_CUTAWAY"]
    span = endings.sign_off_span(inp.get("words") or [], cfg, inp.get("marker_ms"), dur)
    cards = [e for e in events if endings.card_role(e)]
    end_src = endings.ending_start(span, cards)
    tail = end_src is None
    if tail:
        end_src = clock.src(max(0.0, clock.total - v["tail_ms"]))
    hook_src = clock.src(v["hook_ms"])
    shots = [c for c in (fr or {}).get("layer") or [] if c["decision_id"] != "AUTO_CUTAWAY"]
    cands = []
    drops = []

    def drop(ids, a, b, code, word):
        drops.append({"word_ids": ids, "word": word, "start_ms": a, "end_ms": b, "code": code, "why": WHY[code][0],
                      "why_en": WHY[code][1]})
    for i0, i1 in phrases(words, v["phrase_gap_ms"], (inp.get("speakers") or {}).get("turns")):
        top = min(range(i0, i1 + 1), key=lambda i: (-scores[i]["total"], words[i]["start_ms"], str(words[i]["id"])))
        w = words[top]
        ws_, we_ = w["start_ms"], w["end_ms"]
        ids = [w["id"]]
        code = None
        if w["id"] in cut_ids:
            code = "cut_word"
        elif any(_overlap(ws_, we_, p["start_ms"], p["end_ms"]) or w["id"] in (p.get("word_ids") or []) for p in ticked):
            code = "proposed"
        elif ws_ < hook_src - 1e-9:
            code = "hook"
        elif we_ > end_src + 1e-9:
            code = "ending"
        else:
            hit = next((z for z in sorted(zones) if _overlap(ws_, we_, z[0], z[1])), None)
            if hit:
                code = hit[2]
            elif not any(a <= ws_ and we_ <= b for a, b in limits):
                code = "removed"
        if code:
            drop(ids, ws_, we_, code, w["word"])
            continue
        L = max([a for a, b in limits if a <= ws_ and we_ <= b] + [hook_src]
                + [z[1] for z in zones if z[1] <= ws_] + [c["at_ms"] for c in shots if c["at_ms"] <= ws_ < c["until_ms"]])
        R = min([b for a, b in limits if a <= ws_ and we_ <= b] + [end_src]
                + [z[0] for z in zones if z[0] >= we_] + [c["until_ms"] for c in shots if c["at_ms"] <= ws_ < c["until_ms"]])
        if R < we_ - 1e-9:
            drop(ids, ws_, we_, "shot", w["word"])
            continue
        run = [j for j in range(i0, i1 + 1) if words[j]["start_ms"] >= L - 1e-9 and words[j]["end_ms"] <= R + 1e-9]
        # the contiguous run of the phrase's allowed words around the top word
        k0 = k1 = run.index(top)
        while k0 > 0 and run[k0 - 1] == run[k0] - 1:
            k0 -= 1
        while k1 + 1 < len(run) and run[k1 + 1] == run[k1] + 1:
            k1 += 1
        span_ix = run[k0:k1 + 1]
        a = words[span_ix[0]]["start_ms"]
        if w["end_ms"] - a > v["max_len_ms"]:
            span_ix = [j for j in span_ix if j >= top]
            a = w["start_ms"]
        span_ix = [j for j in span_ix if words[j]["end_ms"] - a <= v["max_len_ms"] or j == top]
        b = words[span_ix[-1]]["end_ms"]
        j = span_ix[-1] + 1
        while b - a < v["min_len_ms"] and j < len(words) and words[j]["end_ms"] <= R + 1e-9 \
                and words[j]["start_ms"] >= words[j - 1]["end_ms"] - 1e-9 and words[j]["end_ms"] - a <= v["max_len_ms"]:
            span_ix.append(j)
            b = words[j]["end_ms"]
            j += 1
        if b - a < v["min_len_ms"]:
            cut_by_end = R == end_src and words[i1]["end_ms"] > R + 1e-9
            drop(ids, a, b, "ending" if cut_by_end else "short", w["word"])
            continue
        cands.append({"top": top, "word_ids": [words[j]["id"] for j in span_ix], "word": w["word"], "start_ms": a,
                      "end_ms": b, "score": scores[top], "_ids": ids,
                      "evidence": " ".join(words[j]["word"] for j in span_ix)})
    # face safety
    status = faces.get("status")
    review_all = None
    if not fr:
        review_all = NOT_MEASURED
        notes.append(_note("no_preflight", "مفيش preflight للفيديو ده، فالوش ماتقاسش: شغّل reel preflight",
                           "no preflight for this footage, so no face could be measured: run reel preflight"))
    elif status == "missing":
        review_all = NO_SAMPLES
    elif status == "damaged":
        review_all = NOT_MEASURED
        notes.append(_note("faces_damaged", "ملف عينات الوش بايظ: شغّل reel emphasis --faces تاني",
                           "01_analysis/face-samples.json is damaged: run reel emphasis --faces again"))
    elif status == "stale":
        review_all = NOT_MEASURED
        notes.append(_note("faces_stale", "عينات الوش متعملة لفيديو أو مدى تاني: شغّل reel emphasis --faces تاني",
                           "the face samples were taken from another footage or range: run reel emphasis --faces again"))
    elif fdoc and fdoc.get("notes"):
        review_all = NOT_MEASURED
        notes.append(_note("face_model_off", "كشف الوشوش ماشتغلش على الجهاز ده: شغّل reel doctor",
                           "face detection could not run on this computer (" + "; ".join(map(str, fdoc["notes"]))[:200]
                           + "): run reel doctor"))
    samples = sorted((s for s in (fdoc or {}).get("samples") or [] if isinstance(s, dict) and _num(s.get("t_ms")) is not None),
                     key=lambda s: s["t_ms"])
    measured = []
    for c in cands:
        a, b = c["start_ms"], c["end_ms"]
        c["warnings"], c["extra"] = [], []
        if review_all:
            c.update(needs_review=True, s_max=None, faces_used=[], review=review_all)
            measured.append(c)
            continue
        use = {s["t_ms"]: s for s in samples if a <= s["t_ms"] <= b}
        for t in (a, (a + b) / 2, b):
            if not samples:
                break
            nearest = min(samples, key=lambda s: (abs(s["t_ms"] - t), s["t_ms"]))
            use[nearest["t_ms"]] = nearest
            d = abs(nearest["t_ms"] - t)
            if d > v["near_ms"]:
                c["extra"].append((f"أقرب عينة على بعد {int(round(d))} ms", f"nearest face sample {int(round(d))} ms away"))
        heads = []
        for t in sorted(use):
            fs = [f for f in use[t].get("faces") or [] if isinstance(f, (list, tuple)) and len(f) >= 4]
            heads += [head_box(f, ratio) for f in protected(fr, fs, max(a, min(b, t)), inp.get("speakers"), v["presence"])]
        c["faces_used"] = sorted(use)
        if not heads:
            c.update(needs_review=True, s_max=None, review=NO_FACE)
            measured.append(c)
            continue
        env = [min(h[0] for h in heads), min(h[1] for h in heads), max(h[2] for h in heads), max(h[3] for h in heads)]
        r = s_max(fr, env, a, cap, v["margin"])
        if r["s_max"] is None or r["s_max"] < v["s_min"]:
            code = r["why"] if r["s_max"] is None else ("black_edge" if r["why"] == "black_edge" else "edge")
            drop(c["_ids"], a, b, code, c["word"])
            continue
        c.update(needs_review=False, s_max=r["s_max"], env=env)
        measured.append(c)
    # spacing: greedy by score, the gap between punch starts and the recipe quota, on the sequence clock
    placed = []
    win = v["quota_window_s"] * 1000
    for c in rank_order(measured):
        sc = clock.seq(c["start_ms"])
        if any(abs(sc - clock.seq(p["start_ms"])) < gap - 1e-9 for p in placed):
            drop(c["_ids"], c["start_ms"], c["end_ms"], "near", c["word"])
            continue
        if quota:
            starts = [clock.seq(p["start_ms"]) for p in placed] + [sc]
            if max(sum(1 for x in starts if s <= x < s + win) for s in starts) > quota:
                drop(c["_ids"], c["start_ms"], c["end_ms"], "quota", c["word"])
                continue
        placed.append(c)
    # rank, scale, offsets, ease, words
    tpl = inp.get("templates")
    if tpl is None:
        from .common import load_config
        tpl = load_config("graphics-templates.json").get("templates", {})
    out = []
    for (rank, r), c in zip(rank_ratios([c["score"]["total"] for c in placed]), placed):
        a, b = c["start_ms"], c["end_ms"]
        if c["needs_review"]:
            scale = v["no_face_scale"]
            ev = evaluate(fr, None, a, scale, v["margin"]) if fr else {"offset_x": 0.0, "offset_y": 0.0}
        else:
            scale = scale_for(c["s_max"], r, v["s_min"])
            ev = evaluate(fr, c["env"], a, scale, v["margin"])
            while not ev["ok"] and scale > v["s_min"]:
                scale = round(scale - 0.0001, 4)
                ev = evaluate(fr, c["env"], a, scale, v["margin"])
            if not ev["ok"]:                       # never ship a punch that failed its own check
                drop(c["_ids"], a, b, ev["why"] or "edge", c["word"])
                continue
        c.update(rank=rank, r=r, scale=scale, offset_x=ev["offset_x"], offset_y=ev["offset_y"])
        c["ease"] = predict_ease(fr, a, b, keep, clock, inp.get("ease_ms") or 0, inp.get("fps") or 24, scale, moves)
        for p in props:
            if p.get("default") != "proposed" and _overlap(a, b, p["start_ms"], p["end_ms"]):
                c["warnings"].append(_note("unticked_proposal",
                                           f"فيه اقتراح قص مش متعلّم ({p.get('id', '?')}) جوه الـ punch: لو علّمته الـ punch هيتقاس تاني",
                                           f"an unticked cut proposal ({p.get('id', '?')}) lies inside the punch: if you "
                                           "accept it, re-run reel emphasis"))
        if not c["needs_review"] and fr:
            c["warnings"] += _overlay_warnings(fr, c, events, tpl, ev)
        out.append(c)
    for n, c in enumerate(sorted(out, key=lambda c: (c["start_ms"], str(c["word_ids"][0]))), 1):
        doc["candidates"].append(_record(n, c, inp, fmt_ts))
    doc["dropped"] = sorted(drops, key=lambda d: (d["start_ms"], str(d["word_ids"][0])))
    if not doc["candidates"]:
        notes.append(_note("none", "مفيش punch مقترح في الريل ده", "no punch-in proposed for this reel"))
    return doc


def _overlay_warnings(fr, c, events, tpl, ev) -> list:
    """Advisory (R-6.4 owns the gate): a face-anchored overlay during the punch whose estimated box (its template's y
    and width) covers the punched head box."""
    from . import safe_zones
    out = []
    hb = _screen(fr, c["env"], ev["P"], ev["cx"], ev["cy"])
    prof = None
    for e in events:
        if e["template"] not in OVERLAYS or not _overlap(c["start_ms"], c["end_ms"], e["start_ms"], e["end_ms"]):
            continue
        t = tpl.get(e["template"]) or {}
        W = fr["W"]
        bw = float(t.get("w") or 900) * W / 1080
        size = float(t.get("size") or t.get("name_size") or 54) * W / 1080
        y = float(t.get("y") or fr["H"] * 0.6) * W / 1080
        box = {"id": e["event_id"], "kind": "shape", "rect": [(W - bw) / 2, y, (W + bw) / 2, y + 3 * size],
               "label": e["template"]}
        prof = prof or safe_zones.load(frame=(fr["W"], fr["H"]))
        if any(f.get("kind") == "face" for f in safe_zones.violations([box], prof, face=list(hb))):
            out.append(_note("overlay_face", f"{e['event_id']} ({e['template']}) ممكن يغطي الوش وقت الـ punch: بص عليه",
                             f"{e['event_id']} ({e['template']}) may cover the face during the punch: check it"))
    return out


def _record(n, c, inp, fmt_ts) -> dict:
    parts = []
    s = c["score"]
    for k, ar, en in (("number", "رقم", "number"), ("client", "اسم العميل أو المنتج", "client term"),
                      ("cta", "كلمة الـ CTA", "CTA keyword"), ("key", "الكلمة المهمة", "key word")):
        if s[k]:
            parts.append((ar, en))
    if s["after_pause"]:
        parts.append(("بعد سكتة", "after a pause"))
    if s["loudness_z"] >= 1:
        parts.append(("بصوت أعلى", "louder"))
    why_ar = "، ".join(p[0] for p in parts) or "أعلى كلمة في الجملة"
    why_en = ", ".join(p[1] for p in parts) or "the strongest word of its phrase"
    ea, ee = _ease_words(c["ease"])
    ar = [f"punch على «{c['word']}» ({why_ar})", ea] + [x[0] for x in c["extra"]]
    en = [f"punch on «{c['word']}» ({why_en})", ee] + [x[1] for x in c["extra"]]
    if c["needs_review"]:
        ar.append(c["review"][0])
        en.append(c["review"][1])
    ease = {k: c["ease"][k] for k in ("in", "out")}
    did = f"EMPH_{n:02d}"
    cid = f"EMP_{n:02d}"
    return {"id": cid, "word_ids": c["word_ids"], "word": c["word"], "start_ms": c["start_ms"], "end_ms": c["end_ms"],
            "score": dict(s), "rank": c["rank"], "r": c["r"], "s_max": c["s_max"], "scale": c["scale"],
            "offset_x": c["offset_x"], "offset_y": c["offset_y"], "faces_used": c["faces_used"], "ease": ease,
            "needs_review": c["needs_review"], "default_keep": not c["needs_review"], "reason": " · ".join(ar),
            "reason_en": " · ".join(en), "warnings": c["warnings"],
            "decision": {"decision_id": did, "segment_id": "EMPHASIS", "evidence": c["evidence"],
                         "start": fmt_ts(c["start_ms"], "."), "end": fmt_ts(c["end_ms"], "."),
                         "semantic_intent": "emphasis", "visual_treatment": "punch_in", "confidence": "medium",
                         "camera": {"type": "punch_in", "at": fmt_ts(c["start_ms"], "."), "until": fmt_ts(c["end_ms"], "."),
                                    "scale_factor": c["scale"], "offset_x": c["offset_x"], "offset_y": c["offset_y"],
                                    "rationale": " · ".join(en),
                                    "emphasis": {"candidate": cid, "inputs_sha1": inp.get("inputs_sha1"),
                                                 "s_max": c["s_max"], "needs_review": c["needs_review"]}}}}


# --------------------------------------------------------------------------- the plan's re-check (`reel plan`)
def plan_inputs(paths, ctx, main_file, rng: dict, pre: dict) -> dict:
    """What `reel plan` reads for the re-check (in read_inputs): the face samples and their status, the candidates
    file, the current inputs hash, the settings and the head ratio."""
    from .plan import main_video
    v = main_video(pre or {}, main_file)
    fr = {"dw": v["display_width"], "dh": v["display_height"]} if v else None
    _, doc = _read(paths.p(FILE))
    return {"faces": load_samples(paths, main_file, rng, fr), "doc": doc if isinstance(doc, dict) else None,
            "sha1": inputs_sha1(paths, ctx), "settings": settings(ctx), "head": head_ratio(ctx)}


def _ms_clock(v) -> str:
    v = max(0, int(round(float(v))))
    return f"{v // 60000:02d}:{v % 60000 / 1000:05.2f}"


def plan_check(inp, cam: dict, fr: dict, tm: dict) -> tuple:
    """The plan step after the time map (3.0 Task 29): every story punch_in re-checked against the face samples on the
    COMPOSED camera (apply_framing's layer: the shot layer and the 4:5 window applied); a stored s_max is never trusted.
    (errors, warnings, info):
      - an emphasis punch (camera.emphasis) that crops the head: an error naming the safe scale; a plain punch_in: a
        warning (Q15);
      - any story move whose composed offsets show a black edge: a warning with the allowed offsets;
      - an emphasis punch moved from its candidate's times is measured at its new times; no face sample there, or no
        samples at all: needs review (never passed silently);
      - candidates made from other inputs: one warning (run reel emphasis again);
      - an emphasis punch across a cut (a removed pause or a cut word): a warning (the jump-cut zoom would step it).
    info = {"kept": n, "review": [{decision_id, start_ms, end_ms (sequence clock), reason, reason_en}], "changed":
    [{decision_id, what: moved | cut, en, ar}] (only when one was moved or now crosses a cut)} | None."""
    from .common import frame_size_of
    from .plan import _try_ms
    em = getattr(inp, "emphasis", None) or {}
    ed = getattr(inp, "ed", None) or {}
    decs = [d for d in ed.get("decisions") or [] if isinstance(d, dict) and isinstance(d.get("camera"), dict)
            and d["camera"].get("type") in STORY_CAMERA]
    if not decs:
        return [], [], None
    errors, warnings = [], []
    v = (em.get("settings") or settings())["values"]
    ratio = (em.get("head") or head_ratio())["value"]
    W, H = frame_size_of(inp.seq_cfg)
    base = getattr(inp, "base", None) or {}
    geo = geometry_from(getattr(inp, "pre_all", None) or {}, getattr(inp, "main_file", None), base,
                        getattr(inp, "style", None) or {}, (W, H), getattr(inp, "speakers", None) or {},
                        getattr(inp, "podcast", None) or {})
    tmap = tm.get("tmap")
    seq = (lambda t: round(tmap.ms(t))) if tmap else (lambda t: int(t))
    keep = (tm.get("time_map_info") or {}).get("keep_ms")
    faces = em.get("faces") or {"status": "missing", "doc": None}
    fdoc = faces.get("doc") if faces.get("status") == "ok" else None
    samples = [] if not fdoc or fdoc.get("notes") else sorted(
        (s for s in fdoc.get("samples") or [] if isinstance(s, dict) and _num(s.get("t_ms")) is not None),
        key=lambda s: s["t_ms"])
    cap = cap_for(getattr(inp, "recipe", None), v)
    cands = {c.get("id"): c for c in (em.get("doc") or {}).get("candidates") or [] if isinstance(c, dict)}
    S = (float(fr["bsp"]) / 100) if fr.get("bsp") else (geo["S"] if geo else 1.0)
    box, boy = float(cam.get("box") or 0.0), float(cam.get("boy") or 0.0)
    stale, kept, review, changed = False, 0, [], []
    for d in decs:
        c, did = d["camera"], d.get("decision_id")
        emph = c.get("emphasis") if isinstance(c.get("emphasis"), dict) else None
        entries = [e for e in fr.get("camera") or [] if e.get("decision_id") == did]
        for e in entries if geo else []:
            win = e.get("window")
            V = (0.0, float(win["y"]), float(W), float(win["y"] + win["h"])) if win else (0.0, 0.0, float(W), float(H))
            P = S * float(e["scale_factor"])
            cx, cy = W / 2 + box + float(e["offset_x"]), H / 2 + boy + float(e["offset_y"])
            P0, cx0, cy0 = compose(geo, e["at_ms"], 1.0, 0.0, 0.0)
            bx, by = _covers(dict(geo, view=V), P0, cx0, cy0)
            hw, hh = geo["dw"] * P / 2, geo["dh"] * P / 2
            ex, ey = _covers(dict(geo, view=V), P, cx, cy)
            if by and not ey:
                lo, hi = V[3] - hh - H / 2 - boy, V[1] + hh - H / 2 - boy
                warnings.append(f"{did}: camera.offset_y {e['offset_y']:g} shows a black edge at the top or bottom of "
                                f"the frame: use offset_y between {lo:.0f} and {hi:.0f} — «{did}»: الـ offset_y بيبيّن طرف "
                                f"الصورة، خليه بين {lo:.0f} و {hi:.0f}")
            if bx and not ex:
                lo, hi = V[2] - hw - W / 2 - box, V[0] + hw - W / 2 - box
                warnings.append(f"{did}: camera.offset_x {e['offset_x']:g} shows a black edge at the side of the frame: "
                                f"keep the picture offset between {lo:.0f} and {hi:.0f} — «{did}»: الـ offset_x بيبيّن "
                                "طرف الصورة")
        if c.get("type") != "punch_in":
            continue
        at = _try_ms(c.get("at", d.get("start")))
        until = _try_ms(c["until"]) if c.get("until") else _try_ms(d.get("end"))
        if at is None or until is None:
            continue
        why = None
        if emph:
            kept += 1
            if emph.get("inputs_sha1") != em.get("sha1"):
                stale = True
            cd = cands.get(emph.get("candidate"))
            if cd and (cd.get("start_ms"), cd.get("end_ms")) != (at, until):
                warnings.append(f"{did}: moved from its candidate {emph.get('candidate')} "
                                f"({_ms_clock(cd.get('start_ms', 0))}-{_ms_clock(cd.get('end_ms', 0))}): measured again at "
                                f"{_ms_clock(at)}-{_ms_clock(until)} — «{did}» اتنقل من مكان الاقتراح، فاتقاس تاني")
                changed.append({"decision_id": did, "what": "moved", "en": "moved from its candidate: measured again",
                                "ar": "اتنقل من مكان الاقتراح: اتقاس تاني"})
            if keep and not any(ka <= at and until <= kb for ka, kb in keep):
                warnings.append(f"{did}: the punch-in crosses a cut (a removed pause or a cut word), so the jump-cut "
                                "zoom would step it past its measured scale: run `reel emphasis` again and copy the new "
                                f"candidate — «{did}» بقى فيه قطع في النص: شغّل reel emphasis تاني")
                changed.append({"decision_id": did, "what": "cut", "en": "now crosses a cut: run reel emphasis again",
                                "ar": "بقى فيه قطع في النص: شغّل reel emphasis تاني"})
        if not samples or geo is None:          # nothing to measure with: the punch needs the editor's eye
            if emph:
                why = NO_SAMPLES if faces.get("status") == "missing" and geo is not None else NOT_MEASURED
        else:
            for e in entries:
                a, b = e["at_ms"], e["until_ms"]
                use = {s["t_ms"]: s for s in samples if a <= s["t_ms"] <= b}
                for t in (a, (a + b) / 2, b):
                    near = min(samples, key=lambda s: (abs(s["t_ms"] - t), s["t_ms"]))
                    if abs(near["t_ms"] - t) <= v["near_ms"]:
                        use[near["t_ms"]] = near
                heads = []
                for t in sorted(use):
                    fs = [f for f in use[t].get("faces") or [] if isinstance(f, (list, tuple)) and len(f) >= 4]
                    heads += [head_box(f, ratio) for f in protected(geo, fs, max(a, min(b - 1, t)),
                                                                     getattr(inp, "speakers", None), v["presence"])]
                if not heads:
                    if emph:
                        why = why or NO_FACE
                    continue
                env = [min(h[0] for h in heads), min(h[1] for h in heads), max(h[2] for h in heads),
                       max(h[3] for h in heads)]
                win = e.get("window")
                V = (0.0, float(win["y"]), float(W), float(win["y"] + win["h"])) if win else (0.0, 0.0, float(W), float(H))
                P = S * float(e["scale_factor"])
                cx, cy = W / 2 + box + float(e["offset_x"]), H / 2 + boy + float(e["offset_y"])
                x0, y0, x1, y1 = _screen(geo, env, P, cx, cy)
                mx, my = v["margin"] * (V[2] - V[0]), v["margin"] * (V[3] - V[1])
                if x0 >= V[0] + mx - 1e-6 and x1 <= V[2] - mx + 1e-6 and y0 >= V[1] + my - 1e-6 and y1 <= V[3] - my + 1e-6:
                    continue
                safe = s_max(geo, env, a, cap, v["margin"])["s_max"]
                fix = (f"use scale_factor <= {safe:.4f} with the offsets `reel emphasis` gives (anchored on the face)"
                       if safe and safe >= v["s_min"] else "no punch-in keeps the head inside here: drop it or move it")
                fix_ar = (f"خلّي الزوم {safe:.4f} أو أقل" if safe and safe >= v["s_min"]
                          else "مفيش زوم هنا يسيب الراس جوه الكادر: شيله أو حرّكه")
                msg = (f"{did}: the punch-in crops the head at {_ms_clock(a)}-{_ms_clock(b)} (head box + "
                       f"{v['margin'] * 100:g} % margin): {fix} — «{did}» الزوم بيقص الراس: {fix_ar}")
                (errors if emph else warnings).append(msg)
                break
        if emph and why:
            review.append({"decision_id": did, "start_ms": seq(at), "end_ms": seq(until), "reason": why[0],
                           "reason_en": why[1]})
    if stale:
        warnings.append("the emphasis candidates were made from other inputs (words, cuts, pauses, face samples or the "
                        "ending changed since): run `reel emphasis` again — الاقتراحات قديمة، شغّل reel emphasis تاني")
    info = {"kept": kept, "review": review, **({"changed": changed} if changed else {})}
    return errors, warnings, (info if kept else None)


# --------------------------------------------------------------------------- face samples (the --faces pass)
def decode_size(dw, dh, long: int = 640) -> tuple:
    """The decode size at the source's own aspect (no padding), long side `long`, both sides even."""
    if dw >= dh:
        return long, max(2, 2 * int(round(long * dh / dw / 2)))
    return max(2, 2 * int(round(long * dw / dh / 2))), long


def _ff_decode(argv):
    """(frames, err): the decoder's raw frames as they come (a generator) and, once read, its error text."""
    import subprocess
    import tempfile
    from . import media_util
    holder = [""]
    w_h = None
    vf = argv[argv.index("-vf") + 1]
    m = re.search(r"scale=(\d+):(\d+)", vf)
    w_h = (int(m.group(1)), int(m.group(2)))

    def gen():
        n = w_h[0] * w_h[1] * 3
        with tempfile.TemporaryFile() as err:
            with media_util.ff_popen(argv, stdout=subprocess.PIPE, stderr=err) as p:
                try:
                    while True:
                        buf = p.stdout.read(n)
                        if len(buf) < n:
                            break
                        yield buf
                finally:
                    p.kill()
            err.seek(0)
            holder[0] = err.read().decode("utf-8", "replace")
    return gen(), (lambda: holder[0])


def _detector_name() -> str:
    if sys.platform == "darwin":
        try:
            import Vision  # noqa: F401
            return "macOS Vision"
        except Exception:  # noqa: BLE001
            pass
    return "OpenCV Haar"


def sample_faces(path, in_ms: int, dur_ms: int, dw: int, dh: int, fps: float = 4, faces_fn=None, decode=None,
                 lane: str = "cpu") -> dict:
    """Face boxes at `fps` over [in_ms, in_ms + dur_ms) of the footage, in ONE decode pass at the source's aspect: {fps,
    display, detector, notes, decode, samples: [{t_ms (reel clock), faces: [[cx, cy, w, h] 0..1 of the source]}]}.
    A GPU decoder that fails is retried once on the CPU, as shots.analyze_window does."""
    from PIL import Image
    from . import accel
    from .common import ffmpeg_exe
    W, H = decode_size(dw, dh)
    notes = set()
    if faces_fn is None:
        from .shots import face_boxes
        detect, detector = (lambda im: face_boxes(im, notes)), _detector_name()
    else:
        detect, detector = faces_fn, "injected"
    decode = decode or _ff_decode

    def run(ln):
        argv = [ffmpeg_exe() or "ffmpeg", "-loglevel", "error", *accel.decode_args(ln), "-ss", f"{in_ms / 1000:.3f}",
                "-t", f"{dur_ms / 1000:.3f}", "-i", str(path), "-an", "-vf", f"fps={fps:g},scale={W}:{H}", "-f",
                "rawvideo", "-pix_fmt", "rgb24", "-"]
        frames, err = decode(argv)
        out = []
        for n, buf in enumerate(frames):
            im = Image.frombuffer("RGB", (W, H), bytes(buf), "raw", "RGB", 0, 1)
            out.append({"t_ms": int((n + 0.5) * 1000 / fps),
                        "faces": [[round(float(x), 4) for x in f[:4]] for f in detect(im) or []]})
        return out, (err() if callable(err) else err)
    samples, err = run(lane)
    if lane != "cpu" and accel.is_gpu_failure(err) and len(samples) < max(1, int(dur_ms / 1000 * fps * 0.9)):
        accel.note_fallback(None, "face samples", err)
        notes.clear()
        samples, err = run("cpu")
    return {"fps": fps, "display": {"w": dw, "h": dh}, "detector": detector, "notes": sorted(notes),
            "decode": {"w": W, "h": H, "padded": False}, "samples": samples}


# --------------------------------------------------------------------------- reading a project
def _read(path):
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError:
        return b"", None
    try:
        return data, json.loads(data.decode("utf-8-sig"))
    except ValueError:
        return data, None


def _words_doc(paths) -> dict:
    from .errors import Guidance
    f = paths.p("02_transcription/words.json")
    data, wj = _read(f)
    if data is None or not isinstance(wj, dict) or not isinstance(wj.get("words"), list):
        raise Guidance("مفيش تفريغ صالح للفيديو ده، فمش هقدر أقترح punch / no usable transcript for this item "
                       "(02_transcription/words.json is missing or damaged)",
                       "Run `reel transcribe` (or fix the file), then `reel emphasis` again", where=str(f))
    return wj


def _main_file(paths, ed: dict, rng: dict):
    g = (ed or {}).get("global") if isinstance((ed or {}).get("global"), dict) else {}
    mf = g.get("main_footage") or (rng or {}).get("footage")
    if not mf:
        from .plan import _default_footage
        mf = _default_footage(paths)[0]
    return str(mf).replace("\\", "/") if mf else None


def load_samples(paths, main_file, rng: dict, fr: dict | None) -> dict:
    """{"status": ok | missing | damaged | stale, "doc"}: stale when the samples were taken from another footage, another
    in-point or another display size than this video's."""
    from .plan import same_footage_name
    data, doc = _read(paths.p(FACES_FILE))
    if data is None:
        return {"status": "missing", "doc": None}
    if not isinstance(doc, dict) or not isinstance(doc.get("samples"), list):
        return {"status": "damaged", "doc": None}
    disp = doc.get("display") or {}
    same = (main_file and doc.get("footage") and same_footage_name(doc["footage"], main_file)
            and int(((doc.get("range") or {}).get("in_ms")) or 0) == int((rng or {}).get("in_ms") or 0)
            and (fr is None or (disp.get("w"), disp.get("h")) == (fr["dw"], fr["dh"])))
    return {"status": "ok" if same else "stale", "doc": doc}


def _terms(ctx, profile: dict) -> list:
    from .safety.lexicon import _folded, client_terms
    extra = [profile.get("display_name")] + [p.get("name") for p in profile.get("people") or [] if isinstance(p, dict)]
    return client_terms(ctx) + _folded([x for x in extra if isinstance(x, str) and x.strip()])


def _statements(paths):
    _, doc = _read(paths.p("01_analysis/transcript-semantic-analysis.json"))
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and isinstance(doc.get("statements"), list):
        return doc["statements"]
    return None


def inputs_sha1(paths, ctx=None) -> str:
    """The hash of everything a candidate depends on except the story-editor's own decisions (so copying a candidate
    into edit-decisions.json does not make it stale): the transcript words, pauses, cut proposals, face samples,
    preflight, speakers, statements, the reel's range; this video's cuts, pause removal, sign-off, endings, footage and
    framing; the profile's endings and style framing/ease; the settings and head ratio."""
    from .common import load_config
    files = ["02_transcription/words.json", "06_audio/dialogue/pauses.json", "01_analysis/cut-proposals.json", FACES_FILE,
             "00_inputs/preflight.json", "00_inputs/speakers.json", "01_analysis/transcript-semantic-analysis.json",
             "00_inputs/source.json"]
    hashes = []
    for f in files:
        data, _ = _read(paths.p(f))
        hashes.append(hashlib.sha1(data).hexdigest() if data is not None else None)
    _, ed = _read(paths.p("01_analysis/edit-decisions.json"))
    ed = ed if isinstance(ed, dict) else {}
    g = ed.get("global") if isinstance(ed.get("global"), dict) else {}
    gk = {k: g.get(k) for k in ("cut_words", "remove_pauses", "sign_off_at", "endings", "main_footage", "framing",
                                "framing_window_y", "base_scale_percent", "base_offset_x", "base_offset_y")}
    style = load_config("style.json", ctx)
    style = style if isinstance(style, dict) else {}
    key = json.dumps([hashes, gk, ed.get("manual_verse"), ed.get("manual_verse_off"),
                      (load_config("profile.json", ctx) or {}).get("endings"),
                      {k: style.get(k) for k in ("framing", "camera")}, settings(ctx), head_ratio(ctx), SCHEMA],
                     ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def gather(paths, ctx=None, audio: bool = True) -> dict:
    """Every read build() needs, done once."""
    from . import endings, manual_verse as mv
    from .camera_ease import ease_settings
    from .common import current_context, frame_size, load_config, seq_fps, source_range
    from .plan import _try_ms
    from .recipes import for_paths
    ctx = ctx or current_context()
    wj = _words_doc(paths)
    _, ed = _read(paths.p("01_analysis/edit-decisions.json"))
    ed = ed if isinstance(ed, dict) else {}
    g = ed.get("global") if isinstance(ed.get("global"), dict) else {}
    rng = source_range(paths)
    _, pre = _read(paths.p("00_inputs/preflight.json"))
    pre = pre if isinstance(pre, dict) else {}
    main_file = _main_file(paths, ed, rng)
    style = load_config("style.json", ctx)
    style = style if isinstance(style, dict) else {}
    profile = load_config("profile.json", ctx) or {}
    _, speakers = _read(paths.p("00_inputs/speakers.json"))
    speakers = speakers if isinstance(speakers, dict) else {}
    fr = geometry_from(pre, main_file, g, style, frame_size(paths), speakers, load_config("podcast.json", ctx))
    words = wj["words"]
    meta = wj.get("meta") if isinstance(wj.get("meta"), dict) else {}
    _, pz = _read(paths.p("06_audio/dialogue/pauses.json"))
    pz = pz if isinstance(pz, dict) else None
    _, cp = _read(paths.p("01_analysis/cut-proposals.json"))
    props = cp.get("proposals") if isinstance(cp, dict) and isinstance(cp.get("proposals"), list) else None
    good, _ = clean_words(words)
    spans, _e, _w = mv.resolve(mv.detect([w for w in good if isinstance(w["id"], int)], mv.config(profile)), ed)
    levels, source = None, None
    if audio and good:
        got = read_wav(paths.p("06_audio/dialogue/dialogue_clean.wav"))
        source = "06_audio/dialogue/dialogue_clean.wav" if got else None
        if got is None and main_file:
            mf = Path(main_file)
            got = read_footage_audio(mf if mf.is_absolute() else paths.root / mf, rng)
            source = "footage" if got else None
        if got is not None:
            levels = word_levels(good, *got)
    return {"video_id": paths.video_id, "words": words, "lang": str(meta.get("language") or "ar"),
            "media_end_ms": _num(meta.get("duration_ms")) or (good[-1]["end_ms"] if good else 0),
            "levels": levels, "audio_source": source,
            "remove_pauses": bool(g.get("remove_pauses")) if ed else pz is not None, "pauses": pz, "ed": ed,
            "proposals": props, "endings": endings.config(profile.get("endings"), g.get("endings")),
            "marker_ms": _try_ms(g.get("sign_off_at")) if g.get("sign_off_at") not in (None, "") else None,
            "recipe": for_paths(paths), "terms": _terms(ctx, profile), "statements": _statements(paths),
            "speakers": speakers, "frame": fr, "faces": load_samples(paths, main_file, rng, fr),
            "verse": [(s["src_start_ms"], s["src_end_ms"]) for s in spans], "ease_ms": ease_settings(style)[0],
            "fps": seq_fps(ctx), "settings": settings(ctx), "head": head_ratio(ctx),
            "templates": (load_config("graphics-templates.json", ctx) or {}).get("templates", {}),
            "inputs_sha1": inputs_sha1(paths, ctx), "main_file": main_file, "range": rng}


def run(paths, ctx=None, faces: bool = False, faces_fn=None, decode=None, audio: bool = True) -> dict:
    """`reel emphasis [--faces]`: (with --faces, first the face samples), then 01_analysis/emphasis.json. A missing
    or damaged words.json is refused with nothing written. Never touches edit-decisions.json or an approval."""
    from .common import current_context, frame_size, load_config, source_range, write_json
    from .errors import Guidance
    ctx = ctx or current_context()
    wj = _words_doc(paths)
    if faces:
        _, ed = _read(paths.p("01_analysis/edit-decisions.json"))
        ed = ed if isinstance(ed, dict) else {}
        rng = source_range(paths)
        main_file = _main_file(paths, ed, rng)
        _, pre = _read(paths.p("00_inputs/preflight.json"))
        g = ed.get("global") if isinstance(ed.get("global"), dict) else {}
        fr = geometry_from(pre if isinstance(pre, dict) else {}, main_file, g, {}, frame_size(paths), {},
                           load_config("podcast.json", ctx))
        if not main_file or fr is None:
            raise Guidance("مفيش preflight للفيديو ده، فمش هقدر أقيس الوش / no preflight for this video's footage",
                           "Run `reel preflight` first, then `reel emphasis --faces`",
                           where=str(paths.p("00_inputs/preflight.json")))
        f = Path(main_file)
        f = f if f.is_absolute() else Path(paths.root) / f
        if not f.exists():
            raise Guidance(f"the footage {main_file} is not in the client folder", "Check global.main_footage",
                           where=str(f))
        in_ms = int((rng or {}).get("in_ms") or 0)
        dur = int(((rng or {}).get("out_ms") or 0) - in_ms) if (rng or {}).get("out_ms") else \
            int(_num((wj.get("meta") or {}).get("duration_ms")) or 0)
        from .gpu_lock import site_slot
        with site_slot("shots", log_to=paths) as lane:
            sd = sample_faces(f, in_ms, dur, fr["dw"], fr["dh"], DEFAULTS["sample_fps"], faces_fn, decode, lane)
        sd = dict({"schema": 1, "video_id": paths.video_id, "footage": main_file,
                   "range": {"in_ms": in_ms, "out_ms": in_ms + dur}}, **sd)
        write_json(paths.p(FACES_FILE), sd)
    doc = build(gather(paths, ctx, audio))
    write_json(paths.p(FILE), doc)
    return doc
