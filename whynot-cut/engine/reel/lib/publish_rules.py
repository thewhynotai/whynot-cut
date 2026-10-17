# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 Task 30 (R-4.8): the stricter rules of `reel publish-check`, on top of the platform limits and the
facts checks in lib/publish.py. Every finding says what is wrong and the fix, Arabic first.

  1. no spoken-sentence repeat: a caption that shares a run of `ngram` words with the transcript, or a caption sentence
     whose word overlap with one transcript sentence is >= `sentence_overlap` (shared words / the longer sentence's
     words, both at least `sentence_min_tokens` words) -> error, the caption's own words quoted. A marked quote («…» or
     “…”; a verse ﴿…﴾) is the allowed way to repeat the speaker (publish.check already proves a quote IS in the
     transcript); links are breaks; hashtags and emoji are not words. Checked: each reel's Instagram and TikTok captions, the Shorts title
     and description, the YouTube description hook and summary.
  2. no cross-platform duplicate: two captions of one reel (Instagram, TikTok, Shorts description; hashtags left out)
     with word Jaccard >= `jaccard` -> error. A Shorts title is a title, not a caption.
  3. no filler hashtags: a tag on the `filler_hashtags` list (generic reach tags, AR and EN; a client edits it in its
     reel-profile, `extra_filler_hashtags` adds to it, `allowed_hashtags` lifts one) -> error, the tag named as written.
  4. the search phrase (`search_phrase` on the reel, or on one platform) must be fully visible in the first line, within
     `first_line[<platform>]` characters -> a warning with the position.
Words are compared after cut_proposals_norm (the Arabic rules of R-4.3: harakat, tatweel, alef/yaa/taa-marbuta
variants, case, punctuation). Thresholds live in config/defaults/publish-rules.json (merged with the client's
reel-profile); a damaged or out-of-range value falls back to the engine default here. `enabled: false` turns every
rule off (publish-check as before Task 30).
"""
from __future__ import annotations

import copy
import re

from . import cut_proposals_norm as N
from .publish import HASHTAG, QUOTE, URL

DEFAULTS: dict = {
    "enabled": True,
    "spoken_repeat": {"ngram": 6, "sentence_overlap": 0.7, "sentence_min_tokens": 4},
    "cross_platform": {"jaccard": 0.8},
    "filler_hashtags": [
        "#fyp", "#foryou", "#foryoupage", "#foryourpage", "#fy", "#xyzbca", "#viral", "#viralvideo", "#viralreels",
        "#goviral", "#blowthisup", "#trending", "#trend", "#explore", "#explorepage", "#reels", "#reelsinstagram",
        "#reelitfeelit", "#instagood", "#instadaily", "#instagram", "#photooftheday", "#tiktok", "#tiktokviral",
        "#shorts", "#youtubeshorts", "#shortsvideo", "#like", "#likes", "#likeforlike", "#likeforlikes", "#l4l",
        "#follow", "#followme", "#followforfollow", "#followback", "#f4f", "#subscribe",
        "#اكسبلور", "#اكسبلورر", "#الاكسبلور", "#اكسبلور_فولو", "#ترند", "#تريند", "#ترندات", "#ترند_تيك_توك",
        "#فولو", "#لايك", "#لايكات", "#لايك_فولو", "#متابعة", "#تابعني", "#فيرال", "#فايرال", "#ريلز", "#رييلز",
        "#انستقرام", "#انستجرام", "#تيك_توك", "#فوريو", "#فوريو_بيج", "#شورتس"],
    "extra_filler_hashtags": [],
    "allowed_hashtags": [],
    "first_line": {"instagram": 125, "tiktok": 100, "shorts": 40},
}
PLATFORMS = (("instagram", "caption"), ("tiktok", "caption"), ("shorts", "title"))   # rule 4: where the phrase goes
SENT = re.compile(r"[!?؟…\n\r]+|\.(?=\s|$)|\.{2,}")
EDGE = " \t\r\n.,;:!?،؛؟…-–—\"'()[]{}"
VERSE = re.compile(r"﴿[^﴾]*﴾")                       # a Quran verse is quoted in ﴿…﴾ (never reworded)
TAG_DROP = re.compile(r"[^0-9a-zء-ي٠-٩]")   # after normalising: decorations (シ, emoji) out
TAG_STRETCH = re.compile(r"(.)\1{2,}")              # «اكسبلوووور», #fypppp: 3+ of one letter count as one


# --------------------------------------------------------------------------- config
def _num(v, lo, hi, default, integer=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not (lo <= v <= hi):
        return default
    return int(v) if integer else float(v)


def _tags(v, default):
    return [t for t in v if isinstance(t, str) and t.strip()] if isinstance(v, list) else list(default)


def config(ctx=None) -> dict:
    """The engine defaults <- config/defaults/publish-rules.json <- the client's reel-profile; every value checked."""
    from .common import load_config
    try:
        over = load_config("publish-rules.json", ctx) or {}
    except Exception:                                    # a damaged file never stops publish-check: defaults
        over = {}
    over = over if isinstance(over, dict) else {}
    d = copy.deepcopy(DEFAULTS)
    sr, cp, fl = (over.get(k) if isinstance(over.get(k), dict) else {} for k in ("spoken_repeat", "cross_platform",
                                                                                   "first_line"))
    s0 = d["spoken_repeat"]
    d["enabled"] = over["enabled"] if isinstance(over.get("enabled"), bool) else True
    d["spoken_repeat"] = {"ngram": _num(sr.get("ngram"), 2, 50, s0["ngram"], True),
                          "sentence_overlap": _num(sr.get("sentence_overlap"), 0.01, 1, s0["sentence_overlap"]),
                          "sentence_min_tokens": _num(sr.get("sentence_min_tokens"), 1, 50, s0["sentence_min_tokens"],
                                                      True)}
    d["cross_platform"] = {"jaccard": _num(cp.get("jaccard"), 0.01, 1, d["cross_platform"]["jaccard"])}
    d["filler_hashtags"] = _tags(over.get("filler_hashtags"), d["filler_hashtags"])
    d["extra_filler_hashtags"] = _tags(over.get("extra_filler_hashtags"), d["extra_filler_hashtags"])
    d["allowed_hashtags"] = _tags(over.get("allowed_hashtags"), d["allowed_hashtags"])
    for p in set(d["first_line"]) | {k for k in fl if isinstance(k, str)}:
        v = _num(fl.get(p), 1, 10000, d["first_line"].get(p), True) if p in fl else d["first_line"].get(p)
        if v is None:
            d["first_line"].pop(p, None)
        else:
            d["first_line"][p] = v
    return d


