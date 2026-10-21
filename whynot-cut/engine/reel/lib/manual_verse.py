# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Manual verse slot (owner decision 2026-10-18, «خلي الايديتور هو اللي يعملها … مانيوال»): WhyNot Cut never writes
Quran text. A recited verse in the transcript is left for the editor to add by hand from a trusted Mushaf.

Pure helpers (no file writes; `config` reads the religious lexicon through review_domains, `reel_spans` reads an
episode's reel plans; nothing else reads):
  config(profile)            which cues apply: the recitation cue class for every client; for a client whose review
                             domains include religious, also the religious lexicon's `verse-phrase` list
  detect(words, cfg)         recited-verse spans on the SOURCE clock from word times:
                               * the citation class (fix round 1, P2-2; fix round 2, P1-1): «قال / يقول / بيقول /
                                 قوله» (a joined و/ف), then ONE divine name right after it («الله», «ربنا», «رب
                                 العزة», «الحق سبحانه» …) and ONE honorific group after the name or the verb
                                 («تعالى», «سبحانه وتعالى», «عز وجل», «جل وعلا», «تبارك وتعالى» …), optionally «في
                                 كتابه الكريم». The span starts AFTER the cue (the speaker's own words stay
                                 captioned); a second name or «تبارك» after that is the verse's first word, so the
                                 span starts AT it. «قال والله» (an oath), «قال الحق», «قال رب البيت», a du'a after the
                                 name («قال الله يرحمه», «قال ربنا يستر») and a name first («ربنا بيقول», everyday
                                 paraphrase far more often than a recitation) never fire;
                               * the basmala and the full isti'adha open a span AT the cue (they are recited text);
                               * a verse phrase (religious clients) is a span over exactly the phrase.
                             A cue span runs from the first word after the cue (a pause right after the cue does not end
                             it) to the first pause >= PAUSE_MS or a change of speaker. Past CAP_MS the end is unknown
                             (`guessed_end`): the span runs on to the first pause after the cap, and past HARD_MS to the
                             end of the sentence or turn (fix round 1, P1-1): nothing after the cue is captioned until a
                             real end. Overlapping spans merge. «آية» alone, «سورة …» and «في الآية» never open one.
  resolve(detected, ed)      the story-editor's edit-decisions.json wins: `manual_verse: [{start_ms, end_ms, note?}]`
                             adds spans (a detected span it overlaps is replaced by it), `manual_verse_off:
                             [{start_ms, end_ms}]` removes the detected spans it overlaps. Ids MV01, MV02 … in time order
  holds / held (fix round 2, P2-1: the plan session's fail-closed ruling)   after a detected span that ends on a
                             pause the verse may go on (a reciter stops at a waqf), so the next caption run is HELD
                             (to the next sentence end, a change of speaker or HOLD_MS) and masked like a span, until
                             the editor releases it: `manual_verse_release: [{start_ms, end_ms}]` in edit-decisions.json
  filter_cues / keep_piece / repeats / strip_recited / marker_comment / hold_comment / label   applying the spans
A span's transcript words are never put into a marker, a NEEDS-YOU line, the edit-plan or a log: Whisper's text of a
recited verse may be a misheard verse. Only ids, timecodes and the cue are shown; a basmala, isti'adha or
verse-phrase cue is NAMED, never quoted.
"""
from __future__ import annotations

import re

SPAN_NAME = "آية: يضيفها المونتير يدويًا"                       # the Premiere marker's name
LINE_AR = "أضف الآية يدويًا من مصحف موثوق ودقّق التشكيل"         # the NEEDS-YOU line
LINE_EN = "add the verse by hand from a trusted Mushaf and check the diacritics"
PLACEHOLDER = "(آية: يضيفها المونتير يدويًا)"                   # in place of evidence that repeats a span's words
GUESSED_AR = "النهاية متخمّنة"
PAUSE_MS = 700                     # a pause this long ends a cue's span
CAP_MS = 12000                     # no pause by here: the end is unknown (guessed); the span runs on to the next pause
HARD_MS = 60000                    # still no pause: the span runs on to the end of the sentence or turn
MIN_LEFT_MS = 600                  # a graphic with less than this left outside every span is dropped
RUN = 3                            # this many span words in a row on a graphic / in copy = the verse is repeated
MARKER_COLOUR = 1                  # Premiere marker colour index 1 (red): the "needs the editor" colour
PREFIXES = ("و", "ف")              # a joined conjunction on a cue's first word («وقال تعالى»)
_JOINED = ("و", "ف", "ب", "ل", "ك", "ال", "وال", "فال", "بال", "كال", "لل")   # one joined prefix on a phrase word
_GAPS = re.compile("[​⁠]")                  # zero-width space, word joiner: a word gap (review P3)
_SENTENCE = re.compile(r"[.!?؟…]\W*$")      # a word that closes a sentence

# the citation class (normalised forms: ى as ي, ة as ه, one alef)
VERBS = {"قال", "يقول", "بيقول", "قوله"}
DIVINE = {"الله", "ربنا", "المولي"}                  # a name as said (never with a joined و: «والله» is an oath)
# fix round 2 (review 91cd197, P1-1): a verse may open with a divine name, «ربنا», «تبارك» or «سبحانه», so the cue
# takes ONE name right after the verb and ONE honorific group after the name or the verb; any word after that (another
# name, «تبارك» …) opens the span. A joined و is allowed on an honorific («وتعالى»).
HEADS = {"سبحانه", "عز", "جل"}                        # a group's first word, then optionally one of TAILS
TAILS = {"تعالي", "جل", "علا", "جلاله", "شانه", "ذكره"}   # «سبحانه وتعالى», «عز وجل», «جل وعلا», «جل جلاله» …
HONOR = {"تعالي", "تبارك"} | HEADS | TAILS            # every honorific word (the cue vocabulary)
WITH_HONOR = {"الحق"}                                 # a name only when an honorific follows («الحق سبحانه»)
RABB_OF = {"العزه", "العالمين"}                       # «رب العزة», «رب العالمين»
# «قال الله يرحمه», «قال ربنا يستر»: a du'a after the name (no honorific) is everyday speech, never a citation
DUA = ("يرحم", "يستر", "يسامح", "يخلي", "يكرم", "يهدي", "يحفظ", "يشفي", "يعين", "يبارك", "يوفق", "يجازي", "يسهل",
       "يفرج", "يصبر", "يعوض", "يسعد", "يجبر", "يحمي", "يتقبل", "يرضي", "ينور")
DUA_ENDS = ("", "ه", "ها", "هم", "ك", "كي", "كم", "كو", "ني", "نا", "لك", "له", "لها", "لهم", "لنا", "لي")
_SOFT = re.compile("[\u200c\u200d\ufeff]")  # ZWNJ, ZWJ, BOM (review P3): dropped inside a word, a gap between cue words
# the hold (plan-session ruling 2026-10-20, P2-1): after a span that ends on a pause the verse may go on, so the next
# caption run is held to the next sentence end, a change of speaker or HOLD_MS, until the editor releases it
HOLD_MS = 10000
HOLD_NAME = "تحقق: الآية ممكن تكون مكمّلة"                     # the hold marker's name ("check: verse may continue")
AFTER_AR = "واسمع الكلام اللي بعدها على طول: لو الآية مكمّلة، ضيف الباقي بإيدك كمان"
AFTER_EN = "listen to the words right after it: if the verse goes on, add the rest by hand too"
BOOK = {"كتابه", "القران", "محكم"}                    # «في كتابه الكريم», «في محكم التنزيل»
BOOK_TAIL = {"الكريم", "العزيز", "التنزيل"}
RECITED = (("basmala", "بسم الله الرحمن الرحيم"), ("istiadha", "أعوذ بالله من الشيطان الرجيم"))
_RECITED_WORDS = {"بسم", "الله", "الرحمن", "الرحيم", "اعوذ", "بالله", "الشيطان", "الرجيم"}   # normalised
LABELS = {"basmala": ("من: البسملة", "from the basmala"),
          "istiadha": ("من: الاستعاذة", "from the isti'adha"),
          "verse_phrase": ("عبارة من آية معروفة", "a known verse phrase"),
          "editor": ("حدّدها الستوري إديتور", "marked by the story editor")}


# --------------------------------------------------------------------------- text
def tokens(text) -> list[str]:
    """The matching words of a text: review_domains' normal form (no diacritics or tatweel, one alef, ى as ي, ة as ه),
    then word characters only; a zero-width space or word joiner is a gap between words. A ZWNJ, ZWJ or BOM is
    dropped inside a word, but splits a word whose pieces are cue words and whose joined form is not («قال» + ZWJ + «تعالى»)."""
    from .review_domains import normalize
    s = _GAPS.sub(" ", str(text or ""))
    if _SOFT.search(s):
        s = " ".join(_soft_split(w) for w in s.split())
    return re.findall(r"\w+", normalize(s))


def _cue_word(piece: str) -> bool:
    from .review_domains import normalize
    toks = re.findall(r"\w+", normalize(piece))
    vocab = VERBS | DIVINE | HONOR | WITH_HONOR | RABB_OF | {"رب"} | _RECITED_WORDS
    return len(toks) == 1 and bool(_cands(toks[0], PREFIXES) & vocab)


def _soft_split(word: str) -> str:
    """One word holding a ZWNJ / ZWJ / BOM: split there when a piece is a cue word and the joined word is not."""
    if not _SOFT.search(word):
        return word
    pieces = [x for x in _SOFT.split(word) if x]
    joined = "".join(pieces)
    if len(pieces) > 1 and not _cue_word(joined) and any(_cue_word(x) for x in pieces):
        return " ".join(pieces)
    return joined


def _cands(tok: str, prefixes=_JOINED) -> set:
    return {tok} | {tok[len(p):] for p in prefixes if tok.startswith(p) and len(tok) - len(p) >= 2}


def _plain(word: str) -> str:
    """A cue word as shown: its letters as said, without punctuation or diacritics (the cue is the speaker's own
    words, never a verse)."""
    w = re.sub("[ً-ٰٟـ]", "", _GAPS.sub(" ", str(word)))
    return w.strip(" \t،,.:;؛!؟?«»\"'()[]")


def label(cue: str, lang: str = "ar", text: str | None = None) -> str:
    """How a span's cue is shown: «بعد: قال تعالى» for a cue the speaker says (their own words); a recited cue or a
    verse phrase by its name only (never its text)."""
    if cue == "say":
        t = text or "قال تعالى"
        return f"بعد: {t}" if lang == "ar" else f"after «{t}»"
    ar, en = LABELS.get(cue, LABELS["editor"])
    return ar if lang == "ar" else en


def _fmt(ms) -> str:
    from .common import fmt_ts
    return fmt_ts(int(round(ms)), ".")


def marker_comment(span: dict) -> str:
    """The marker's comment: the span's SOURCE timecodes and its cue, nothing the speaker said."""
    out = (f"المصدر {_fmt(span['src_start_ms'])}–{_fmt(span['src_end_ms'])} · "
           f"{label(span.get('cue', 'editor'), 'ar', span.get('cue_text'))}")
    return out + (f" · {GUESSED_AR}" if span.get("guessed_end") else "")


# --------------------------------------------------------------------------- configuration
def config(profile: dict | None) -> dict:
    """{"religious", "phrases" (token lists), "warnings"}. The lexicon is read only for a religious client; a lexicon
    that cannot be read leaves the cue class and one warning."""
    prof = profile if isinstance(profile, dict) else {}
    religious = False
    try:
        from .review_domains import client_set
        religious = "religious" in client_set(prof)
    except Exception:  # noqa: BLE001 — a profile the registry refuses: the legacy `domain` still says it
        religious = str(prof.get("domain") or "").strip().lower() == "religious"
    out = {"religious": religious, "phrases": [], "warnings": []}
    if not religious:
        return out
    try:
        from .review_domains import lexicon
        rules = lexicon("religious").get("rules") or []
        terms = next((r.get("terms") or [] for r in rules if isinstance(r, dict) and r.get("id") == "verse-phrase"), [])
        out["phrases"] = [t for t in (tokens(x) for x in terms if isinstance(x, str)) if t]
    except Exception:  # noqa: BLE001
        out["warnings"].append("the religious verse-phrase list could not be read: recited verses are found from "
                               "«قال تعالى» and its kind, the basmala and the isti'adha only — fix config/review-domains")
    return out


# --------------------------------------------------------------------------- detection
def _good(w) -> bool:
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(w, dict) and isinstance(w.get("word"), str) and num(w.get("start_ms")) and num(w.get("end_ms"))


def _stream(words: list) -> list[tuple[str, int]]:
    """(token, word index) for every token of every word, in order."""
    return [(t, i) for i, w in enumerate(words) for t in tokens(w["word"])]


def _match(stream: list, k: int, phrase: list, first_prefix=PREFIXES, every=False) -> bool:
    if k + len(phrase) > len(stream):
        return False
    for j, want in enumerate(phrase):
        tok = stream[k + j][0]
        ok = tok == want or ((j == 0 or every) and want in _cands(tok, _JOINED if every else first_prefix))
        if not ok:
            return False
    return True


def _tok(stream: list, j: int) -> str:
    return stream[j][0] if j < len(stream) else ""


def _honor_len(stream: list, j: int) -> int:
    """The honorific group at token j: «تعالى»; «سبحانه / عز / جل» with an optional second word («وتعالى», «وجل»,
    «وعلا», «جلاله», «شأنه»); «تبارك» only as «تبارك وتعالى». 0 = none."""
    here, nxt = _cands(_tok(stream, j), PREFIXES), _cands(_tok(stream, j + 1), PREFIXES)
    if "تعالي" in here:
        return 1
    if here & HEADS:
        return 2 if nxt & TAILS else 1
    if "تبارك" in here and "تعالي" in nxt:
        return 2
    return 0


def _name_len(stream: list, j: int) -> int:
    """The divine name at token j: «الله», «ربنا», «المولى»; «الحق» before an honorific; «رب العزة / العالمين»."""
    tok = _tok(stream, j)
    if tok in DIVINE:
        return 1
    if tok in WITH_HONOR and _honor_len(stream, j + 1):
        return 1
    if tok == "رب" and _tok(stream, j + 1) in RABB_OF:
        return 2
    return 0


def _dua(tok: str) -> bool:
    return any(tok.startswith(s) and tok[len(s):] in DUA_ENDS for s in DUA)


def _say_cue(stream: list, k: int) -> int:
    """How many tokens of a citation cue start at token k (0 = none): a verb, ONE name right after it, ONE honorific
    group after the name or the verb, optionally «في كتابه الكريم». Whatever follows opens the span, so a verse that
    starts with a name or «تبارك» is never taken into the cue (fix round 2, P1-1). A verb followed directly by
    «تبارك» (not «تبارك وتعالى») is a cue of the verb alone and the span starts AT «تبارك»."""
    n = len(stream)
    if not _cands(stream[k][0], PREFIXES) & VERBS:
        return 0
    j = k + 1
    name = _name_len(stream, j)
    honor = _honor_len(stream, j + name)
    if name and not honor and _dua(_tok(stream, j + name)):
        return 0                                         # «قال الله يرحمه», «قال ربنا يستر»
    if not (name or honor or "تبارك" in _cands(_tok(stream, j), PREFIXES)):
        return 0
    j += name + honor
    if j + 1 < n and stream[j][0] == "في" and stream[j + 1][0] in BOOK:
        j += 2
        while j < n and stream[j][0] in BOOK_TAIL:
            j += 1
    return j - k


def _phrase_end(words: list, j: int, start: float) -> tuple[float, str, bool]:
    """From word j: the end of the recited phrase: the first pause >= PAUSE_MS, a change of speaker or the end of
    the speech. Past CAP_MS the end is a guess and the search goes on to the next pause; past HARD_MS it also ends at
    the end of a sentence (a closing mark on a word)."""
    n, i, capped = len(words), j, False
    while True:
        end = float(words[i]["end_ms"])
        if end - start > CAP_MS:
            capped = True
        if i + 1 >= n:
            return end, "speech_end", capped
        if words[i + 1]["start_ms"] - words[i]["end_ms"] >= PAUSE_MS:
            return end, "cap_pause" if capped else "pause", capped
        if words[i + 1].get("speaker") != words[i].get("speaker"):
            return end, "cap_turn" if capped else "turn", capped
        if capped and end - start > HARD_MS and _SENTENCE.search(str(words[i]["word"])):
            return end, "cap_sentence", True
        i += 1


def detect(words: list, cfg: dict | None) -> list[dict]:
    """Recited-verse spans on the source clock, sorted and merged."""
    cfg = cfg or {}
    words = sorted((w for w in words or [] if _good(w)), key=lambda w: w["start_ms"])
    stream = _stream(words)
    recited = [(cid, tokens(ph)) for cid, ph in RECITED]
    phrases = (cfg.get("phrases") or []) if cfg.get("religious") else []
    spans = []
    k = 0
    while k < len(stream):
        rec = next(((cid, ph) for cid, ph in recited if _match(stream, k, ph)), None)
        size = len(rec[1]) if rec else _say_cue(stream, k)
        if size:
            first_w, last_w = stream[k][1], stream[k + size - 1][1]
            nxt = last_w + 1
            cue = {"cue": rec[0] if rec else "say", "source": "detected"}
            if not rec:
                cue["cue_text"] = " ".join(x for x in (_plain(words[i]["word"]) for i in range(first_w, last_w + 1)) if x)
            if nxt < len(words):
                start = words[first_w]["start_ms"] if rec else words[nxt]["start_ms"]
                end, why, guessed = _phrase_end(words, nxt, start)
                spans.append(dict(cue, src_start_ms=int(start), src_end_ms=int(round(end)), end=why,
                                  guessed_end=guessed))
            elif rec:                                   # the clip ends on the recited cue: the cue itself
                spans.append(dict(cue, src_start_ms=int(words[first_w]["start_ms"]),
                                  src_end_ms=int(words[last_w]["end_ms"]), end="speech_end", guessed_end=False))
            k += size
            continue
        ph = next((p for p in phrases if p and _match(stream, k, p, every=True)), None)
        if ph:
            a, b = words[stream[k][1]], words[stream[k + len(ph) - 1][1]]
            spans.append({"src_start_ms": int(a["start_ms"]), "src_end_ms": int(b["end_ms"]), "cue": "verse_phrase",
                          "end": "phrase", "guessed_end": False, "source": "detected"})
            k += len(ph)
            continue
        k += 1
    return _merge(spans)


def _merge(spans: list) -> list:
    out = []
    for s in sorted(spans, key=lambda s: (s["src_start_ms"], -s["src_end_ms"])):
        if out and s["src_start_ms"] <= out[-1]["src_end_ms"]:
            last = out[-1]
            if s["src_end_ms"] > last["src_end_ms"]:
                last.update(src_end_ms=s["src_end_ms"], end=s["end"], guessed_end=s["guessed_end"])
            continue
        out.append(dict(s))
    return out


def strip_recited(text: str) -> tuple[str, bool]:
    """`text` without the basmala / isti'adha words it holds (a hook title that quotes them), and whether any went."""
    words = str(text or "").split()
    stream = [(t, i) for i, w in enumerate(words) for t in tokens(w)]
    recited = [tokens(p) for _c, p in RECITED]
    drop, k = set(), 0
    while k < len(stream):
        ph = next((p for p in recited if _match(stream, k, p)), None)
        if ph:
            drop |= {stream[k + x][1] for x in range(len(ph))}
            k += len(ph)
            continue
        k += 1
    if not drop:
        return text, False
    return " ".join(w for i, w in enumerate(words) if i not in drop).strip(" ،,.:-—"), True


def reel_spans(root, episode_id: str) -> list:
    """The verse ranges the episode's reels recorded in their plans (the story-editor's spans included), on the
    episode's clock: every reel whose 00_inputs/source.json names this episode, its spec's manual_verse, verse_cut and
    verse_hold ranges shifted by its source_in_ms. Unreadable plans are skipped. [] when none."""
    import json
    from pathlib import Path
    out = []
    proj = Path(root) / "output" / "projects"
    if not proj.is_dir():
        return out
    for d in sorted(proj.iterdir()):
        try:
            src = json.loads((d / "00_inputs/source.json").read_text(encoding="utf-8-sig"))
            if not (isinstance(src, dict) and src.get("episode_id") == episode_id):
                continue
            spec = json.loads((d / "01_analysis/timeline-spec.json").read_text(encoding="utf-8-sig"))
            off = int(spec.get("source_in_ms") or src.get("in_ms") or 0)
            held_ = [h for h in spec.get("verse_hold") or [] if isinstance(h, dict) and not h.get("released")]
            for s in (spec.get("manual_verse") or []) + (spec.get("verse_cut") or []) + held_:
                out.append((int(s["src_start_ms"]) + off, int(s["src_end_ms"]) + off))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    return out


# --------------------------------------------------------------------------- the story-editor's overrides
def _ms(v):
    from .media_util import parse_time
    try:
        return parse_time(v, int_is_ms=True)
    except (TypeError, ValueError):
        return None


def _entries(ed: dict, key: str, errors: list) -> list:
    raw = ed.get(key) if isinstance(ed, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append(f"{key} must be a list of {{start_ms, end_ms}} (edit-decisions.json)")
        return []
    out = []
    for n, e in enumerate(raw):
        a = _ms(e.get("start_ms")) if isinstance(e, dict) else None
        b = _ms(e.get("end_ms")) if isinstance(e, dict) else None
        if a is None or b is None or b <= a or a < 0:
            errors.append(f"{key}[{n}]: start_ms and end_ms must be times with end after start "
                          "(milliseconds such as 12500, or a clock such as 00:00:12.500)")
            continue
        out.append((int(a), int(b), e))
    return out


def resolve(detected: list, ed: dict | None) -> tuple[list, list, list]:
    """(spans, errors, warnings): the detected spans minus `manual_verse_off`, with `manual_verse` added (the editor's
    span replaces a detected one it overlaps), sorted, ids MV01 …"""
    errors, warnings = [], []
    ed = ed if isinstance(ed, dict) else {}
    off = _entries(ed, "manual_verse_off", errors)
    add = _entries(ed, "manual_verse", errors)
    spans = [dict(s) for s in detected or []]
    for a, b, _e in off:
        hit = [s for s in spans if s["src_start_ms"] < b and a < s["src_end_ms"]]
        if not hit:
            warnings.append(f"manual_verse_off {_fmt(a)}–{_fmt(b)} matches no detected verse: nothing removed")
        spans = [s for s in spans if s not in hit]
    for a, b, e in add:
        spans = [s for s in spans if not (s["src_start_ms"] < b and a < s["src_end_ms"])]
    for a, b, e in add:
        s = {"src_start_ms": a, "src_end_ms": b, "cue": "editor", "end": "editor", "guessed_end": False,
             "source": "editor"}
        if isinstance(e.get("note"), str) and e["note"].strip():
            s["note"] = e["note"].strip()[:300]
        spans.append(s)
    spans.sort(key=lambda s: (s["src_start_ms"], s["src_end_ms"]))
    for i, s in enumerate(spans, 1):
        s["id"] = f"MV{i:02d}"
    return spans, errors, warnings


# --------------------------------------------------------------------------- the hold after a span (P2-1)
def holds(spans: list, words: list) -> list:
    """The caption runs held after the detected spans that end on a pause (`pause`, `cap_pause`): a reciter stops at
    a waqf, so the verse may go on. A run starts at the first word after the span and ends at the first word that
    closes a sentence, before a change of speaker, at the speech end, or with the last word starting within HOLD_MS.
    The editor's spans and verse phrases have a known end: no hold.
    [{id, after (the span's id), src_start_ms, src_end_ms, end (why it ends), released: False}]."""
    good = sorted((w for w in words or [] if _good(w)), key=lambda w: w["start_ms"])
    out = []
    for k, s in enumerate(spans or [], 1):
        if s.get("source") != "detected" or s.get("end") not in ("pause", "cap_pause"):
            continue
        i = next((x for x, w in enumerate(good) if w["start_ms"] >= s["src_end_ms"]), None)
        if i is None:
            continue
        start = good[i]["start_ms"]
        while True:
            w = good[i]
            if _SENTENCE.search(str(w["word"])):
                why = "sentence"
            elif i + 1 >= len(good):
                why = "speech_end"
            elif good[i + 1].get("speaker") != w.get("speaker"):
                why = "turn"
            elif good[i + 1]["start_ms"] - start >= HOLD_MS:
                why = "time"
            else:
                i += 1
                continue
            break
        sid = s.get("id") or f"MV{k:02d}"
        out.append({"id": f"{sid}H", "after": sid, "src_start_ms": int(start), "src_end_ms": int(round(w["end_ms"])),
                    "end": why, "released": False})
    return out


def held(spans: list, words: list, ed: dict | None) -> tuple[list, list, list]:
    """(holds, errors, warnings): `holds` with `released: True` on the runs the editor released
    (`manual_verse_release: [{start_ms, end_ms}]` in edit-decisions.json: each entry releases the held runs it
    overlaps; the plan runs again). A released run is listed, never blanked."""
    errors, warnings = [], []
    out = holds(spans, words)
    for a, b, _e in _entries(ed if isinstance(ed, dict) else {}, "manual_verse_release", errors):
        hit = [h for h in out if h["src_start_ms"] < b and a < h["src_end_ms"]]
        if not hit:
            warnings.append(f"manual_verse_release {_fmt(a)}–{_fmt(b)} matches no held caption run: nothing released")
        for h in hit:
            h["released"] = True
    return out, errors, warnings


def hold_comment(h: dict) -> str:
    """The hold marker's comment: the run's SOURCE timecodes and the span it follows, never a word."""
    return (f"المصدر {_fmt(h['src_start_ms'])}–{_fmt(h['src_end_ms'])} · بعد {h['after']}: الكابشن متوقف هنا. اسمع: لو "
            f"الآية مكمّلة ضيفها بإيدك، ولو لأ رجّع الكابشن (manual_verse_release)")


# --------------------------------------------------------------------------- applying the spans
def overlaps(a: float, b: float, ranges) -> bool:
    return any(a < z and r < b for r, z in ranges)


def in_span(w: dict, ranges) -> bool:
    """A word overlapping a span (source or sequence clock, as the ranges are)."""
    return overlaps(w["start_ms"], w["end_ms"], ranges)


def span_words(spans: list, words: list) -> list[list[str]]:
    """Per span, its words' tokens in order (to recognise a graphic or copy that repeats them; never shown)."""
    good = [w for w in words or [] if _good(w)]
    out = []
    for s in spans:
        rng = [(s["src_start_ms"], s["src_end_ms"])]
        toks = [t for w in sorted(good, key=lambda w: w["start_ms"]) if in_span(w, rng) for t in tokens(w["word"])]
        if toks:
            out.append(toks)
    return out


def repeats(text, seqs: list, n: int = RUN) -> bool:
    """True when `text` holds `n` words in a row of a span (the whole span when it is shorter)."""
    t = [_cands(x, PREFIXES) for x in tokens(text)]
    for seq in seqs or []:
        need = min(n, len(seq))
        if not need:
            continue
        for i in range(len(seq) - need + 1):
            win = seq[i:i + need]
            for k in range(len(t) - need + 1):
                if all(win[x] in t[k + x] for x in range(need)):
                    return True
    return False


def keep_piece(s: float, e: float, ranges) -> tuple | None:
    """A graphic's [s, e) with the spans taken out: unchanged when it overlaps none; else the first remaining piece of
    at least MIN_LEFT_MS (the part before the verse first); None when no such piece is left."""
    if not overlaps(s, e, ranges):
        return s, e
    pieces = [(s, e)]
    for r, z in sorted(ranges):
        nxt = []
        for a, b in pieces:
            if z <= a or r >= b:
                nxt.append((a, b))
                continue
            if r > a:
                nxt.append((a, r))
            if z < b:
                nxt.append((z, b))
        pieces = nxt
    return next(((a, b) for a, b in pieces if b - a >= MIN_LEFT_MS), None)


def filter_cues(cues: list, ranges, words: list) -> list:
    """Caption cues with nothing inside the spans: a cue outside every span stays as written; a cue inside one goes;
    a cue across an edge keeps, per remaining part, the words whose middle falls in that part (never a placeholder).
    `words` and `ranges` are on the cues' clock."""
    ranges = sorted((float(a), float(b)) for a, b in ranges)
    good = sorted((w for w in words or [] if _good(w)), key=lambda w: w["start_ms"])
    out = []
    for c in cues or []:
        s, e = c["start_ms"], c["end_ms"]
        if not overlaps(s, e, ranges):
            out.append(c)
            continue
        parts, cur = [], [(s, e)]
        for r, z in ranges:
            nxt = []
            for a, b in cur:
                if z <= a or r >= b:
                    nxt.append((a, b))
                    continue
                if r > a:
                    nxt.append((a, r))
                if z < b:
                    nxt.append((z, b))
            cur = nxt
        parts = cur
        for a, b in parts:
            ws = [w["word"] for w in good if not in_span(w, ranges)
                  and a <= (w["start_ms"] + w["end_ms"]) / 2 < b]
            text = " ".join(x.strip() for x in ws if x.strip())
            if text:
                out.append({"start_ms": int(round(a)), "end_ms": int(round(b)), "text": text})
    return out
