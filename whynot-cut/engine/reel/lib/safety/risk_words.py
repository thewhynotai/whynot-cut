# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""K-T1 (Phase 4 Task 61): the words to confirm, risk first.

Today's list of words to confirm (the words the transcription is unsure of) is re-ordered by risk × doubt so the editor
hears the dangerous ones first:
- risk (high): doses (a number with a unit, «٣ ونص مجم», «حبايتين»), numbers (any digits, spelled), drug and product
  names (the shipped lexicon groups, the client's glossary, a near-miss of a long listed name, a generic-name ending, a
  Latin word in an Arabic medical clip), a negation next to a claim («مش بيعالج», «ما تاخدهاش», «اوعى», "don't
  take", «لا تزيد عن ٤»), durations, frequencies and timing («مرتين في اليوم», «قبل النوم»); medium: any other word of
  a medical claim; low: the rest, fillers last;
- doubt: a word probability below the measured threshold (safety.json `risk_words`, with its basis), the transcript
  editor's flag, a stretch the decoder had to decode again, or a correction that changed the word.

A confirmation is today's: the editor proofreads subtitle-review.md and records `reel transcript-verify` (by ear; a
"claude", "auto" or "delegated" verification does not count, and a reel's "episode verification" counts only when the
episode's own verification was by ear). There is no new command.

Behind the K-T1 switch (switches.PLAN_BLOCK, off until the Gate 4 tag): `plan_errors` refuses a graphic that shows a
high-risk word that is still unconfirmed (medical-accuracy rule 4), the block at the top of subtitle-review.md and the
NEEDS-YOU order. While the switch is off every function a call site uses returns today's result unchanged.
Nothing here writes a file, and nothing here raises for a damaged input (G10)."""
import hashlib
import json
import math
import re
from pathlib import Path

from . import switches
from .lexicon import client_terms, inn_like, load_sources, near
from .numbers import (LINK, canon, fold, frequency_value, is_frequency, is_time, quantities, stems, timing_phrases,
                      tokens, values_in)

DEFAULT_THRESHOLD = 0.9
DEFAULT_BASIS = ("measured 2026-10-17 on 8 corrected transcripts (whynot-test copies; 661 words, 51 corrected by the "
                 "editor): below 0.5 none of the corrected words is caught, below 0.9 35 of 51 (69 %) are, with 31 % of "
                 "the right words listed too; the list is ranked, so the risky ones still come first")
WEIGHT = {"dose": 1.0, "drug": 0.9, "negation": 0.9, "duration": 0.85, "number": 0.8, "claim": 0.4, "other": 0.2,
          "filler": 0.05}
HIGH = ("dose", "drug", "negation", "duration", "number")
TIER = {**{k: 0 for k in HIGH}, "claim": 1, "other": 2, "filler": 2}
LABEL = {"dose": ("جرعة", "dose"), "drug": ("اسم دوا أو منتج", "drug or product name"),
         "negation": ("نفي جنب كلام طبي", "negation next to a claim"),
         "duration": ("مدة أو عدد مرات أو توقيت", "duration, frequency or timing"), "number": ("رقم", "number"),
         "claim": ("كلمة في كلام طبي", "word in a medical claim"), "other": ("كلمة", "word"),
         "filler": ("كلمة حشو", "filler")}
BY_EAR = {"editor"}      # the only `transcript-verify --by` that is the editor's own ear (allow-list, as NEEDS-YOU)
EPISODE_BY = "episode verification"
NEAR = 4                 # a negation this many words from a claim is part of it
CLAIM_SPAN = 6           # words this close to a claim word or a risky item belong to the claim

NEGATIONS = {"مش", "مو", "لا", "ما", "مفيش", "مافيش", "ممنوع", "بلاش", "لم", "لن", "ليس", "ليست", "بدون", "ولا",
             "اوعي", "اوعا", "اوع", "اياك", "اياكي", "اياكم",
             "no", "not", "never", "dont", "don't", "doesnt", "doesn't", "didnt", "didn't", "cant", "can't", "cannot",
             "shouldnt", "shouldn't", "wont", "won't", "without", "avoid", "nor", "isnt", "isn't", "arent", "aren't",
             "mustnt", "mustn't", "stop"}
_CIRCUMFIX = re.compile(r"^(ما|م[تيناب])(\w{2,}?)(ه|ها|هم|ك|كي|كو|ني|ي)?ش$")   # «ماتاخدش», «ما تاخدهاش», «مينفعش»
CLAIM_CUES = {"علاج", "يعالج", "بيعالج", "عالج", "دوا", "دواء", "ادويه", "خد", "خدي", "خدوا", "تاخد", "ياخد",
              "اخد", "استخدم", "تستخدم", "يستخدم", "ينفع", "بينفع", "مفيد", "مضر", "ضار", "خطر", "خطير", "امن", "يسبب",
              "بيسبب", "يقلل", "بيقلل", "يزود", "بيزود", "يرفع", "بيرفع", "ينزل", "بينزل", "يشفي", "بيشفي", "شفا",
              "جرعه", "حقنه", "عمليه", "تحليل", "اشعه", "ضغط", "سكر", "كوليسترول", "مرض", "اعراض", "تاثير", "اثار",
              "تزيد", "يزيد", "تزود", "تقلل", "توقف", "يوقف", "تبطل", "حامل", "رضاعه", "مريض", "مرضي",
              "take", "takes", "use", "uses", "cure", "cures", "treat", "treats", "treatment", "safe", "harmful",
              "cause", "causes", "help", "helps", "prevent", "prevents", "works", "dose", "dosage", "drug", "medicine",
              "pill", "surgery", "test", "risk", "side", "effect", "effects", "symptoms", "disease", "exceed", "more",
              "less", "pregnant", "stop", "skip"}
_CUE_CORES = sorted((c for c in CLAIM_CUES if len(c) >= 4 and re.search("[؀-ۿ]", c)), key=len, reverse=True)
FILLERS = {"يعني", "اه", "ايوه", "ام", "امم", "اممم", "اا", "ااه", "طب", "بقي", "كده", "خلاص", "يا", "بص", "اصل",
           "um", "uh", "uhm", "er", "erm", "like", "so", "well", "ok", "okay", "yeah", "mm", "hmm"}
COMMON_LATIN = {"the", "and", "or", "of", "to", "in", "on", "is", "it", "a", "an", "ok", "okay", "yes", "no", "so",
                "video", "videos", "channel", "like", "really", "very", "good", "nice", "please", "thanks", "thank",
                "you", "hello", "hi", "bye", "follow", "share", "comment", "subscribe", "online", "doctor", "dr",
                "instagram", "insta", "facebook", "tiktok", "youtube", "whatsapp", "snapchat", "twitter", "google",
                "live", "story", "reel", "reels", "post", "link", "page", "clinic", "center", "centre", "keto", "diet",
                "fitness", "gym", "cardio", "workout", "sport", "body", "skin", "hair", "care", "beauty", "detox",
                "fasting", "check", "up", "checkup", "test", "scan", "level", "high", "low", "normal", "plan", "team",
                "mama", "baby", "kids", "family", "home", "free", "offer", "sale", "new", "best", "top", "tips"}
# everyday words one letter away from a listed medicine («بروتين» / «بروفين», "aspiring" / "aspirin")
NEAR_MISS_STOP = {"بروتين", "بروفيل", "بروفايل", "protein", "proteins", "profile", "aspiring", "morphing", "retinal",
                  "retinas", "insulting", "colleges", "vitamins"}
_LATIN = re.compile(r"[a-z]")
_ARABIC = re.compile("[؀-ۿ]")


def threshold(ctx=None) -> tuple:
    """(value, basis) from safety.json `risk_words` (client reel-profile over config/defaults). A value without its
    basis, a bool, a string or a number outside (0, 1] is not accepted: the measured default and its basis are used."""
    v, basis = None, None
    # layer by layer (config/defaults, shipped profile, client reel-profile): the file that sets the value must give
    # its basis too, so a client's own number never borrows the shipped basis
    for f in switches.layers("safety.json", ctx):
        s = f.get("risk_words") if isinstance(f.get("risk_words"), dict) else {}
        if "low_probability_threshold" in s:
            v, basis = s.get("low_probability_threshold"), s.get("low_probability_threshold_basis")
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 1 and isinstance(basis, str) \
            and basis.strip():
        return float(v), basis.strip()
    return DEFAULT_THRESHOLD, DEFAULT_BASIS


# --- doubt -------------------------------------------------------------------------------------------------------------
def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def _spans(meta: dict) -> list:
    """The decoder's decoded-again stretches, on this transcript's clock: a reel cut from an episode keeps the
    episode's stretches, so they move back by the reel's offset."""
    recs = meta.get("redecoded_segments")
    off = _num(meta.get("offset_ms")) or 0
    out = []
    for r in recs if isinstance(recs, list) else []:
        if isinstance(r, dict) and _num(r.get("start_ms")) is not None and _num(r.get("end_ms")) is not None:
            out.append((r["start_ms"] - off, r["end_ms"] - off))
    return out


def _doubt(w: dict, thr: float, redecoded: list) -> tuple:
    """(doubt 0..1, [(arabic, english) reasons]). 0 = the transcription is sure and nobody changed the word."""
    d, why = 0.0, []
    if w.get("flagged"):
        d = 1.0
        why.append(("علّم عليها مراجع التفريغ", "flagged by the transcript editor"))
    p = _num(w.get("probability"))
    if p is None:
        d = max(d, 0.3)
        why.append(("التفريغ مسجّلش ثقته فيها", "no confidence recorded"))
    elif p < thr:
        d = max(d, max(0.01, 1 - p))
        why.append((f"ثقة التفريغ {p:.2f} (أقل من {thr:g})", f"probability {p:.2f} (< {thr:g})"))
    s = _num(w.get("start_ms"))
    if s is not None and any(a <= s <= b for a, b in redecoded):
        d = max(d, 0.5)
        why.append(("الجزء ده اتفرّغ مرتين ومكانش ثابت", "decoded twice here (the decoder disagreed)"))
    mw = w.get("machine_word")
    if (isinstance(mw, str) and mw != w.get("word")) or w.get("corrected"):
        d = max(d, 0.5)
        heard = f" «{mw}»" if isinstance(mw, str) else ""
        why.append((f"اتصححت (التفريغ سمع{heard})", f"a correction changed it (heard{heard or ' something else'})"))
    return d, why


# --- ranking -----------------------------------------------------------------------------------------------------------
def _tokens(ws: list) -> list:
    out = []
    for w in ws:
        raw = str(w.get("word") or "").strip()
        t = fold(raw)
        if not t and raw in (".", "٫"):
            t = "."
        elif not t and raw in (",", "٬"):
            t = ","
        out.append(t)
    return out


def _cue_core(tok: str) -> bool:
    """A claim word, also conjugated or with a pronoun or the negation's «ش» around it («تاخده», «تاخدهاش»,
    «مينفعش»): a listed cue, or a listed Arabic cue of 4+ letters inside the word."""
    if any(s in CLAIM_CUES for s in stems(tok)):
        return True
    return bool(_ARABIC.search(tok)) and any(c in tok for c in _CUE_CORES)


def _negation(tok: str) -> str | None:
    """"word" for a negation word, "verb" for a negated verb («ماتاخدش»), None otherwise."""
    if tok in NEGATIONS:
        return "word"
    return "verb" if _CIRCUMFIX.match(tok) else None


def _lexicon_index(groups) -> tuple:
    """(term -> group number, [group variants])."""
    idx, vs = {}, []
    for g in groups or []:
        g = [t for t in g if t]
        if not g:
            continue
        n = len(vs)
        vs.append(g)
        for t in g:
            idx.setdefault(t, n)
    return idx, vs


def _drug_spans(toks: list, doubtful: list, index: dict, medical: bool, latin_rule: bool) -> list:
    """(start, end, group number | None) token spans that name a drug or product. Longer matches first; a name split
    over two or three words («ميت فورمين», "para cetamol") counts once; a doubtful long word one letter away from a
    listed name («اوزمبك») counts too."""
    multi = sorted({tuple(t.split()) for t in index if " " in t}, key=len, reverse=True)
    single = {t for t in index if " " not in t}
    longs = [t for t in single if len(t) >= 6]
    spans, used = [], set()

    def take(a, b, g):
        if not any(k in used for k in range(a, b)):
            spans.append((a, b, g))
            used.update(range(a, b))

    def group_of(tok):
        for s in stems(tok):
            if s in index:
                return index[s]
        return None
    for parts in multi:
        n = len(parts)
        for i in range(len(toks) - n + 1):
            if all(p in stems(toks[i + k]) for k, p in enumerate(parts)):
                take(i, i + n, index[" ".join(parts)])
    for n in (3, 2):
        for i in range(len(toks) - n + 1):
            joined = "".join(toks[i:i + n])
            if len(joined) >= 6 and all(toks[i:i + n]):
                g = group_of(joined)
                if g is not None:
                    take(i, i + n, g)
    for i, t in enumerate(toks):
        if not t or i in used:
            continue
        g = group_of(t)
        if g is not None:
            take(i, i + 1, g)
            continue
        if medical and doubtful[i] and len(t) >= 6 and t not in NEAR_MISS_STOP:
            hit = next((index[x] for x in longs for s in stems(t) if near(s, x)), None)
            if hit is not None:
                take(i, i + 1, hit)
                continue
        if inn_like(t) or (medical and latin_rule and _LATIN.search(t) and len(t) >= 4 and t not in COMMON_LATIN):
            take(i, i + 1, None)
    return spans


def classify(words, meta=None, *, domain: str = "general", terms=None, groups=None) -> list:
    """Every high-risk item of these words (dose, number, drug name, negation by a claim, duration), sure or not: the
    words whose loss changes meaning (K-T2 marks them on the "what we removed" slates)."""
    return [e for e in rank(words, meta, domain=domain, terms=terms, groups=groups, every_item=True) if e["high"]]


def rank(words, meta=None, *, thr: float = DEFAULT_THRESHOLD, domain: str = "general", terms=None,
         groups=None, every_item: bool = False) -> list:
    """The words to confirm, risk first. Each entry: word_ids, text (as heard, decimals kept), start_ms, end_ms, risk,
    high, doubt, why [(ar, en)], score, flagged, and when it applies value (numbers), variants (other spellings of a
    drug), anchor (the claim word a negation belongs to). Stable: the same words give the same list.
    terms: extra names (each its own group); groups: [[spellings of one medicine]]."""
    meta = meta if isinstance(meta, dict) else {}
    ws = [w for w in (words if isinstance(words, list) else []) if isinstance(w, dict)
          and isinstance(w.get("word"), str) and w["word"].strip()]
    ws.sort(key=lambda w: (_num(w.get("start_ms")) or 0, str(w.get("id"))))
    toks = _tokens(ws)
    index, variants = _lexicon_index(list(groups or []) + [[t] for t in (terms or [])])
    redecoded = _spans(meta)
    medical = domain == "medical"
    ar = sum(1 for t in toks if _ARABIC.search(t))
    latin_rule = ar > len(toks) / 2               # a Latin word stands out only in an Arabic clip
    doubts = [_doubt(w, thr, redecoded) for w in ws]

    kinds = [None] * len(ws)
    items = []

    owner = [None] * len(ws)

    def add(a, b, kind, **extra):
        if a >= b or any(kinds[k] for k in range(a, b)):
            return None
        it = {"a": a, "b": b, "risk": kind, **extra}
        for k in range(a, b):
            kinds[k], owner[k] = kind, it
        items.append(it)
        return it
    for q in quantities(toks):
        add(q["start"], q["end"], q["kind"], value=q["value"], **({"alts": q["alts"]} if q.get("alts") else {}))
    for a, b in timing_phrases(toks):
        add(a, b, "duration")
    for i, t in enumerate(toks):
        if t and is_frequency(t):        # «مرتين في اليوم», "twice a day": the tail too
            tail = i + 3 if i + 2 < len(toks) and toks[i + 1] in LINK and is_time(toks[i + 2]) else i + 1
            v = frequency_value(t)
            add(i, tail, "duration", **({"value": v} if v is not None else {}))
    for a, b, g in _drug_spans(toks, [d[0] > 0 for d in doubts], index, medical, latin_rule):
        add(a, b, "drug", **({"variants": variants[g]} if g is not None else {}))
    anchors = sorted({k for k, x in enumerate(kinds) if x in HIGH} | {k for k, t in enumerate(toks) if t and _cue_core(t)})
    for i, t in enumerate(toks):
        kind = _negation(t) if t else None
        if not kind:
            continue
        near_ = [k for k in anchors if k != i and abs(k - i) <= NEAR and kinds[k] != "negation"]
        inner = kind == "verb" and _cue_core(t)              # «ماتاخدهاش»: the claim is inside the word
        if near_ or inner:
            # every claim word or risky item within reach: the graphic must show the negation with one of them, matched
            # the way that item is matched (a number by its value, a drug by any spelling, a word by its stem)
            anchor_items, seen = [], set()
            for k in sorted(near_, key=lambda k: (abs(k - i), k)):
                it = owner[k]
                key = id(it) if it else ("tok", k)
                if key in seen:
                    continue
                seen.add(key)
                if it and it["risk"] in HIGH:
                    anchor_items.append({"risk": it["risk"], "text": " ".join(toks[it["a"]:it["b"]]),
                                         **{x: it[x] for x in ("value", "alts", "variants") if it.get(x) is not None}})
                else:
                    anchor_items.append({"risk": "claim", "text": toks[k]})
            add(i, i + 1, "negation", anchors=anchor_items or None)
    claim_anchor = anchors + [k for k, x in enumerate(kinds) if x == "negation"]
    for i, t in enumerate(toks):
        if kinds[i] or not t:
            continue
        if t in FILLERS:
            kind = "filler"
        elif any(abs(i - k) <= CLAIM_SPAN for k in claim_anchor):
            kind = "claim"
        else:
            kind = "other"
        add(i, i + 1, kind)

    out = []
    for it in items:
        rng = range(it["a"], it["b"])
        d = max(doubts[k][0] for k in rng)
        if d <= 0 and not every_item:
            continue
        why = []
        for k in rng:
            why += [r for r in doubts[k][1] if r not in why]
        group = [ws[k] for k in rng]
        e = {"word_ids": [w.get("id") for w in group], "text": " ".join(w["word"].strip() for w in group),
             "start_ms": _num(group[0].get("start_ms")), "end_ms": _num(group[-1].get("end_ms")),
             "risk": it["risk"], "high": it["risk"] in HIGH, "doubt": round(d, 3), "why": why,
             "score": round(WEIGHT[it["risk"]] * d, 4), "flagged": any(bool(w.get("flagged")) for w in group)}
        for k in ("value", "alts", "variants", "anchors"):
            if it.get(k) is not None:
                e[k] = it[k]
        out.append(e)
    out.sort(key=lambda e: (TIER[e["risk"]], -e["score"], e["start_ms"] or 0, str(e["word_ids"][0])))
    return out


# --- reading a project -------------------------------------------------------------------------------------------------
def _read(path):
    try:
        data = Path(path).read_bytes()
        return data, json.loads(data.decode("utf-8-sig"))
    except Exception:  # noqa: BLE001  (missing or damaged: today's checks own it, K-T1 adds nothing)
        return None, None


def _current(ver, data) -> bool:
    if not isinstance(ver, dict) or ver.get("verified") is not True or data is None:
        return False
    return ver.get("words_sha1") in (None, hashlib.sha1(data).hexdigest())


def _who(ver: dict, key: str = "by") -> str:
    return str(ver.get(key) or "").strip().lower()


def confirmed(paths) -> bool:
    """Today's confirmation: verification.json says verified, for THESE words (sha1), by the editor's own ear
    (`--by editor`, the allow-list NEEDS-YOU uses: auto, delegated, claude, an agent or no name do not count). A
    reel's copy of its episode's verification counts only when the episode's own verification is the editor's and
    still current."""
    data, wj = _read(paths.p("02_transcription/words.json"))
    _, ver = _read(paths.p("02_transcription/verification.json"))
    if not _current(ver, data):
        return False
    if _who(ver) in BY_EAR:
        return True
    if _who(ver) != EPISODE_BY or ("episode_by" in ver and _who(ver, "episode_by") not in BY_EAR):
        return False
    ep = (wj.get("meta") or {}).get("episode_transcript") if isinstance(wj, dict) else None
    if not isinstance(ep, str) or not ep:
        return False
    folder = Path(ep).parent
    ep_data, _ = _read(folder / "words.json")
    _, ep_ver = _read(folder / "verification.json")
    return _current(ep_ver, ep_data) and _who(ep_ver) in BY_EAR


def context(ctx=None) -> dict:
    """The settings rank() needs, from the client's configuration: threshold, domain, lexicon. Never raises."""
    from ..common import content_domain, current_context, use_context
    ctx = ctx or current_context()
    with use_context(ctx):
        thr, basis = threshold(ctx)
        lex = load_sources()
        try:
            domain = content_domain()
        except Exception:  # noqa: BLE001  (a damaged profile.json: today's checks report it; rank as general)
            domain = "general"
        # the client glossary names medicines only for a medical client (a religious client's glossary holds verse
        # words: «آمنوا» is not a drug name)
        return {"thr": thr, "basis": basis, "domain": domain, "groups": lex["groups"],
                "terms": client_terms(ctx) if domain == "medical" else [],
                "lexicon_refused": lex["refused"]}