def _filled(cfg: dict) -> dict:
    """A caller's partial cfg with the missing or wrong-typed parts taken from DEFAULTS: the threshold blocks are merged
    key by key; a given `first_line` map is the whole map (a platform left out has no limit)."""
    d = copy.deepcopy(DEFAULTS)
    for k, v in (cfg if isinstance(cfg, dict) else {}).items():
        if isinstance(d.get(k), dict):
            if isinstance(v, dict):
                d[k] = v if k == "first_line" else {**d[k], **v}
        elif k not in d or v is not None:
            d[k] = v
    return d


# --------------------------------------------------------------------------- words
def _tokens(text: str, a: int = 0, b: int | None = None) -> list[tuple[str, int, int]]:
    """(normalised word, raw start, raw end) for text[a:b]; offsets are in `text`."""
    out = []
    for m in re.finditer(r"\S+", text[a:b]):
        for t in N.normalize(m.group()):
            out.append((t, a + m.start(), a + m.end()))
    return out


def _span(text: str, s: int, e: int, cap: int = 120) -> str:
    t = text[s:e].strip(EDGE)
    return t if len(t) <= cap else t[:cap].rstrip() + "…"


def hashtag_key(tag: str) -> str:
    """'#For_You 🔥' -> 'foryou', '#إكسبلور' / '#اكسبلوووور' -> 'اكسبلور', '#fypシ' -> 'fyp' (case, marks, letter
    variants, '_', emoji and other decorations, stretched letters ignored)."""
    return TAG_STRETCH.sub(r"\1", TAG_DROP.sub("", "".join(N.normalize(str(tag or "").lstrip("#")))))


def _blank(text: str, rx) -> str:
    return rx.sub(lambda m: " " * len(m.group()), text)


def _runs(text: str) -> list[tuple[int, int]]:
    """The stretches of `text` between marked quotes, verses and links (each one a break)."""
    cuts = sorted([m.span() for rx in (QUOTE, VERSE, URL) for m in rx.finditer(text)])
    runs, pos = [], 0
    for s, e in cuts:
        if s > pos:
            runs.append((pos, s))
        pos = max(pos, e)
    if pos < len(text):
        runs.append((pos, len(text)))
    return runs


