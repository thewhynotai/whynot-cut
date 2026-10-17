# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Cut proposals v2 (Phase 4 Task 25, R-4.3): pauses, retakes, false starts, fillers and repeated words, proposed for
the editor and never applied on their own.

`propose(paths)` reads the reviewed words (02_transcription/words.json), the audio pause map
(06_audio/dialogue/pauses.json), the client's settings (config/defaults/cut-proposals.json <- profile <- reel-profile)
and the plan inputs that protect words (edit-decisions.json: scene quotes, caption highlights, B-roll anchors, the
editor's sign-off marker; profile.json endings.sign_off), and writes 01_analysis/cut-proposals.json. The same input
gives the same file, byte for byte.

Nothing is cut here. `accept(paths, ids)` copies the chosen word proposals into edit-decisions.json `global.cut_words`
(the plan's own cut list), which changes the plan: `reel plan` recompiles it and the editor approves it again before
anything is built. Pause proposals are the pause map the plan already applies with `remove_pauses`.

Rules (R-4.3 "Our version"; every number is a starting value of ours with its basis in the config):
- text is compared with the one shared normaliser (cut_proposals_norm.py; digits of any script are the same digit);
- retakes: word runs (2–12 words) inside a 20 s window, similarity = (Jaccard + longest common subsequence / run
  length) / 2 ≥ 0.65 with ≥ 2 shared content words; the better take is kept (complete, higher confidence, no filler;
  a tie keeps the later); an exact short repeat that is complete both times is emphasis, never proposed;
- false starts: a short or unsure cut-off word restarted within 400 ms;
- fillers: pure hesitation sounds always; «امم» only stretched; context words («يعني», «بص», «طب», «إيه», «اه», "like",
  "so", "you know") only stretched, with a pause of 250 ms on both sides, not before a question or a sentence end;
  bare «اه» is a real "yes": soft (left unticked); written laughter («هه») is never a filler; "er" only in English;
- repeated words: the same word twice in a row, one proposed (never an intensifier or a negation said twice);
- protected, never proposed: the sign-off and everything after it (or the last 8 s when the profile expects one that
  is not found), scene quotes, caption highlights, drug and product names, B-roll anchors, speaker changes, and any cut
  that would leave a kept piece shorter than 300 ms."""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import unicodedata
from pathlib import Path

from . import cut_proposals_norm as N
from .safety.differences import compare as compare_takes, describe as describe_differences

FILE = "01_analysis/cut-proposals.json"
SCHEMA = 1
KINDS = ("pause", "retake", "false_start", "filler", "repeat_word")
WORD_KINDS = ("retake", "false_start", "filler", "repeat_word")

# every number: a starting value of ours (R-4.3 "Basis for every threshold"); the config may replace it with a
# measured one and says so in its basis
DEFAULTS = {
    "retake_window_s": 20, "retake_min_words": 2, "retake_max_words": 12, "retake_score": 0.65,
    "retake_min_shared": 2, "complete_pause_ms": 350, "pad_ms": 40,
    "false_start_restart_ms": 400, "false_start_max_ms": 250, "false_start_max_p": 0.6,
    "stretch_factor": 1.6, "stretch_min_ms": 350, "context_pause_ms": 250, "unsure_p": 0.6,
    "min_kept_ms": 300, "sign_off_search_s": 20, "sign_off_fallback_s": 8, "keep_below": 0.6,
    "repeat_max_gap_ms": 600, "snap_ms": 50, "snap_frame_ms": 10,
    "emphasis_max_content": 3, "fragment_min_letters": 3,
    # confidence of each kind (with keep_below, they decide what is ticked by default)
    "conf_always_filler": 0.9, "conf_context_filler": 0.7, "conf_unsure_bonus": 0.1, "conf_false_start": 0.75,
    "conf_repeat_word": 0.85, "conf_retake_base": 0.55, "conf_retake_per_similarity": 0.4, "conf_pause": 0.9,
    "conf_on_purpose": 0.5,
}
FILLERS = {
    "always": [r"م{3,}", r"ام{3,}", r"ا{2,}ه+", r"ه+م{2,}", r"um+", r"u+h+", r"erm+", r"hm+", r"m{3,}"],
    "always_en": [r"e+r+"],
    "stretched_only": ["امم"],
    "context": ["ايه", "اه", "يعني", "بص", "طب", "ف", "like", "so", "you know"],
    "soft": ["اه"],
}
# whole words that also start longer words («كان» / «كانت», "the" / "there"): never a cut-off fragment by spelling
_COMMON_PREFIX_WORDS = {"كان", "كنت", "اللي", "عشان", "بعد", "قبل", "كل", "هو", "هي", "انا", "انت", "احنا", "ده", "دي",
                        "مش", "علي", "على", "عند", "the", "and", "for", "you", "can", "not", "but", "his", "her", "our",
                        "out", "all", "any", "one", "two", "she", "they", "them", "then", "this", "that", "with", "some",
                        "more", "over", "under", "every", "after", "before", "work", "take", "make", "help", "use"}
_ARABIC = re.compile("[؀-ۿ]")
LAUGHTER = re.compile(r"ه{2,}|(ha){2,}h?|(he){2,}|lo+l")
EMPHASIS = {"جدا", "خالص", "اوي", "قوي", "ابدا", "لا", "مش", "اه", "ايوه", "very", "really", "no", "never", "so", "yes"}
STOP = {"و", "في", "من", "على", "علي", "عن", "ال", "ان", "إن", "ده", "دي", "هو", "هي", "انا", "احنا", "اللي", "ما",
        "يا", "the", "a", "an", "of", "to", "in", "and", "is", "it", "i", "you", "that", "this"}
_DIGITS = str.maketrans({**{chr(0x660 + i): str(i) for i in range(10)}, **{chr(0x6F0 + i): str(i) for i in range(10)}})
_SENT_END = re.compile(r"[.!?؟…]\s*$")
_QUESTION = re.compile(r"[?؟]\s*$")

LABEL = {"pause": ("سكتة", "pause"), "retake": ("إعادة", "retake"), "false_start": ("بداية مقطوعة", "false start"),
         "filler": ("حشو", "filler"), "repeat_word": ("كلمة متكررة", "repeated word")}


# --- settings ----------------------------------------------------------------------------------------------------------
def settings(ctx=None) -> dict:
    """{"values", "basis", "fillers"} from config/defaults/cut-proposals.json (+ profile, reel-profile). A value that
    is not a plain number falls back to the starting default; a damaged file means the defaults (G10)."""
    from .common import load_config
    try:
        cfg = load_config("cut-proposals.json", ctx)
    except Exception:  # noqa: BLE001
        cfg = {}
    cfg = cfg if isinstance(cfg, dict) else {}
    vals, basis = dict(DEFAULTS), {k: "starting" for k in DEFAULTS}
    for k, v in (cfg.get("thresholds") or {}).items() if isinstance(cfg.get("thresholds"), dict) else []:
        val = v.get("value") if isinstance(v, dict) else v
        if k in DEFAULTS and isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 0:
            vals[k] = val
            basis[k] = str(v.get("basis") or "config") if isinstance(v, dict) else "config"
    fill = {k: list(v) for k, v in FILLERS.items()}
    over = cfg.get("fillers")
    if isinstance(over, dict):
        for k, v in over.items():
            if k in fill and isinstance(v, list) and all(isinstance(x, str) for x in v):
                fill[k] = list(v)
    return {"values": vals, "basis": basis, "fillers": fill}


# --- text --------------------------------------------------------------------------------------------------------------
def norm_word(word) -> str:
    """One word in compared form: the shared normaliser's tokens joined, digits of any script as Western digits."""
    return " ".join(N.normalize(unicodedata.normalize("NFKC", str(word or "")).translate(_DIGITS)))


def _content(tok: str, fill: dict) -> bool:
    return bool(tok) and tok not in STOP and tok not in EMPHASIS and tok not in fill["context"] and not _always(tok, fill, "en") \
        and len(tok) > 1


def _always(tok: str, fill: dict, lang: str) -> bool:
    pats = list(fill["always"]) + (list(fill["always_en"]) if lang == "en" else [])
    return any(re.fullmatch(p, tok) for p in pats)


def _says_number(ws: list) -> bool:
    """A number or a dose is said in these words (digits of any script, spelled, a dual «حبايتين», an everyday number
    word beside a unit «حباية واحدة»; «واحد» "someone" alone is not)."""
    from .safety.numbers import find_numbers, fold, quantities
    toks = [fold(w["word"]) for w in ws]
    return any(not n["ambiguous"] for n in find_numbers(toks)) or bool(quantities(toks))


def _holds_number(*raw: str) -> bool:
    """Any of these words is or holds a number, an everyday number word included («خمس» before «خمسمية»)."""
    from .safety.numbers import find_numbers, fold
    return any(find_numbers([fold(w)]) or re.search(r"\d", norm_word(w)) for w in raw)


def _never_filler(raw: str) -> bool:
    """A word written with «ة» or as «آي…» is a real word («آية», a verse), never «إيه» or another filler: checked
    before the shared normaliser folds ة into ه."""
    bare = re.sub("[\u064b-\u065f\u0670\u0640]", "", unicodedata.normalize("NFC", str(raw or "")))
    return "ة" in bare or bare.startswith("آي")


def _lcs(a: list, b: list) -> int:
    dp = [0] * (len(b) + 1)
    for x in a:
        prev = 0
        for j, y in enumerate(b, 1):
            cur = dp[j]
            dp[j] = prev + 1 if x == y else max(dp[j], dp[j - 1])
            prev = cur
    return dp[-1]


def similarity(a: list, b: list) -> float:
    """(Jaccard on the token sets + longest common subsequence / the longer run) / 2."""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return (len(sa & sb) / len(sa | sb) + _lcs(a, b) / max(len(a), len(b))) / 2


# --- the engine (pure) -------------------------------------------------------------------------------------------------
def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def clean_words(words) -> list:
    """Usable word records, in time order: an id, a word, start_ms <= end_ms."""
    out = []
    for w in words or []:
        if not isinstance(w, dict) or not isinstance(w.get("word"), str) or not w["word"].strip():
            continue
        s, e = _num(w.get("start_ms")), _num(w.get("end_ms"))
        if s is None or e is None or e < s or w.get("id") is None:
            continue
        out.append(w)
    return sorted(out, key=lambda w: (w["start_ms"], str(w["id"])))


def compute(words, pauses=None, *, cfg: dict | None = None, lang: str = "ar", protect: dict | None = None,
            samples=None, sr: int = 0, media_end_ms=None) -> dict:
    """{"proposals": [...], "notes": [(ar, en)]} for clean words. protect: {"word_ids": set, "spans": [[a, b]],
    "anchors": [ms], "after_ms": ms | None}. Deterministic."""
    cfg = cfg or {"values": dict(DEFAULTS), "fillers": {k: list(v) for k, v in FILLERS.items()}}
    V, F = cfg["values"], cfg["fillers"]
    protect = protect or {}
    ws = clean_words(words)
    notes = []
    if not ws:
        notes.append(("مفيش كلام في التفريغ، فمفيش أي اقتراح قص.", "No speech in the transcript, so no cut is proposed."))
        return {"proposals": [], "notes": notes}
    toks = [norm_word(w["word"]) for w in ws]
    n = len(ws)

    def gap_before(i):
        return ws[i]["start_ms"] - ws[i - 1]["end_ms"] if i > 0 else float("inf")

    def gap_after(i):
        return ws[i + 1]["start_ms"] - ws[i]["end_ms"] if i + 1 < n else float("inf")

    def sentence_end(i):
        return bool(_SENT_END.search(ws[i]["word"])) or gap_after(i) >= V["complete_pause_ms"] or i == n - 1 or \
            ws[i].get("segment_id") != ws[i + 1].get("segment_id")

    def prob(i):
        p = _num(ws[i].get("probability"))
        return 1.0 if p is None else p

    # stretched: longer than stretch_factor x the median of words with the same letter count (same speaker)
    med = {}
    for i, t in enumerate(toks):
        med.setdefault((len(t.replace(" ", "")), ws[i].get("speaker")), []).append(ws[i]["end_ms"] - ws[i]["start_ms"])
    med = {k: statistics.median(v) for k, v in med.items()}

    all_med = statistics.median(w["end_ms"] - w["start_ms"] for w in ws)

    def stretched(i):
        """Longer than stretch_factor x the median of the clip's words with the same letter count (same speaker); a
        word with no such peer («اه», «طب» in a short clip) is compared with the median of all its words."""
        d = ws[i]["end_ms"] - ws[i]["start_ms"]
        size = len(toks[i].replace(" ", ""))
        peers = sum(1 for t in toks if len(t.replace(" ", "")) == size) > 1
        m = med.get((size, ws[i].get("speaker")), d) if peers else all_med
        return d >= V["stretch_min_ms"] and d >= V["stretch_factor"] * m

    def phrase_only_word(i):
        """The whole of a written phrase («اه.» answering a question): punctuation on both sides (a pause alone does
        not make a phrase: a stretched «يعني» between two pauses is the filler itself)."""
        return (i == 0 or bool(_SENT_END.search(ws[i - 1]["word"]))) and bool(_SENT_END.search(ws[i]["word"]))

    pid = protect.get("word_ids") or set()
    props = []

    def span(a, b):
        """[start, end] ms of words a..b (inclusive): from just before the first word (never into the previous word)
        to just before the next word, so the breath after the take goes with it."""
        start = max(ws[a]["start_ms"] - V["pad_ms"], ws[a - 1]["end_ms"] if a > 0 else 0)
        end = max(ws[b]["end_ms"], (ws[b + 1]["start_ms"] - V["pad_ms"]) if b + 1 < n else ws[b]["end_ms"])
        return int(start), int(end)

    def add(kind, a, b, conf, ar, en, default=None, extra=None):
        s, e = span(a, b)
        p = {"kind": kind, "start_ms": s, "end_ms": e, "word_ids": [ws[k]["id"] for k in range(a, b + 1)],
             "words": [ws[k]["word"].strip() for k in range(a, b + 1)], "confidence": round(min(conf, 0.99), 2),
             "reason": ar, "reason_en": en,
             "default": default or ("proposed" if conf >= V["keep_below"] else "keep"),
             # where a snapped edge may go: never into the word before or after
             "_bounds": (ws[a - 1]["end_ms"] if a > 0 else 0, ws[a]["start_ms"], ws[b]["end_ms"],
                         ws[b + 1]["start_ms"] if b + 1 < n else ws[b]["end_ms"] + V["snap_ms"])}
        p.update(extra or {})
        props.append(p)

    def one_speaker(x, lx):
        return len({ws[k].get("speaker") for k in range(x, x + lx)}) == 1

    # retakes ------------------------------------------------------------------------------------------------------
    used = set()
    lo, hi = int(V["retake_min_words"]), int(V["retake_max_words"])
    for a in range(n):
        if a in used or not _content(toks[a], F) and toks[a] not in STOP:
            continue
        best = None
        for la in range(lo, min(hi, n - a) + 1):
            if la > 1 and sentence_end(a + la - 2):
                break                          # a take never runs across a sentence end or a long pause
            if any(k in used for k in range(a, a + la)):
                break
            A = toks[a:a + la]
            sa = {t for t in A if _content(t, F)}
            if len(sa) < V["retake_min_shared"]:
                continue
            heads = set(A[:2])
            for b in range(a + la, n):
                if ws[b]["start_ms"] - ws[a]["start_ms"] > V["retake_window_s"] * 1000:
                    break
                if toks[b] not in heads:       # a retake starts again from the same words
                    continue
                for lb in (la, la + 1, la - 1):
                    if lb < lo or b + lb > n:
                        continue
                    # an interviewer echoing the guest is no retake: both takes are one speaker's
                    if not one_speaker(a, la) or not one_speaker(b, lb) or \
                            ws[a].get("speaker") != ws[b].get("speaker"):
                        continue
                    B = toks[b:b + lb]
                    if len(sa & set(B)) < V["retake_min_shared"]:
                        continue
                    sc = similarity(A, B)
                    if sc >= V["retake_score"] and (best is None or (sc, la) > (best[0], best[2])):
                        best = (sc, a, la, b, lb)
        if not best:
            continue
        sc, a, la, b, lb = best
        A, B = toks[a:a + la], toks[b:b + lb]
        # emphasis: the end of a sentence said again straight away, complete both times («مهم جدا. مهم جدا.»)
        emphasis = len([t for t in B if _content(t, F)]) <= V["emphasis_max_content"]
        if b == a + la and A[-len(B):] == B and emphasis and sentence_end(a + la - 1) and sentence_end(b + lb - 1):
            continue

        # the earlier take runs on to where it was abandoned («أول حاجة لازم تعرفي …»), never into the later take
        e = a + la - 1
        while e < b - 1 and not sentence_end(e):
            e += 1
        la = e - a + 1
        A = toks[a:a + la]
        # the later take runs on to its sentence end («أول حاجة لازم تعرفيها كويس.»): judge it whole
        e = b + lb - 1
        while e < min(n - 1, b + hi - 1) and not sentence_end(e):
            e += 1
        lb = e - b + 1
        B = toks[b:b + lb]

        def quality(x, lx, other):
            # a sentence the transcript closed («.», «؟») beats one that only stops at a pause
            complete = 2 if _SENT_END.search(ws[x + lx - 1]["word"]) else int(sentence_end(x + lx - 1))
            mine = {t for t in toks[x:x + lx] if _content(t, F)}
            theirs = {t for t in other if _content(t, F)}
            cover = round(len(mine & theirs) / max(1, len(theirs)), 3)
            conf = statistics.mean(prob(k) for k in range(x, x + lx))
            fillers = sum(1 for k in range(x, x + lx) if _always(toks[k], F, lang))   # hesitation sounds only
            return (complete, cover, -fillers, round(conf, 3))
        qa, qb = quality(a, la, B), quality(b, lb, A)
        drop, keep = ((a, la), (b, lb)) if qb >= qa else ((b, lb), (a, la))
        conf = V["conf_retake_base"] + V["conf_retake_per_similarity"] * sc
        if A == B and qa[0] and qb[0]:
            conf = min(conf, V["conf_on_purpose"])     # said twice, complete both times: maybe on purpose
        has_number = _says_number(ws[drop[0]:drop[0] + drop[1]])
        if has_number:
            conf = min(conf, V["conf_on_purpose"])     # a dose or a number said again is often said on purpose
        # the two takes differ in a negation, a number or dose, or a timing word: the editor hears both and chooses.
        # Each take is read with the rest of its sentence («it doesn't lower | the blood pressure»), never with the
        # other take's words.
        def sentence_of(x, lx, other):
            lo_, hi_ = x, x + lx - 1
            while lo_ > 0 and not sentence_end(lo_ - 1) and not other[0] <= lo_ - 1 < other[0] + other[1]:
                lo_ -= 1
            while hi_ < n - 1 and not sentence_end(hi_) and not other[0] <= hi_ + 1 < other[0] + other[1]:
                hi_ += 1
            return [ws[k]["word"] for k in range(lo_, hi_ + 1)]
        differs = compare_takes(sentence_of(drop[0], drop[1], keep), sentence_of(keep[0], keep[1], drop))
        kept_text = " ".join(ws[k]["word"].strip() for k in range(keep[0], keep[0] + keep[1]))
        number_ar = "؛ بس فيها رقم أو جرعة، فسايبينها لحد ما تسمعها" if has_number else ""
        number_en = "; it holds a number or a dose, so it is left unticked" if has_number else ""
        later = keep[0] > drop[0]
        ar = ("اتقالت الجملة مرتين؛ نشيل " + ("الأولى ونسيب التانية لأنها أكمل وأوضح" if later else
                                              "التانية ونسيب الأولى لأنها أكمل وأوضح") + f": «{kept_text}»")
        en = (f"said twice; drop the {'first' if later else 'second'} take, keep the "
              f"{'later' if later else 'earlier'} one (more complete, clearer): \"{kept_text}\"")
        ks, ke = span(keep[0], keep[0] + keep[1] - 1)
        # a later take dropped from the middle of its sentence would leave a broken line: shown, never ticked
        mid = drop[0] > keep[0] and drop[0] > 0 and not sentence_end(drop[0] - 1)
        if mid:
            number_ar += "؛ بس الجزء ده بيبدأ من نص جملة، فسايبينه لحد ما تسمعه"
            number_en += "; it starts mid-sentence, so it is left unticked"
            conf = min(conf, V["conf_on_purpose"])
        extra = {"keep": {"start_ms": ks, "end_ms": ke, "word_ids": [ws[k]["id"] for k in range(keep[0], keep[0] + keep[1])]},
                 "similarity": round(sc, 2)}
        if differs:
            d_ar, d_en = describe_differences(differs)
            number_ar += f"؛ بس الإعادتين مختلفين في المعنى ({d_ar})، فسايبينها لحد ما تسمعهم وتختار"
            number_en += f"; but the two takes differ in meaning ({d_en}), so it is left unticked for you to choose"
            conf = min(conf, V["conf_on_purpose"])
            extra["differs"] = differs
        add("retake", drop[0], drop[0] + drop[1] - 1, conf, ar + number_ar, en + number_en,
            default="keep" if differs or mid else None, extra=extra)
        used.update(range(a, a + la))
        used.update(range(b, b + lb))

    # false starts ----------------------------------------------------------------------------------------------------
    for i in range(n - 1):
        t, nx = toks[i], toks[i + 1]
        if i in used or not t or len(t) < 2 or not nx.startswith(t) or nx == t:
            continue
        short = ws[i]["end_ms"] - ws[i]["start_ms"] <= V["false_start_max_ms"]
        # a fragment that is no word of its own and a real start of the next one («عاو» → «عاوز»)
        fragment = len(t) >= V["fragment_min_letters"] and len(nx) - len(t) >= (1 if _ARABIC.search(t) else 2) \
            and t not in STOP and t not in EMPHASIS and t not in _COMMON_PREFIX_WORDS
        if (short or prob(i) < V["false_start_max_p"] or fragment) and gap_after(i) <= V["false_start_restart_ms"]:
            bonus = V["conf_unsure_bonus"] if short and prob(i) < V["false_start_max_p"] else 0
            # «50» before «500», «خمس» before «خمسمية»: a number is never ticked, the editor hears it
            number = _holds_number(ws[i]["word"], ws[i + 1]["word"])
            add("false_start", i, i, V["conf_on_purpose"] if number else V["conf_false_start"] + bonus,
                f"بداية كلمة اتقطعت واتقالت تاني: «{ws[i + 1]['word'].strip()}»"
                + ("؛ بس فيها رقم، فسايبينها لحد ما تسمعها" if number else ""),
                f"a cut-off start, said again: \"{ws[i + 1]['word'].strip()}\""
                + ("; it holds a number, so it is left unticked" if number else ""),
                default="keep" if number else None)
            used.add(i)

    # fillers ---------------------------------------------------------------------------------------------------------
    two = {tuple(c.split()) for c in F["context"] if " " in c}
    one = {c for c in F["context"] if " " not in c}
    for i, t in enumerate(toks):
        if i in used or not t or LAUGHTER.fullmatch(t) or _never_filler(ws[i]["word"]):
            continue
        if _always(t, F, lang):
            add("filler", i, i, V["conf_always_filler"] + (V["conf_unsure_bonus"] / 2 if prob(i) < V["unsure_p"] else 0),
                f"صوت تردد «{ws[i]['word'].strip()}»، مش كلمة", f"a hesitation sound \"{ws[i]['word'].strip()}\", not a word")
            used.add(i)
            continue
        size = 2 if i + 1 < n and (t, toks[i + 1]) in two else (1 if t in one or t in F["stretched_only"] else 0)
        if not size:
            continue
        j = i + size - 1
        if any(k in used for k in range(i, j + 1)) or phrase_only_word(i) or _never_filler(ws[j]["word"]):
            continue
        if not stretched(j) and not (size == 1 and stretched(i)):
            continue
        if t in F["stretched_only"]:
            ok = True
        else:
            ok = gap_before(i) >= V["context_pause_ms"] and gap_after(j) >= V["context_pause_ms"] and \
                not _QUESTION.search(ws[j]["word"]) and not _SENT_END.search(ws[j]["word"]) and j != n - 1
        if not ok:
            continue
        soft = t in F["soft"]
        conf = V["conf_context_filler"] + (V["conf_unsure_bonus"] if prob(i) < V["unsure_p"] else 0)
        heard = " ".join(ws[k]["word"].strip() for k in range(i, j + 1))
        add("filler", i, j, conf,
            f"«{heard}» ممطوطة وحواليها سكتة: حشو" + ("؛ بس «اه» ممكن تكون «أيوه»، فسايبينها" if soft else ""),
            f"\"{heard}\" stretched between pauses: a filler" + ("; but «اه» may mean \"yes\", so it is left unticked"
                                                                 if soft else ""),
            default="keep" if soft else None)
        used.update(range(i, j + 1))

    # repeated words --------------------------------------------------------------------------------------------------
    for i in range(n - 1):
        t = toks[i]
        if i in used or i + 1 in used or not t or t != toks[i + 1] or t in EMPHASIS or LAUGHTER.fullmatch(t) \
                or ws[i].get("speaker") != ws[i + 1].get("speaker"):     # two people saying it is no repeat
            continue
        if gap_after(i) > V["repeat_max_gap_ms"]:
            continue
        number = _holds_number(ws[i]["word"])
        add("repeat_word", i, i, V["conf_on_purpose"] if number else V["conf_repeat_word"],
            f"«{ws[i]['word'].strip()}» اتقالت مرتين ورا بعض؛ نشيل واحدة"
            + ("، بس دي رقم فسايبينها لحد ما تسمعها" if number else ""),
            f"\"{ws[i]['word'].strip()}\" said twice in a row; drop one" + ("; it is a number, so left unticked"
                                                                          if number else ""))
        used.add(i)

    # pauses ----------------------------------------------------------------------------------------------------------
    word_spans = [(p["start_ms"], p["end_ms"]) for p in props]
    for c in pauses or []:
        if not (isinstance(c, (list, tuple)) and len(c) == 2 and all(_num(x) is not None for x in c) and c[1] > c[0]):
            continue
        if any(c[0] < b and a < c[1] for a, b in word_spans):
            continue                       # a word proposal already takes this pause with it (counted once)
        before = max((w["end_ms"] for w in ws if w["end_ms"] <= c[0]), default=0)
        after_w = min((w["start_ms"] for w in ws if w["start_ms"] >= c[1]), default=int(c[1]))
        props.append({"kind": "pause", "start_ms": int(c[0]), "end_ms": int(c[1]), "word_ids": [], "words": [],
                      "confidence": V["conf_pause"], "default": "proposed",
                      "reason": f"سكتة {int(c[1] - c[0])} مللي ثانية (من خريطة السكتات)",
                      "reason_en": f"a {int(c[1] - c[0])} ms pause (from the pause map)",
                      "_bounds": (before, int(c[1]), int(c[0]), after_w)})

    # protections -----------------------------------------------------------------------------------------------------
    after = protect.get("after_ms")
    spans = [s for s in (protect.get("spans") or []) if isinstance(s, (list, tuple)) and len(s) == 2]
    anchors = [a for a in (protect.get("anchors") or []) if _num(a) is not None]
    speaker_at = {ws[k]["id"]: ws[k].get("speaker") for k in range(n)}
    turns = sorted(_num(t) for t in (protect.get("turns") or []) if _num(t) is not None)
    kept = []
    for p in props:
        if after is not None and p["end_ms"] > after:
            continue
        if any(w in pid for w in p["word_ids"]):
            continue
        if any(p["start_ms"] < b and a < p["end_ms"] for a, b in spans):
            continue
        if any(p["start_ms"] < a < p["end_ms"] for a in anchors):
            continue
        if len({speaker_at.get(w) for w in p["word_ids"]}) > 1 or any(p["start_ms"] < t < p["end_ms"] for t in turns):
            continue
        kept.append(p)
    # cut points land in the quietest 10 ms nearby, never inside a neighbouring word (only with audio)
    if samples is not None and sr:
        for p in kept:
            s_lo, s_hi, e_lo, e_hi = p["_bounds"]
            p["start_ms"] = snap(p["start_ms"], samples, sr, int(V["snap_ms"]), int(V["snap_frame_ms"]), s_lo, s_hi)
            p["end_ms"] = max(p["start_ms"], snap(p["end_ms"], samples, sr, int(V["snap_ms"]),
                                                  int(V["snap_frame_ms"]), e_lo, e_hi))
    kept.sort(key=lambda p: (p["start_ms"], KINDS.index(p["kind"]), p["end_ms"]))
    # never leave a kept piece shorter than min_kept_ms: between two removed parts, or at the clip's start or end
    end_of_media = media_end_ms if _num(media_end_ms) is not None else ws[-1]["end_ms"]
    last_end = 0
    ticked = [p for p in kept if p["default"] == "proposed"]
    for k, p in enumerate(ticked):
        later = [q["start_ms"] for q in ticked[k + 1:]]
        tail = (min(later) if later else end_of_media) - p["end_ms"]
        if 0 < p["start_ms"] - last_end < V["min_kept_ms"] or (not later and 0 < tail < V["min_kept_ms"]):
            p["default"] = "keep"
            p["reason"] += f"؛ لو اتشالت هيفضل جزء أقصر من {int(V['min_kept_ms'])} مللي ثانية"
            p["reason_en"] += f"; cutting it would leave a piece shorter than {int(V['min_kept_ms'])} ms"
            continue
        last_end = max(last_end, p["end_ms"])
    for k, p in enumerate(kept, 1):
        p["id"] = f"CP-{k:03d}"
        if p["kind"] == "retake":
            p["keep_ref"] = p["id"] + "k"
    return {"proposals": [_ordered(p) for p in kept], "notes": notes}


_ORDER = ("id", "kind", "start_ms", "end_ms", "word_ids", "words", "keep_ref", "keep", "similarity", "differs",
          "confidence", "reason", "reason_en", "default")


def _ordered(p: dict) -> dict:
    return {k: p[k] for k in _ORDER if k in p}


def snap(ms: int, samples, sr: int, window_ms: int = 50, frame_ms: int = 10, lo=None, hi=None) -> int:
    """The start of the quietest frame_ms frame within ±window_ms of ms, never before lo or after hi (the
    neighbouring words: a cut never moves into a word). On equal energy (flat audio, digital silence) the point
    nearest to ms wins, so nothing moves. samples: a sequence of floats at sr Hz. No audio: ms unchanged."""
    if samples is None or not sr or len(samples) == 0:
        return int(ms)
    step = max(1, int(sr * frame_ms / 1000))
    best, best_e = int(ms), None
    for off in sorted(range(-window_ms, window_ms + 1, frame_ms), key=lambda o: (abs(o), o)):
        t = ms + off
        if (lo is not None and t < lo) or (hi is not None and t > hi):
            continue
        a = int(t * sr / 1000)
        if a < 0 or a + step > len(samples):
            continue
        e = sum(float(x) * float(x) for x in samples[a:a + step])
        if best_e is None or e < best_e - 1e-12:
            best, best_e = int(t), e
    return best


# --- project I/O ----------------------------------------------------------------------------------------------------
def _read(path: Path):
    try:
        data = Path(path).read_bytes()
        return data, json.loads(data.decode("utf-8-sig"))
    except FileNotFoundError:
        return None, None
    except Exception:  # noqa: BLE001
        return b"", None


def _ms(v):
    """A time from edit-decisions: "HH:MM:SS.mmm" (or seconds as text) -> ms; a number is already ms."""
    if _num(v) is not None:
        return v
    if isinstance(v, str):
        from .media_util import parse_time
        try:
            return int(parse_time(v))
        except Exception:  # noqa: BLE001
            return None
    return None


def _quote_spans(toks: list, q: list) -> list:
    """(first, last) token positions where a scene quote is said. The transcript may differ a little (a hesitation
    inside, one word heard differently): the quote's first and last words bound the span, its length may stretch by
    3 words or shrink by 2, and at least 60 % of its words must be inside."""
    if not q:
        return []
    if len(q) == 1:
        return [(i, i) for i, t in enumerate(toks) if t == q[0]]
    out, need = [], max(2, -(-len(q) * 6 // 10))
    for i, t in enumerate(toks):
        if t != q[0]:
            continue
        for j in range(i + max(1, len(q) - 3), min(len(toks), i + len(q) + 3)):
            if toks[j] == q[-1] and sum(1 for x in q if x in toks[i:j + 1]) >= need:
                out.append((i, j))
                break
    return out


def _protections(paths, ws: list, toks: list, lang: str, ctx=None, media_end_ms=None) -> tuple:
    """(protect dict, notes): scene quotes and caption highlights (their words), drug and product names, B-roll
    anchors, speaker turns, and the sign-off."""
    from .common import load_config
    from .plan import onscreen_strings
    notes, ids, anchors, turns = [], set(), [], []
    _, ed = _read(paths.p("01_analysis/edit-decisions.json"))
    ed = ed if isinstance(ed, dict) else {}
    texts = []
    for d in ed.get("decisions") or []:
        for g in (d.get("graphics") or []) if isinstance(d, dict) else []:
            if not isinstance(g, dict):
                continue
            tpl = str(g.get("template") or "")
            if "quote" in tpl or "kinetic" in tpl or "quote" in g:
                texts += onscreen_strings({k: v for k, v in g.items() if k not in ("id", "template", "start", "end")})
            if "broll" in tpl:
                a = _ms(g.get("start"))
                if a is not None:
                    anchors.append(a)
    for h in ed.get("caption_highlights") or []:
        if isinstance(h, dict) and isinstance(h.get("text"), str):
            texts.append(h["text"])
    for text in texts:
        q = [norm_word(x) for x in str(text).split() if norm_word(x)]
        for i, j in _quote_spans(toks, q):
            ids.update(ws[k]["id"] for k in range(i, j + 1))
    try:     # drug and product names: K-T1's reader (split names, clitics) over its lexicon + the client's glossary
        from .safety import lexicon, risk_words
        index, _ = risk_words._lexicon_index(lexicon.load_sources()["groups"] + [[t] for t in lexicon.client_terms(ctx)])
        for a, b, _g in risk_words._drug_spans(risk_words._tokens(ws), [False] * len(ws), index, False, False):
            ids.update(ws[k]["id"] for k in range(a, b))
    except Exception:  # noqa: BLE001
        pass
    _, sp = _read(paths.p("00_inputs/speakers.json"))
    for t in (sp.get("turns") or []) if isinstance(sp, dict) else []:
        if isinstance(t, dict):
            a = _ms(t.get("start_ms", t.get("start")))
            if a is not None:
                turns.append(a)
    # the sign-off: the editor's marker, else the profile phrase in the last 20 s
    after = None
    marker = _ms((ed.get("global") or {}).get("sign_off_at")) if isinstance(ed.get("global"), dict) else None
    try:
        so = (load_config("profile.json", ctx).get("endings") or {}).get("sign_off") or {}
    except Exception:  # noqa: BLE001
        so = {}
    end_ms = media_end_ms if _num(media_end_ms) is not None else (ws[-1]["end_ms"] if ws else 0)
    V = settings(ctx)["values"]
    if marker is not None:
        after = marker
    elif isinstance(so, dict) and so.get("on"):
        phrase = str(so.get("phrase") or "").strip()
        q = [norm_word(x) for x in phrase.split() if norm_word(x)]
        hit = None
        for i in range(len(toks) - len(q) + 1):
            if q and toks[i:i + len(q)] == q and ws[i]["start_ms"] >= end_ms - V["sign_off_search_s"] * 1000:
                hit = ws[i]["start_ms"]
        if hit is not None:
            after = hit
        else:
            after = max(0, end_ms - V["sign_off_fallback_s"] * 1000)
            said = f"«{phrase}»" if phrase else "(من غير نص في الملف / no phrase in the profile)"
            notes.append((f"جملة الختام {said} ماتلقتش في آخر {V['sign_off_search_s']:g} ثانية، فآخر "
                          f"{V['sign_off_fallback_s']:g} ثواني محمية من القص.",
                          f"The sign-off {said} was not found in the last {V['sign_off_search_s']:g} s, so the "
                          f"last {V['sign_off_fallback_s']:g} s are protected from cuts."))
    return {"word_ids": ids, "anchors": anchors, "turns": turns, "after_ms": after, "spans": []}, notes


def _inputs(paths, data: bytes, wj: dict, ctx=None) -> dict:
    """Everything the proposals depend on (words, settings, pause map, protections, clip length) and its hash: a
    later --accept recomputes the hash, so it refuses ids from a list made with other inputs."""
    meta = wj.get("meta") if isinstance(wj.get("meta"), dict) else {}
    lang = "en" if str(meta.get("language") or "").lower().startswith("en") else "ar"
    cfg = settings(ctx)
    ws = clean_words(wj["words"])
    media_end = _num(meta.get("duration_ms"))
    protect, notes = _protections(paths, ws, [norm_word(w["word"]) for w in ws], lang, ctx, media_end)
    _, pj = _read(paths.p("06_audio/dialogue/pauses.json"))
    pauses = pj.get("cuts_ms") if isinstance(pj, dict) and isinstance(pj.get("cuts_ms"), list) else []
    key = json.dumps([hashlib.sha1(data).hexdigest(), cfg["values"], cfg["fillers"], pauses,
                      sorted(map(str, protect["word_ids"])), protect["anchors"], protect["turns"],
                      protect["after_ms"], media_end, lang], ensure_ascii=False, sort_keys=True, default=str)
    return {"words": ws, "lang": lang, "cfg": cfg, "protect": protect, "notes": notes, "pauses": pauses,
            "media_end_ms": media_end, "sha1": hashlib.sha1(key.encode("utf-8")).hexdigest()}


def propose(paths, ctx=None, samples=None, sr: int = 0) -> dict:
    """Compute the proposals and write 01_analysis/cut-proposals.json (one atomic write). A missing or damaged
    words.json is refused with a plain reason and nothing is written."""
    from .common import write_json
    from .errors import Guidance
    wf = paths.p("02_transcription/words.json")
    data, wj = _read(wf)
    if data is None or not isinstance(wj, dict) or not isinstance(wj.get("words"), list):
        raise Guidance("مفيش تفريغ صالح للفيديو ده، فمش هقدر أقترح قص / no usable transcript for this item "
                       "(02_transcription/words.json is missing or damaged)",
                       "Run `reel transcribe` (or fix the file), then `reel cut-proposals` again", where=str(wf))
    inp = _inputs(paths, data, wj, ctx)
    res = compute(inp["words"], inp["pauses"], cfg=inp["cfg"], lang=inp["lang"], protect=inp["protect"],
                  samples=samples, sr=sr, media_end_ms=inp["media_end_ms"])
    cfg, lang, notes = inp["cfg"], inp["lang"], inp["notes"]
    totals = {}
    for p in res["proposals"]:
        t = totals.setdefault(p["kind"], {"count": 0, "seconds": 0.0})
        t["count"] += 1
        t["seconds"] = round(t["seconds"] + (p["end_ms"] - p["start_ms"]) / 1000, 2)
    doc = {"schema": SCHEMA, "video_id": paths.video_id, "words_sha1": hashlib.sha1(data).hexdigest(),
           "inputs_sha1": inp["sha1"], "language": lang, "snapped": bool(samples is not None and sr),
           "settings": {"values": cfg["values"], "basis": cfg["basis"]},
           "notes": [{"ar": a, "en": e} for a, e in notes + res["notes"]],
           "proposals": res["proposals"], "totals": totals,
           "how": "لا شيء يتقص قبل موافقتك: اختار الأرقام وشغّل `reel cut-proposals --accept CP-001,CP-004`، بعدين "
                  "`reel plan` وموافقة جديدة / nothing is cut until you choose: `reel cut-proposals --accept "
                  "CP-001,CP-004`, then `reel plan` and a new approval"}
    write_json(paths.p(FILE), doc)
    return doc


def load(paths) -> dict | None:
    _, doc = _read(paths.p(FILE))
    return doc if isinstance(doc, dict) and isinstance(doc.get("proposals"), list) else None


def accept(paths, ids, by: str = "editor", ctx=None) -> dict:
    """Copy the chosen word proposals into edit-decisions.json global.cut_words (idempotent). Refused, with nothing
    written, when the proposals are missing or stale (the words changed since), an id is unknown, or there is no
    edit-decisions.json yet. The plan must then be compiled and approved again before anything is cut."""
    from .common import read_json, write_json
    from .errors import Guidance
    doc = load(paths)
    if not doc:
        raise Guidance("مفيش اقتراحات قص لسه / no cut proposals yet", "Run `reel cut-proposals` first",
                       where=str(paths.p(FILE)))
    data, wj = _read(paths.p("02_transcription/words.json"))
    stale = not data or not isinstance(wj, dict) or not isinstance(wj.get("words"), list) \
        or hashlib.sha1(data).hexdigest() != doc.get("words_sha1")
    if not stale:
        stale = _inputs(paths, data, wj, ctx).get("sha1") != doc.get("inputs_sha1")
    if stale:
        raise Guidance("التفريغ أو الإعدادات اتغيرت بعد الاقتراحات، فالأرقام ممكن تكون اتغيرت / the transcript or the "
                       "settings changed after these proposals, so their numbers may point at other words",
                       "Run `reel cut-proposals` again and choose from the new list", where=str(paths.p(FILE)))
    by_id = {p["id"]: p for p in doc["proposals"]}
    want = [str(i).strip().upper() for i in ids or [] if str(i).strip()]
    unknown = [i for i in want if i not in by_id]
    if not want or unknown:
        raise Guidance(f"رقم اقتراح مش موجود: {', '.join(unknown) or '(ولا رقم)'} / unknown proposal id(s): "
                       f"{', '.join(unknown) or '(none given)'}",
                       "Use the ids listed in 01_analysis/cut-proposals.json (e.g. CP-001)", where=str(paths.p(FILE)))
    ef = paths.p("01_analysis/edit-decisions.json")
    ed = read_json(ef)
    if not isinstance(ed, dict):
        raise Guidance("مفيش قرارات مونتاج لسه / no edit decisions yet (01_analysis/edit-decisions.json)",
                       "The story editor writes them first, then accept the cuts", where=str(ef))
    g = ed.setdefault("global", {})
    cw = g.setdefault("cut_words", [])
    # the same words are never added twice, whatever id they had in an earlier list
    have = {tuple(sorted(map(str, c.get("word_ids") or []))) for c in cw if isinstance(c, dict)}
    added, already, pauses = [], [], []
    for i in want:
        p = by_id[i]
        if p["kind"] not in WORD_KINDS:
            pauses.append(i)
            continue
        key = tuple(sorted(map(str, p["word_ids"])))
        if key in have:
            already.append(i)
            continue
        # range_ms: the proposal's own span (padding, the breath after a take, the snapped edges), so the plan cuts
        # the take whole instead of word by word
        cw.append({"word_ids": list(p["word_ids"]), "range_ms": [p["start_ms"], p["end_ms"]],
                   "reason": f"{i} {p['kind']}: {p['reason_en']}", "by": by})
        have.add(key)
        added.append(i)
    if added:
        write_json(ef, ed)
    res = {"added": added, "already": already,
           "next": "`reel plan`, then the editor approves the plan again (nothing is cut before that)"}
    if pauses:
        res["pauses"] = pauses
        res["pauses_note"] = ("السكتات دي بتتشال لما «شيل السكتات» يكون شغال في الخطة (remove_pauses)، مش من هنا / "
                              "these pauses are removed by the plan's remove_pauses, not here")
    return res


def plan_table(doc: dict | None) -> list:
    """The "Proposed cuts" lines for edit-plan.md (Arabic first), with seconds saved per kind."""
    if not doc or not doc.get("proposals"):
        return []
    L = ["## اقتراحات القص — Proposed cuts", "", "| # | النوع / kind | من / from | إلى / to | السبب / reason | الافتراضي |",
         "|---|---|---|---|---|---|"]
    for p in doc["proposals"]:
        ar, en = LABEL[p["kind"]]
        L.append(f"| {p['id']} | {ar} / {en} | {p['start_ms'] / 1000:.2f} | {p['end_ms'] / 1000:.2f} | {p['reason']} | "
                 f"{'مقترح' if p['default'] == 'proposed' else 'سيبه'} |")
    L.append("")
    for k, t in (doc.get("totals") or {}).items():
        ar, en = LABEL.get(k, (k, k))
        L.append(f"- {ar} / {en}: {t['count']} ({t['seconds']:.1f} s)")
    L += ["", "لا شيء يتقص قبل موافقتك / nothing is cut before your approval.", ""]
    return L


MARKER_COLOUR = {"pause": 0, "retake": 1, "false_start": 3, "filler": 4, "repeat_word": 5}   # Premiere label indexes


def seq_ms(src_ms: float, keep_ms: list | None) -> float:
    """A source time on the sequence clock of a plan that removed pauses (timeline-spec time_map.keep_ms): the kept
    pieces are laid end to end; a time inside a removed piece lands on the cut. No keep list: unchanged."""
    if not keep_ms:
        return src_ms
    t = 0.0
    for a, b in keep_ms:
        if src_ms < a:
            return t
        if src_ms <= b:
            return t + (src_ms - a)
        t += b - a
    return t


def markers(doc: dict | None, fps: float, keep_ms: list | None = None) -> list:
    """Sequence markers for the Premiere build: one per proposal, colour per kind, name = kind + reason, placed on
    the sequence clock (keep_ms: the plan's time_map.keep_ms when it removed pauses). A proposal the plan already
    removed whole (a pause the plan cut) gets no marker."""
    out = []
    for p in (doc or {}).get("proposals") or []:
        a, b = seq_ms(p["start_ms"], keep_ms), seq_ms(p["end_ms"], keep_ms)
        if b <= a:
            continue
        ar, en = LABEL[p["kind"]]
        out.append({"t": round(a / 1000, 3), "dur": round((b - a) / 1000, 3),
                    "name": f"{p['id']} {ar} / {en}", "comment": p["reason"], "colour": MARKER_COLOUR[p["kind"]],
                    "frame": int(round(a / 1000 * fps))})
    return out