def for_project(paths, ctx=None) -> dict | None:
    """{"confirmed", "threshold", "basis", "items", "lexicon_refused"} for the panel and NEEDS-YOU; None when
    words.json is missing or damaged."""
    _, wj = _read(paths.p("02_transcription/words.json"))
    if not isinstance(wj, dict) or not isinstance(wj.get("words"), list):
        return None
    c = context(ctx)
    items = rank(wj["words"], wj.get("meta"), thr=c["thr"], domain=c["domain"], terms=c["terms"], groups=c["groups"])
    ok = confirmed(paths)
    data, _ = _read(paths.p("02_transcription/words.json"))
    _, ver = _read(paths.p("02_transcription/verification.json"))
    verified_by = _who(ver) if not ok and _current(ver, data) else None     # verified, but not as the editor's ear
    return {"confirmed": ok, "threshold": c["thr"], "basis": c["basis"], "items": items,
            "lexicon_refused": c["lexicon_refused"], "domain": c["domain"], "verified_by": verified_by}


def _tc(ms) -> str:
    ms = int(ms or 0)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000 // 100}"


# --- surfaces (each behind the K-T1 switch) ----------------------------------------------------------------------------
def _has(tok: str, shown: set) -> bool:
    return any(s in shown for s in stems(tok)) or any(_cue_core(x) and tok in x for x in shown if len(tok) >= 4)