def _first_line_match(text: str, phrase: str):
    want = N.normalize(phrase)
    lines = [ln for ln in re.split(r"\r?\n", text) if ln.strip()]
    if not want or not lines:
        return None
    toks = _tokens(lines[0])
    words = [t for t, _s, _e in toks]
    for i in range(len(words) - len(want) + 1):
        if words[i:i + len(want)] == want:
            return toks[i][1], toks[i + len(want) - 1][2]
    return None


def first_line_position(text: str, phrase: str):
    """Where the phrase starts in the first non-empty line (characters before it), else None."""
    m = _first_line_match(str(text or ""), str(phrase or ""))
    return m[0] if m else None


# --------------------------------------------------------------------------- the transcript
class _Spoken:
    def __init__(self, segments, n: int, min_tokens: int):
        texts = [s.get("text") for s in segments or [] if isinstance(s, dict) and isinstance(s.get("text"), str)]
        joined = " ".join(texts)
        words = N.normalize(joined)
        self.n = n
        self.grams = {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}
        # the sentences: by punctuation across the whole stream (a sentence the ASR split in two), and each segment's
        # own sentences (ASR text without full stops: a segment is a sentence, never one episode-long "sentence")
        parts = SENT.split(joined) + [x for t in texts for x in SENT.split(t)]
        sets = (frozenset(N.normalize(x)) for x in parts)
        self.sents = list(dict.fromkeys(st for st in sets if len(st) >= min_tokens))
        self.index: dict[str, list[int]] = {}
        for k, st in enumerate(self.sents):
            for w in st:
                self.index.setdefault(w, []).append(k)

    def best_overlap(self, words: set) -> float:
        cand = {k for w in words for k in self.index.get(w, ())}
        return max((len(words & self.sents[k]) / max(len(words), len(self.sents[k])) for k in cand), default=0.0)


def _repeats(text: str, sp: _Spoken, cfg: dict) -> list[str]:
    """The spans of `text` that re-say the transcript (raw words, in order)."""
    n, thr, mn = (cfg["spoken_repeat"][k] for k in ("ngram", "sentence_overlap", "sentence_min_tokens"))
    plain = _blank(text, HASHTAG)
    found: list[tuple[int, int]] = []
    for a, b in _runs(plain):
        toks = _tokens(plain, a, b)
        hit = [False] * len(toks)
        for i in range(len(toks) - n + 1):
            if tuple(t for t, _s, _e in toks[i:i + n]) in sp.grams:
                for j in range(i, i + n):
                    hit[j] = True
        i = 0
        while i < len(toks):
            if hit[i]:
                j = i
                while j + 1 < len(toks) and hit[j + 1]:
                    j += 1
                found.append((toks[i][1], toks[j][2]))
                i = j + 1
            else:
                i += 1
        pos = a
        for m in list(SENT.finditer(plain, a, b)) + [None]:
            e = m.start() if m else b
            st = _tokens(plain, pos, e)
            ws = {t for t, _s, _e in st}
            if len(ws) >= mn and not any(s < st[-1][2] and e2 > st[0][1] for s, e2 in found) \
                    and sp.best_overlap(ws) >= thr:
                found.append((st[0][1], st[-1][2]))
            pos = m.end() if m else b
    return [_span(text, s, e) for s, e in sorted(found)]


# --------------------------------------------------------------------------- the check
def _d(v) -> dict:
    return v if isinstance(v, dict) else {}


def _s(v) -> str:
    return v if isinstance(v, str) else ""


def _l(v) -> list:
    """A hashtag list; one string ("#a #b") is read as the tags written in it."""
    return HASHTAG.findall(v) if isinstance(v, str) else [x for x in v if isinstance(x, str)] if isinstance(v, list)         else []


def _r1(where: str, span: str) -> str:
    return (f"{where}: «{span}» — دي جملة اتقالت في الكلام. قول الفكرة بكلام جديد بدل ما تكرر الجملة اللي اتقالت؛ "
            "ولو لازم تنقل كلامه بالنص (زي معلومة طبية) حطه بين «» كاقتباس، والآية بين ﴿﴾. "
            "(this repeats a spoken sentence: say the idea in new words, or put the speaker's exact words in «» as a "
            "quote, a verse in ﴿﴾)")


