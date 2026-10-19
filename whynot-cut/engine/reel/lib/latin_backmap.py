# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Latin back-map (3.0 Phase 4 Task 55 = Addendum M2-T3, approach 3): English terms that Whisper wrote in Arabic
letters are PROPOSED in Latin letters («إنسولين» → insulin), never applied.

The pair list is config/defaults/latin-terms.json: `{latin, arabic: [spellings], domain, source}` per term, built only
from our own review lexicons (config/review-domains/lexicons/*.json) and the medical glossary (`check_pairs` proves it:
every Latin term and every Arabic spelling is a term of the lexicon of its domain, or of the glossary). Kalam reads the
same file (6B).

A run of words is a candidate when its spelling, in the plan.norm form (NFKC, invisible format characters such as
ZWJ, bidi marks and zero-width spaces dropped, diacritics and tatweel dropped, alef forms, ى and ة folded, edge
punctuation dropped), equals one of the list's Arabic spellings, word for word; the first word may carry ONE joined
clitic (و ف ب ل ك ال and their pairs), which stays in Arabic in front of the Latin word: «بالإنسولين» → «بالـ insulin»
(tatweel after a letter that joins forward, the M2 «الـ» + Latin unit), «وإنسولين» → «و insulin». The longest
spelling wins («شات جي بي تي» before «جي بي تي»). A candidate is PROPOSED only when the audio and the context agree:
  * audio: every word of the term has a probability >= the threshold (transcription.json `low_confidence_threshold`,
    default 0.5); a word with no probability is not confident;
  * context: within CONTEXT_WORDS (3) words before or after the term (its own words excluded), a word in Latin letters,
    a hit of the review lexicon of the entry's own domain (lib/review_domains.detect on those words), or another
    pair-list term.
Never a candidate, whatever the context:
  * a word of a profile person's name or of the client's display name (`profile.json` people[].name, display_name);
  * a word inside a recited verse (lib/manual_verse.detect, the manual verse slot's own spans: after «قال تعالى» … to
    the next pause, the basmala, the isti'adha, a religious client's listed verse phrases), a hadith (after
    «قال رسول الله», «قال النبي», «قال الرسول» … to the next pause, by the same pause and cap rules) or a ﴿ ﴾ zone
    written in the transcript.
  * any word for a client whose profile says `latin_backmap: false` (an Arabic-first client keeps English terms in
    Arabic letters).
Each proposal carries the ready transcript-corrections.json rows (`corrections`: the first word becomes the Latin form,
the term's other words merge into it with an empty `to`), so once the editor agrees by ear the transcript-editor copies
them into transcript-corrections.json and runs `reel transcript-correct`. This module never writes words.json,
transcript.json or transcript-corrections.json: `write_proposals` writes only 02_transcription/latin-proposals.json
(deterministic bytes: no clock, sorted rows, the words.json sha1 it was made from) and `review_lines` gives the
"Latin term proposals" section of subtitle-review.md. Standard library only; linear in the number of words (the
context check runs only for candidates, and a repeated context is looked up once).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from .common import PLUGIN_DIR, load_config, read_json, write_json
from .errors import Guidance
from .plan import norm

PAIRS_FILE = PLUGIN_DIR / "config" / "defaults" / "latin-terms.json"
GLOSSARY_FILE = PLUGIN_DIR / "config" / "defaults" / "medical-glossary.json"
OUT = "02_transcription/latin-proposals.json"
SCHEMA = 1
CONTEXT_WORDS = 3
DEFAULT_THRESHOLD = 0.5            # transcription.json low_confidence_threshold, when the config does not say
HIGH = 0.9                         # a term this sure is a "high" correction row, else "medium" (the editor confirms)
# one joined clitic on the first word, longest first: conjunction / preposition, with or without the article
CLITICS = ("وبال", "فبال", "وكال", "فكال", "وال", "فال", "بال", "كال", "ولل", "فلل", "لل", "ال",
           "وب", "فب", "ول", "فل", "وك", "فك", "و", "ف", "ب", "ل", "ك")
_NON_JOINING = set("اأإآءدذرزوؤةى")   # letters that never join the next one: no tatweel after them («و insulin»)
TATWEEL = "ـ"
HADITH_CUES = ("قال رسول الله", "قال النبي", "قال الرسول", "يقول النبي", "يقول رسول الله", "عن النبي",
               "عن رسول الله")
_LATIN = re.compile(r"[A-Za-z]")
_ARABIC_LETTER = re.compile(r"[\u0621-\u063f\u0641-\u064a\u0671-\u06d3\u06fa-\u06ff]")  # no tatweel (U+0640)
NOTE = ("Proposals only: the engine never applied them. Each one needs the editor's ear; the accepted rows go into "
        "transcript-corrections.json (`corrections`), then `reel transcript-correct`.")
WHY = {"low_confidence": "the audio is not sure of the word", "no_context": "no English or domain word near it",
       "name": "a person's or the client's name", "religious_zone": "inside a verse, a hadith or ﴿ ﴾"}


# --------------------------------------------------------------------------------------------- text
def _no_format(s: str) -> str:
    """Invisible format characters (Unicode Cf: ZWJ/ZWNJ, RLM/LRM, bidi embeddings and isolates, ZWSP, BOM) dropped."""
    return "".join(c for c in str(s) if unicodedata.category(c) != "Cf")


def key(word) -> str:
    """The matching form of one word: plan.norm with its spaces removed (one word, one key). plan.norm turns every
    character that is not a word character into a space, so invisible format characters (ZWJ, bidi marks, ZWSP, BOM)
    inside a word vanish here too."""
    return norm(word if isinstance(word, str) else "").replace(" ", "")


def _edges(raw: str) -> tuple[str, str, str]:
    """(leading punctuation, the word, trailing punctuation) of one raw word: Unicode P*/S* and format characters."""
    s = _no_format(raw)
    a, b = 0, len(s)
    while a < b and unicodedata.category(s[a])[0] in "PS":
        a += 1
    while b > a and unicodedata.category(s[b - 1])[0] in "PS":
        b -= 1
    return s[:a], s[a:b], s[b:]


def _clean_prefix(core: str, n_letters: int) -> str:
    """The first n_letters Arabic letters of a word as written, without diacritics or tatweel."""
    out = []
    for ch in unicodedata.normalize("NFKC", core):
        if _ARABIC_LETTER.match(ch):
            out.append(ch)
            if len(out) == n_letters:
                break
    return "".join(out)


def _latin_form(first_raw: str, last_raw: str, clitic: str, latin: str) -> str:
    """The proposed text: edge punctuation kept, a clitic kept in Arabic («بالـ insulin», «و insulin»)."""
    lead = _edges(first_raw)[0]
    trail = _edges(last_raw)[2]
    if clitic:
        pre = _clean_prefix(_edges(first_raw)[1], len(clitic))
        join = "" if pre[-1:] in _NON_JOINING else TATWEEL
        return f"{lead}{pre}{join} {latin}{trail}"
    return f"{lead}{latin}{trail}"


# --------------------------------------------------------------------------------------------- the pair list
def _lexicon_terms(domain: str) -> list:
    from .review_domains import lexicon
    lex = lexicon(domain)
    return [t for r in (lex.get("rules") or []) + (lex.get("supporting") or []) for t in (r.get("terms") or [])
            if isinstance(t, str)]


def check_pairs(doc, glossary=None) -> list:
    """Problems of a pair-list document (empty = good): structure, an Arabic spelling mapped to two Latin terms, and
    provenance (every Latin term and Arabic spelling is a term of its domain's lexicon or of the glossary)."""
    from .review_domains import normalize, registry
    if not isinstance(doc, dict):
        return ["the pair list is not a JSON object"]
    probs = []
    if doc.get("schema") != SCHEMA:
        probs.append(f"schema must be {SCHEMA}")
    terms = doc.get("terms")
    if not isinstance(terms, list):
        return probs + ["terms must be a list"]
    try:
        domains = set(registry())
    except Exception as e:  # noqa: BLE001 — a broken registry is reported, not raised
        return probs + [f"the review-domain registry cannot be read: {e}"]
    gl = read_json(GLOSSARY_FILE, {}) if glossary is None else glossary
    gl_terms = (gl or {}).get("terms") or {} if isinstance(gl, dict) else {}
    gl_latin = {str(x).casefold() for x in gl_terms.get("english") or []}
    gl_arabic = {normalize(str(x)) for x in gl_terms.get("arabic") or []}
    seen: dict = {}
    lex_cache: dict = {}
    for i, t in enumerate(terms):
        where = f"terms[{i}]"
        if not isinstance(t, dict):
            probs.append(f"{where}: not an object")
            continue
        lat, ar, dom, src = t.get("latin"), t.get("arabic"), t.get("domain"), t.get("source")
        if not isinstance(lat, str) or not lat.strip():
            probs.append(f"{where}: latin must be a non-empty text")
            lat = None
        elif not re.fullmatch(r"[A-Za-z][A-Za-z0-9 .+-]*", lat):
            probs.append(f"{where}: latin {lat!r} must be in Latin letters")
        if not isinstance(ar, list) or not ar or not all(isinstance(a, str) and a.strip() for a in ar):
            probs.append(f"{where}: arabic must be a non-empty list of spellings")
            ar = []
        if not isinstance(dom, str) or dom not in domains:
            probs.append(f"{where}: domain {dom!r} is not a review domain ({', '.join(sorted(domains))})")
            dom = None
        if not isinstance(src, str) or not src.strip():
            probs.append(f"{where}: source must name the lexicon or glossary the term comes from")
        lex = None
        if dom:
            if dom not in lex_cache:
                try:
                    lex_cache[dom] = _lexicon_terms(dom)
                except Exception:  # noqa: BLE001
                    lex_cache[dom] = []
            lex = lex_cache[dom]
        lex_latin = {x.rstrip("*").casefold() for x in lex or []}
        lex_arabic = {normalize(x.rstrip("*")) for x in lex or []}
        if lat and lex is not None and lat.casefold() not in lex_latin and lat.casefold() not in gl_latin:
            probs.append(f"{where}: {lat!r} is in neither the {dom} lexicon nor the glossary (our own lists only)")
        for a in ar:
            if not _ARABIC_LETTER.search(a) or _LATIN.search(a):
                probs.append(f"{where}: spelling {a!r} must be in Arabic letters")
                continue
            if lex is not None and normalize(a) not in lex_arabic and normalize(a) not in gl_arabic:
                probs.append(f"{where}: spelling {a!r} is in neither the {dom} lexicon nor the glossary")
            k = " ".join(key(x) for x in a.split())
            if k in seen and seen[k] != (lat or "").casefold():
                probs.append(f"{where}: spelling {a!r} maps to two Latin terms ({seen[k]!r} and {lat!r})")
            seen.setdefault(k, (lat or "").casefold())
    return probs


def load_pairs(path=None) -> list:
    """The checked terms of the pair list (default config/defaults/latin-terms.json); a broken list is refused."""
    f = Path(path) if path else PAIRS_FILE
    doc = read_json(f, None)
    probs = check_pairs(doc) if doc is not None else [f"{f} is missing"]
    if probs:
        raise Guidance(f"the Latin pair list {f.name} is not usable: " + "; ".join(probs[:5]),
                       "Fix config/defaults/latin-terms.json: each term needs its Latin form and its Arabic spelling "
                       "in one of our review lexicons (or the glossary) first")
    return doc["terms"]


def _index(pairs: list) -> dict:
    """first key -> [(keys tuple, entry)], longest spelling first (then by Latin form: deterministic)."""
    idx: dict = {}
    for e in pairs or []:
        if not isinstance(e, dict) or not isinstance(e.get("latin"), str):
            continue
        for sp in e.get("arabic") or []:
            ks = tuple(k for k in (key(x) for x in str(sp).split()) if k)
            if ks:
                idx.setdefault(ks[0], []).append((ks, e))
    for v in idx.values():
        v.sort(key=lambda x: (-len(x[0]), x[1]["latin"]))
    return idx


# --------------------------------------------------------------------------------------------- the profile
def _off(profile: dict) -> bool:
    v = profile.get("latin_backmap")
    return v is False or (isinstance(v, str) and v.strip().lower() in ("false", "off", "no"))


def _name_keys(profile: dict) -> set:
    from .people import PARTICLES, TITLES
    texts = [p.get("name") for p in profile.get("people") or [] if isinstance(p, dict)]
    texts.append(profile.get("display_name"))
    out = set()
    for t in texts:
        if isinstance(t, str):
            for w in re.split(r"[\s/|,،]+", t):
                k = key(w)
                if len(k) >= 2 and k not in PARTICLES and k not in TITLES:
                    out.add(k)
    return out


def default_threshold() -> float:
    try:
        v = load_config("transcription.json").get("low_confidence_threshold")
        return float(v) if v is not None else DEFAULT_THRESHOLD
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


# --------------------------------------------------------------------------------------------- zones
def _good(w) -> bool:
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(w, dict) and isinstance(w.get("word"), str) and num(w.get("start_ms")) and num(w.get("end_ms"))


def _phrase_at(stream: list, k: int, phrase: list) -> bool:
    """The cue's tokens start at token k; its first token may carry «و» or «ف» («وقال النبي»)."""
    if not phrase or k + len(phrase) > len(stream):
        return False
    for j, want in enumerate(phrase):
        tok = stream[k + j][0]
        if tok != want and not (j == 0 and tok in ("و" + want, "ف" + want)):
            return False
    return True


def _run_end(words: list, j: int, start: float) -> float:
    """From word j: where the speech run ends (the first pause >= manual_verse.PAUSE_MS), capped CAP_MS after start."""
    from .manual_verse import CAP_MS, PAUSE_MS
    end = words[j]["end_ms"]
    while j + 1 < len(words) and words[j + 1]["start_ms"] - words[j]["end_ms"] < PAUSE_MS and end - start <= CAP_MS:
        j += 1
        end = words[j]["end_ms"]
    return min(end, start + CAP_MS)


def _zones(words: list, profile: dict) -> set:
    """Indexes of the words inside a recited verse (lib/manual_verse.detect), a hadith (after a HADITH_CUES cue, from the
    next word to the next pause, capped) or a ﴿ ﴾ zone."""
    from . import manual_verse as MV
    ranges = [(s["src_start_ms"], s["src_end_ms"]) for s in MV.detect(words, MV.config(profile))]
    stream = [(t, i) for i, w in enumerate(words) for t in MV.tokens(w["word"])]
    cues = [MV.tokens(c) for c in HADITH_CUES]
    k = 0
    while k < len(stream):
        ph = next((c for c in cues if _phrase_at(stream, k, c)), None)
        if not ph:
            k += 1
            continue
        nxt = stream[k + len(ph) - 1][1] + 1
        if nxt < len(words):
            start = words[nxt]["start_ms"]
            ranges.append((start, _run_end(words, nxt, start)))
        k += len(ph)
    merged = []                                       # disjoint spans in time order
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    inside, r = set(), 0
    for n, w in enumerate(words):                     # words in time order: one sweep over the spans
        while r < len(merged) and merged[r][1] <= w["start_ms"]:
            r += 1
        if r < len(merged) and merged[r][0] < w["end_ms"]:
            inside.add(n)
    depth = 0                                         # ﴿ … ﴾ written in the transcript (an editor's correction)
    for n, w in enumerate(words):
        opens, closes = w["word"].count("﴿"), w["word"].count("﴾")
        if depth or opens:
            inside.add(n)
        depth = max(0, depth + opens - closes)
    return inside


# --------------------------------------------------------------------------------------------- matching
def _match_at(keys: list, i: int, idx: dict):
    """(n words, clitic, entry) for the longest pair-list term starting at word i, or None."""
    k = keys[i]
    if not k:
        return None
    firsts = [(k, "")] + [(k[len(c):], c) for c in CLITICS if k.startswith(c) and len(k) - len(c) >= 2]
    best = None
    for first, clitic in firsts:
        for ks, e in idx.get(first, ()):
            n = len(ks)
            if i + n <= len(keys) and all(keys[i + j] == ks[j] for j in range(1, n)):
                if best is None or n > best[0]:
                    best = (n, clitic, e)
                break                                 # longest first within this first key
    return best


def analyse(words: list, pairs: list, *, profile: dict | None = None, threshold: float | None = None,
            context: int = CONTEXT_WORDS) -> dict:
    """{"status", "proposals": [...], "skipped": [{word_ids, from, latin, why}]}: the whole decision, nothing written."""
    from .review_domains import detect, matchers
    prof = profile if isinstance(profile, dict) else (load_config("profile.json") or {})
    thr = default_threshold() if threshold is None else float(threshold)
    if _off(prof):
        return {"status": "off", "proposals": [], "skipped": []}
    ws = sorted((w for w in words or [] if _good(w)), key=lambda w: (w["start_ms"], w["end_ms"], str(w.get("id"))))
    keys = [key(w["word"]) for w in ws]
    idx = _index(pairs)
    hits, i = [], 0
    while i < len(ws):
        m = _match_at(keys, i, idx)
        if m:
            hits.append((i, *m))
            i += m[0]
        else:
            i += 1
    if not hits:
        return {"status": "none", "proposals": [], "skipped": []}
    in_term = {j for (s, n, _c, _e) in hits for j in range(s, s + n)}
    names = _name_keys(prof)
    zones = _zones(ws, prof)
    ms, ctx_cache = None, {}
    props, skipped = [], []
    for s, n, clitic, e in hits:
        span = ws[s:s + n]
        raw = " ".join(w["word"] for w in span)
        ids = [w.get("id") for w in span]
        probs = [w.get("probability") for w in span]
        conf = min((p if isinstance(p, (int, float)) and not isinstance(p, bool) else -1.0) for p in probs)
        term_keys = {keys[j] for j in range(s, s + n)} | ({keys[s][len(clitic):]} if clitic else set())
        why = None
        if term_keys & names:
            why = "name"
        elif any(j in zones for j in range(s, s + n)):
            why = "religious_zone"
        elif conf < thr:
            why = "low_confidence"
        else:
            near = [j for j in range(max(0, s - context), min(len(ws), s + n + context)) if not s <= j < s + n]
            ok = any(_LATIN.search(ws[j]["word"]) for j in near) or any(j in in_term for j in near)
            if not ok and near:
                text = " ".join(ws[j]["word"] for j in near)
                if (e["domain"], text) not in ctx_cache:
                    ms = ms if ms is not None else matchers()
                    ctx_cache[(e["domain"], text)] = e["domain"] in detect(text, ms)
                ok = ctx_cache[(e["domain"], text)]
            why = None if ok else "no_context"
        if why:
            skipped.append({"word_ids": ids, "start_ms": span[0]["start_ms"], "from": raw, "latin": e["latin"],
                            "why": why})
            continue
        to = _latin_form(span[0]["word"], span[-1]["word"], clitic, e["latin"])
        reason = (f"«{raw}» is the Arabic spelling of the {e['domain']} term \"{e['latin']}\" (latin-terms.json); "
                  f"audio p={round(conf, 3)}, English or {e['domain']} words near it")
        level = "high" if conf >= HIGH else "medium"
        rows = [{"word_id": ids[0], "from": span[0]["word"], "to": to, "reason": reason, "confidence": level}]
        rows += [{"word_id": w.get("id"), "from": w["word"], "to": "", "reason": f"part of «{raw}» → {to}",
                  "confidence": level} for w in span[1:]]
        props.append({"word_id": ids[0], "word_ids": ids, "start_ms": span[0]["start_ms"], "end_ms": span[-1]["end_ms"],
                      "from": raw, "to": to, "latin": e["latin"], "domain": e["domain"],
                      "confidence": round(conf, 3), "reason": reason, "status": "proposed", "corrections": rows})
    return {"status": "proposed" if props else "none", "proposals": props, "skipped": skipped}


def propose(words: list, pairs: list, *, profile: dict | None = None, threshold: float | None = None,
            context: int = CONTEXT_WORDS) -> list:
    """The proposals for a words list (words.json rows), in time order. Nothing is written or changed."""
    return analyse(words, pairs, profile=profile, threshold=threshold, context=context)["proposals"]


# --------------------------------------------------------------------------------------------- files
def write_proposals(paths, profile: dict | None = None, pairs: list | None = None,
                    threshold: float | None = None) -> dict:
    """02_transcription/latin-proposals.json from 02_transcription/words.json; nothing else is written."""
    wf = paths.p("02_transcription/words.json")
    if not wf.exists():
        raise Guidance("there is no 02_transcription/words.json to read Latin terms from",
                       "Transcribe first (`reel transcribe`), then propose Latin terms")
    data = wf.read_bytes()
    doc = read_json(wf)
    words = doc.get("words") if isinstance(doc, dict) else doc
    thr = default_threshold() if threshold is None else float(threshold)
    res = analyse(words if isinstance(words, list) else [], load_pairs() if pairs is None else pairs,
                  profile=profile, threshold=thr)
    out = {"schema": SCHEMA, "status": res["status"], "note": NOTE, "words_sha1": hashlib.sha1(data).hexdigest(),
           "threshold": thr, "context_words": CONTEXT_WORDS, "proposals": res["proposals"], "skipped": res["skipped"]}
    f = write_json(paths.p(OUT), out)
    return {"file": str(f), "status": res["status"], "proposals": len(res["proposals"]),
            "skipped": len(res["skipped"])}


def review_lines(doc) -> list:
    """The "Latin term proposals" section of subtitle-review.md, in its style (markdown lines; [] with no file)."""
    from .common import fmt_ts
    if not isinstance(doc, dict):
        return []
    if doc.get("status") == "off":
        return ["## Latin term proposals — off", "Off for this client (profile.json `latin_backmap: false`).", ""]
    props = doc.get("proposals") or []
    out = [f"## Latin term proposals — {len(props)}", "",
           "English terms Whisper wrote in Arabic letters, from config/defaults/latin-terms.json, where the audio and the "
           f"context agree. {NOTE} Proposals were never applied: confirm each by ear.", ""]
    out += [f"- `{fmt_ts(p.get('start_ms', 0), '.')}` «{p.get('from')}» → **{p.get('to')}** (word"
            f"{'s' if len(p.get('word_ids') or []) > 1 else ''} {', '.join(str(i) for i in p.get('word_ids') or [])}, "
            f"p={p.get('confidence')})" for p in props] or ["- none"]
    counts: dict = {}
    for s in doc.get("skipped") or []:
        counts[s.get("why")] = counts.get(s.get("why"), 0) + 1
    if counts:
        out += ["", "Not proposed: " + "; ".join(f"{n} × {WHY.get(w, w)}" for w, n in sorted(counts.items()))]
    return out + [""]