def _shown(entry: dict, text: str) -> bool:
    """Does the graphic text show this item? A number by its value (any script, spelled; «٣٫٥» on screen is «3.5»
    heard, «35» is not); a drug by any spelling of its group; a negation only together with the claim word it belongs
    to (one unsure «مش» does not block every graphic that says «مش»); anything else by all its words."""
    toks = tokens(text)
    shown = {s for t in toks for s in stems(t)}
    if entry.get("value") is not None:              # "1.500" heard may be 1.5 or 1500: either one on screen
        seen = values_in(text)
        return any(canon(v) in seen for v in [entry["value"], *(entry.get("alts") or [])])
    parts = [fold(t) for t in entry["text"].split() if fold(t)]
    if not parts:
        return False
    if entry["risk"] == "drug":
        names = set(entry.get("variants") or []) | {" ".join(parts), "".join(parts)}
        joined = " ".join(toks)
        return any((" " in n and f" {n} " in f" {joined} ") or (" " not in n and n in shown) for n in names) \
            or all(p in shown for p in parts)
    if entry["risk"] == "negation":
        if not all(_has(p, shown) for p in parts):
            return False
        anchors = entry.get("anchors")
        return not anchors or any(_shown(a, text) for a in anchors)
    return all(_has(p, shown) for p in parts)