def check(pub: dict, reels: list, segments: list, cfg: dict | None = None) -> dict:
    """pub = publish/publish.json, reels = [(reel_id, publish/reels/<REEL>.json)], segments = the transcript's
    segments -> {"errors": [...], "warnings": [...]} in a stable order. Reads nothing, writes nothing."""
    cfg = config() if cfg is None else _filled(cfg)
    errors: list[str] = []
    warnings: list[str] = []
    if not cfg.get("enabled", True):
        return {"errors": errors, "warnings": warnings}
    sp = _Spoken(segments, cfg["spoken_repeat"]["ngram"], cfg["spoken_repeat"]["sentence_min_tokens"])
    allowed = {hashtag_key(t) for t in cfg.get("allowed_hashtags") or []}
    filler = {hashtag_key(t) for t in (cfg.get("filler_hashtags") or []) + (cfg.get("extra_filler_hashtags") or [])}
    filler -= allowed | {""}
    jac = cfg["cross_platform"]["jaccard"]
    limits = cfg.get("first_line") or {}

    def repeat(where: str, text: str):
        if text.strip():
            errors.extend(_r1(where, s) for s in _repeats(text, sp, cfg))

    def tags(where: str, texts: list[str], listed: list[str]):
        seen = set()
        for t in [h for x in texts for h in HASHTAG.findall(x)] + listed:
            k, t = hashtag_key(t), t.rstrip(EDGE)
            if k in filler and k not in seen:
                seen.add(k)
                errors.append(f"{where}: الهاشتاج {t} عام ومالوش علاقة بالموضوع (بيتحط عشان الوصول بس) — شيله وحط "
                              f"هاشتاج عن موضوع الريل نفسه. (generic reach hashtag {t}: replace it with one about the "
                              "reel's topic)")

    d = _d(_d(_d(pub).get("youtube")).get("description"))
    for k in ("hook", "summary"):
        repeat(f"description {k}", _s(d.get(k)))
    tags("description", [_s(d.get(k)) for k in ("hook", "summary", "guest", "sponsor", "cta")], _l(d.get("hashtags")))

    for rid, r in reels:
        r = _d(r)
        ig, tt, sh = _d(r.get("instagram")), _d(r.get("tiktok")), _d(r.get("shorts"))
        caps = {"instagram": _s(ig.get("caption")), "tiktok": _s(tt.get("caption")),
                "shorts": _s(sh.get("description"))}
        repeat(f"{rid} instagram", caps["instagram"])
        repeat(f"{rid} tiktok", caps["tiktok"])
        repeat(f"{rid} shorts title", _s(sh.get("title")))
        repeat(f"{rid} shorts description", caps["shorts"])
        sets = {p: set(N.normalize(_blank(t, HASHTAG))) for p, t in caps.items()}
        names = list(caps)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                A, B = sets[a], sets[b]
                if A and B and len(A & B) / len(A | B) >= jac:
                    pct = round(100 * len(A & B) / len(A | B))
                    errors.append(f"{rid}: كل منصة محتاجة نص مختلف — نص {a} ونص {b} متشابهين {pct}%؛ اكتب لكل منصة "
                                  f"نص بصياغة مختلفة. (the {a} and {b} captions are {pct}% the same: write a different "
                                  "caption for each platform)")
        tags(f"{rid} instagram", [caps["instagram"]], _l(ig.get("hashtags")))
        tags(f"{rid} tiktok", [caps["tiktok"]], _l(tt.get("hashtags")))
        tags(f"{rid} shorts", [_s(sh.get("title")), caps["shorts"]], [])
        for plat, field in PLATFORMS:
            obj = {"instagram": ig, "tiktok": tt, "shorts": sh}[plat]
            phrase = _s(obj.get("search_phrase")).strip() or _s(r.get("search_phrase")).strip()
            limit = limits.get(plat)
            if not phrase or not N.normalize(phrase) or not isinstance(limit, int):
                continue
            text = _s(obj.get(field))
            if not text.strip():                         # an empty caption is the limits check's job
                continue
            m = _first_line_match(text, phrase)
            where = "الكابشن" if field == "caption" else "العنوان"
            if m is None:
                warnings.append(f"{rid} {plat}: عبارة البحث «{phrase}» مش موجودة في أول سطر من {where} — حطها في أول "
                                f"السطر عشان تبان من غير «المزيد». (the search phrase is not in the first line of the "
                                f"{field}; put it there)")
            elif m[1] > limit:
                warnings.append(f"{rid} {plat}: عبارة البحث «{phrase}» بتبدأ بعد {m[0]} حرف وبتخلص عند الحرف {m[1]}، "
                                f"وأول سطر بيبان منه {limit} حرف بس — قدّمها لأول السطر عشان تبان كلها. (the search "
                                f"phrase runs from character {m[0]} to {m[1]}; only the first {limit} show before "
                                "«more»: move it to the start)")
    return {"errors": errors, "warnings": warnings}