def _errors(rep: dict, events) -> list:
    from ..plan import onscreen_strings
    errs = []
    for ev in events if isinstance(events, list) else []:
        if not isinstance(ev, dict):
            continue
        text = " ".join(s for s in onscreen_strings(ev.get("params")) if isinstance(s, str))
        if not text.strip():
            continue
        for e in rep["items"]:
            # a plain number blocks only for a medical client («٣ عيال» heard is not «3 نصائح» shown)
            plain = e["risk"] == "number" and rep.get("domain") != "medical"
            if not e["high"] or e["flagged"] or plain or not _shown(e, text):
                continue
            ar, en = LABEL[e["risk"]]
            ids = ", ".join(str(i) for i in e["word_ids"])
            ar_why = "، ".join(r[0] for r in e["why"])
            en_why = "; ".join(r[1] for r in e["why"])
            errs.append(f"{ev.get('event_id')}: «{e['text']}» ({_tc(e['start_ms'])}) {ar} والتفريغ مش متأكد منها "
                        f"({ar_why}): اسمعها وأكّدها قبل ما تظهر على الشاشة — on-screen text uses '{e['text']}' "
                        f"(word {ids}, {_tc(e['start_ms'])}), a {en} the transcription is unsure of ({en_why}): "
                        "confirm it by ear first (correct it in transcript-corrections.json if needed), then "
                        "`reel transcript-verify`" + _who_hint(rep.get("verified_by")))
    return errs


def _who_hint(name) -> str:
    """The transcript is verified, but not as the editor's own ear: say so, or the editor waits on a block they think
    they already cleared."""
    if name is None:
        return ""
    shown = name or "(بدون اسم / no name)"
    return (f" — المراجعة اتسجّلت باسم «{shown}»، ودي مش موافقة المونتير بالسمع: بعد ما المونتير يسمعها، "
            f"`reel transcript-verify --by editor` / the check was recorded as \"{shown}\", which is not the "
            "editor's ear: once the editor has listened, `reel transcript-verify --by editor`")


def plan_errors(paths, events, ctx=None) -> list:
    """`reel plan` errors for graphics that show a high-risk word still unconfirmed. [] while the switch is off, once
    the transcript is confirmed, or when words.json is missing or damaged (today's checks report that). A word the
    transcript editor flagged is left to today's flagged-word check (no double report). Never raises: an unexpected
    failure becomes one plain error, so the editor knows the check did not run."""
    if not switches.enabled(switches.PLAN_BLOCK, ctx):
        return []
    try:
        rep = for_project(paths, ctx)
        if not rep or rep["confirmed"]:
            return []
        return _errors(rep, events)
    except Exception as e:  # noqa: BLE001
        return [f"فحص الكلمات المهمة ما اشتغلش ({type(e).__name__}): راجع الجرعات والأرقام وأسماء الأدوية اللي على "
                f"الجرافيك بالسمع قبل الموافقة — the risk-first word check did not run ({type(e).__name__}): check the "
                "doses, numbers and drug names on the graphics by ear before approving"]


def review_block(rep: dict) -> str:
    """The "check these first" block for the top of subtitle-review.md, Arabic first."""
    high = [e for e in rep["items"] if e["high"]]
    L = [f"## راجع دول الأول — Check these first ({len(high)})", "",
         "دي كلمات فيها جرعة أو رقم أو اسم دوا أو نفي أو مدة، والتفريغ مش متأكد منها. اسمعها الأول بالترتيب ده، "
         "ومش هتظهر على الجرافيك لحد ما تأكّد التفريغ (`reel transcript-verify`).",
         "These words carry a dose, a number, a drug name, a negation or a duration, and the transcription is unsure "
         "of them. Listen to them first, in this order; they stay off the graphics until the transcript is confirmed "
         "(`reel transcript-verify`).", "",
         f"- عتبة الثقة / threshold: {rep['threshold']:g} — {rep['basis']}", ""]
    for e in high:
        ar, en = LABEL[e["risk"]]
        L.append(f"- `{_tc(e['start_ms'])}` **{e['text']}** — {ar} / {en} — "
                 + "؛ ".join(r[0] for r in e["why"]) + " / " + "; ".join(r[1] for r in e["why"])
                 + f" (word {', '.join(str(i) for i in e['word_ids'])})")
    if not high:
        L.append("- مفيش / none")
    for r in rep.get("lexicon_refused") or []:
        L.append(f"- {r.get('reason_ar') or r['id']} / lexicon source {r['id']} refused: {r['reason']}")
    return "\n".join(L) + "\n"


def with_review_block(review_md: str, paths, ctx=None) -> str:
    """subtitle-review.md with the block placed before its first section. Unchanged while the switch is off, when
    words.json is missing or damaged, or if the block cannot be built."""
    if not switches.enabled(switches.PLAN_BLOCK, ctx):
        return review_md
    try:
        rep = for_project(paths, ctx)
        if not rep:
            return review_md
        block = review_block(rep)
    except Exception:  # noqa: BLE001  (an aid on top of today's review; never blocks the transcript)
        return review_md
    k = review_md.find("\n## ")
    return review_md + "\n" + block if k < 0 else review_md[:k + 1] + block + "\n" + review_md[k + 1:]


def needs_you_order(todo: list, paths, ctx=None) -> list:
    """NEEDS-YOU's words, risk first: the words of every high-risk item still to confirm (from words.json, in rank
    order, even when today's lower threshold left them out), then the rest of today's list in today's order. Nothing
    of today's list is dropped. Unchanged while the switch is off, when words.json is missing or damaged, or once the
    transcript is confirmed."""
    if not switches.enabled(switches.PLAN_BLOCK, ctx):
        return todo
    try:
        rep = for_project(paths, ctx)
        if not rep or rep["confirmed"]:
            return todo
        _, wj = _read(paths.p("02_transcription/words.json"))
        by_id = {w.get("id"): w for w in wj["words"] if isinstance(w, dict)}
    except Exception:  # noqa: BLE001
        return todo
    first, seen = [], set()
    for e in rep["items"]:
        if not e["high"]:
            continue
        for wid in e["word_ids"]:
            if wid in by_id and wid not in seen:
                seen.add(wid)
                first.append(by_id[wid])
    return first + [w for w in todo if not (isinstance(w, dict) and w.get("id") in seen)]
