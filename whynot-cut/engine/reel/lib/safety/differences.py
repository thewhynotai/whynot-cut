# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""What two takes of one line do not share in meaning: numbers and doses, negation, timing (Task 25 retakes and K-T7
takes read it the same way).

- numbers, doses, ordinals («الشهر التالت», "first trimester"; not the openers «أول حاجة», «أول ما», "first of
  all") and «تاني» / "again" (one dose more?): K-T1's number reader (`quantities`: «حباية واحدة», «٥٠٠ مجم» == "500 mg", «حبايتين»), a
  frequency word («مرتين», "daily"), compared by kind and value; an everyday word that is also a number («واحد»
  someone, «ست» lady) counts only when the other take says a number too («خمسة» → «ست»);
- negation: K-T1's negation reader (a negation word, a negated verb «مبيقللش», "doesn't", "isn't") plus «غير»
  («غير آمن», «من غير أكل»); «ما» after «قبل», «زي», «لحد» … is a connector, and «ولا» is "or" unless it opens the
  take, follows a negation («لا ده ولا ده»), comes before «حاجة», «حد», «مرة» or a verb («ولا تاخدي»). Compared by how
  many there are, on purpose: «مش بيقلل» and «مبيقللش» say the same, and so do "not" and "never" (a flip of
  polarity is what changes a claim);
- timing: a time of day («الصبح», «بالليل»), a day («السبت», «النهارده», «بكرة», «بعد بكرة»), how often («كل أسبوع», «يوميا»,
  "once a week" == "weekly"), and before/after/with a meal or sleep within three words («بعد الفطار», «قبل ما
  تنامي», "with a full meal" == "with food"); a clitic does not make another time («بالليل» == «الليل»).

`compare` returns {} when the takes agree, else {kind: {"a": [as said in take a], "b": [as said in take b]}}.
Nothing here reads a file or raises for odd input (G10)."""
import re
from collections import Counter

from .numbers import canon, find_numbers, fold, frequency_value, is_frequency, quantities, stems, timing_phrases
from .risk_words import _negation

TIME_OF_DAY = {"صبح": "morning", "صباح": "morning", "صباحا": "morning", "ضهر": "noon",
               "ظهر": "noon", "عصر": "afternoon", "مغرب": "evening", "مسا": "evening", "مساء": "evening",
               "مساءا": "evening", "ليل": "night", "ليله": "night", "بليل": "night", "نهار": "day",
               "morning": "morning", "mornings": "morning", "noon": "noon", "midday": "noon", "afternoon": "afternoon",
               "evening": "evening", "evenings": "evening", "night": "night", "nights": "night", "tonight": "night",
               "bedtime": "sleep"}
DAYS = {"سبت": "sat", "حد": "sun", "احد": "sun", "اتنين": "mon", "اثنين": "mon", "تلات": "tue", "ثلاثاء": "tue",
        "تلاتاء": "tue", "اربع": "wed", "اربعاء": "wed", "خميس": "thu", "جمعه": "fri",
        "saturday": "sat", "sunday": "sun", "monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu",
        "friday": "fri"}
# days that are also everyday words («حد» someone, «اتنين» two, «اربع» four): a day only after «يوم» / «كل»
_DAY_NEEDS_CUE = {"حد", "احد", "اتنين", "اثنين", "تلات", "اربع"}
_DAY_CUE = {"يوم", "كل", "on", "every"}
MEALS = {"فطار": "breakfast", "فطور": "breakfast", "غدا": "lunch", "غداء": "lunch", "عشا": "dinner",
         "عشاء": "dinner", "اكل": "meal", "تاكل": "meal", "تاكلي": "meal", "ناكل": "meal", "ياكل": "meal", "وجبه": "meal",
         "نوم": "sleep", "تنام": "sleep", "تنامي": "sleep", "ننام": "sleep", "ينام": "sleep", "انام": "sleep",
         "ريق": "empty",
         "breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner", "supper": "dinner", "meal": "meal",
         "meals": "meal", "food": "meal", "eating": "meal", "eat": "meal", "bed": "sleep", "bedtime": "sleep",
         "sleep": "sleep", "sleeping": "sleep"}
RELATIVE_DAYS = {"النهارده": "today", "نهارده": "today", "انهارده": "today", "النهاردا": "today", "بكره": "tomorrow",
                 "بكرا": "tomorrow", "امبارح": "yesterday", "امبارحه": "yesterday", "امس": "yesterday",
                 "today": "today", "tomorrow": "tomorrow", "yesterday": "yesterday"}
PERIOD = {"يوم": "day", "ايام": "day", "يوميا": "day", "day": "day", "days": "day", "daily": "day",
          "اسبوع": "week", "اسابيع": "week", "اسبوعيا": "week", "week": "week", "weeks": "week", "weekly": "week",
          "شهر": "month", "شهور": "month", "اشهر": "month", "شهريا": "month", "month": "month", "months": "month",
          "monthly": "month", "سنه": "year", "سنين": "year", "سنويا": "year", "year": "year", "years": "year",
          "yearly": "year", "annually": "year", "ساعه": "hour", "ساعات": "hour", "hour": "hour", "hours": "hour",
          "hourly": "hour", "nightly": "night"}
_PER_ADVERB = {"يوميا", "اسبوعيا", "شهريا", "سنويا", "daily", "weekly", "monthly", "yearly", "annually", "hourly",
               "nightly"}
_EVERY = {"كل", "في", "a", "an", "per", "every", "each"}
# two-word days: «بعد بكرة», «أول امبارح»
RELATIVE_DAY_PAIRS = {("بعد", "بكره"): "after_tomorrow", ("بعد", "بكرا"): "after_tomorrow",
                      ("اول", "امبارح"): "before_yesterday", ("اول", "امبارحه"): "before_yesterday"}
# ordinals («الشهر التالت», «الأسبوع الأول», "first trimester"); «تاني» alone is also "again", so the 2nd counts only
# with the article («التاني»)
ORDINALS = {"اول": 1, "اولاني": 1, "اولانيه": 1, "اولانيين": 1, "اولي": 1, "تالت": 3, "ثالث": 3, "تالته": 3,
            "ثالثه": 3, "رابع": 4, "رابعه": 4, "خامس": 5, "خامسه": 5, "سادس": 6, "سادسه": 6, "سابع": 7, "سابعه": 7,
            "تامن": 8, "ثامن": 8, "تامنه": 8, "تاسع": 9, "تاسعه": 9, "عاشر": 10, "عاشره": 10, "اخر": "last",
            "اخراني": "last", "اخرانيه": "last", "اخرانيين": "last", "اخير": "last", "اخيره": "last",
            "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
            "ninth": 9, "tenth": 10, "last": "last", "final": "last", "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
_SECOND_WITH_ARTICLE = {"التاني": 2, "الثاني": 2, "التانيه": 2, "الثانيه": 2, "التانيين": 2}
# openers that only look like ordinals: «أول حاجة», «آخر حاجة», «أول ما» (as soon as), "first of all", "at first"
_OPENER_NEXT = {"حاجه", "ما"}
# «تاني» / "again" beside a dose may be one dose more: read with the numbers
AGAIN = {"تاني", "تانيه", "again"}
_MEAL_REACH = 3          # «قبل ما تنامي», "with a full meal": the meal or sleep word within this many words
RELATIVE = {"قبل": "before", "بعد": "after", "ورا": "after", "مع": "with", "علي": "on", "before": "before",
            "after": "after", "with": "with"}
LABEL = {"negation": ("نفي", "negation"), "numbers": ("رقم أو جرعة", "number or dose"),
         "timing": ("توقيت", "timing")}
_ORDER = ("negation", "numbers", "timing")
_EDGE_PUNCT = re.compile(r"^[\s\"'«»“”(\[]+|[\s.,!?؟…،؛:\"'«»“”)\]]+$")    # shown as said, without the sentence's marks


def _stems(tok: str) -> list:
    """stems(), and a second clitic off too: «وبالليل» = و + بال + ليل."""
    return list(dict.fromkeys(x for s in stems(tok) for x in stems(s)))


def _key(table: dict, tok: str):
    for s in _stems(tok):
        if s in table:
            return table[s]
    return None


NEGATION_EXTRA = {"غير", "بلا"}
_MA_CONNECTOR = {"قبل", "بعد", "زي", "اول", "كل", "طول", "لحد", "لغايه", "عشان", "بين", "مع", "من", "يوم", "وقت"}
_WALA_NEG_NEXT = {"حاجه", "حد", "واحد", "مره", "اي", "يوم"}


def _negates(raws: list, toks: list, i: int, after_negation: bool) -> bool:
    """Is word i a negation in this take (see the module text for «ما» and «ولا»); after_negation: an earlier word of
    the take is one."""
    tok = toks[i]
    prev = toks[i - 1] if i > 0 else ""
    nxt_ = toks[i + 1] if i + 1 < len(toks) else ""
    if tok == "ما" and any(s in _MA_CONNECTOR for s in stems(prev)) and not (len(nxt_) >= 3 and nxt_.endswith("ش")):
        return False                    # «قبل ما تنامي», «زي ما قلتلك»: a connector; «عشان ما تتعبيش» stays negation
    if tok == "ولا":
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        return i == 0 or after_negation or nxt in _WALA_NEG_NEXT             or (len(nxt) >= 4 and nxt[0] in "تين")       # «ولا حاجة», «لا ده ولا ده», «ولا تاخدي»; else "or"
    if _negation(tok) or any(s in NEGATION_EXTRA for s in stems(tok)):
        return True
    low = str(raws[i] or "").lower().replace("’", "'").strip(".,!?؟…\"'«»")
    return low.endswith("n't") or bool(_negation(low))


def reading(words) -> dict:
    """{kind: [(key, words as said)]} for one take (a list of spoken words, as written in the transcript)."""
    raw = [_EDGE_PUNCT.sub("", str(w or "").strip()) for w in (words or [])]
    toks = [fold(w) for w in raw]
    out = {"numbers": [], "negation": [], "timing": []}
    said = lambda a, b: " ".join(raw[a:b])                      # noqa: E731
    taken = set()
    for q in quantities(toks):
        out["numbers"].append(((q["kind"], canon(q["value"])), said(q["start"], q["end"])))
        taken.update(range(q["start"], q["end"]))
    for n in find_numbers(toks):                               # a number word with no unit («خمسة», «ست»)
        if not taken & set(range(n["start"], n["end"])):
            kind = "everyday" if n["ambiguous"] else "number"
            out["numbers"].append(((kind, canon(n["value"])), said(n["start"], n["end"])))
            taken.update(range(n["start"], n["end"]))
    pair_days = {}
    for i in range(len(toks) - 1):
        d = next((RELATIVE_DAY_PAIRS[(x, y)] for x in stems(toks[i]) for y in stems(toks[i + 1])
                  if (x, y) in RELATIVE_DAY_PAIRS), None)
        if d and i not in pair_days and i - 1 not in pair_days:
            pair_days[i] = d
    paired = {k for i in pair_days for k in (i, i + 1)}
    for i, t in enumerate(toks):
        if not t or i in taken or i in paired:
            continue
        if t in AGAIN:
            out["numbers"].append((("again",), raw[i]))
            taken.add(i)
            continue
        o = _SECOND_WITH_ARTICLE.get(t) or next((ORDINALS[s] for s in stems(t) if s in ORDINALS), None)
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        after = toks[i + 2] if i + 2 < len(toks) else ""
        if o is not None and (nxt in _OPENER_NEXT or (nxt == "of" and after == "all")
                              or (t == "first" and i > 0 and toks[i - 1] == "at")):
            continue
        if o is not None:
            out["numbers"].append((("ordinal", o), raw[i]))
            taken.add(i)
    for i, t in enumerate(toks):
        if t and i not in taken and is_frequency(t) and frequency_value(t) is not None:     # «مرتين», "twice"
            out["numbers"].append((("frequency", canon(frequency_value(t))), raw[i]))
    for i, t in enumerate(toks):
        if t and _negates(raw, toks, i, bool(out["negation"])):
            out["negation"].append((("not",), raw[i]))
    timed = set(paired)
    for i, d in sorted(pair_days.items()):
        out["timing"].append((("day", d), said(i, i + 2)))
    for i, t in enumerate(toks):
        rel = _key(RELATIVE, t)
        if not rel or i in timed:
            continue
        for j in range(i + 1, min(len(toks), i + 1 + _MEAL_REACH)):
            if _key(RELATIVE, toks[j]):
                break
            meal = _key(MEALS, toks[j])
            if meal:
                out["timing"].append(((rel, meal), said(i, j + 1)))
                timed.update(range(i, j + 1))
                break
    for a, b in timing_phrases(toks):
        if not timed & set(range(a, b)):
            out["timing"].append((tuple(toks[a:b]), said(a, b)))
            timed.update(range(a, b))
    for i, t in enumerate(toks):                   # how often: «كل أسبوع», «في اليوم», "a week", «يوميا», "daily"
        if i in timed or not t:
            continue
        per = _key(PERIOD, toks[i + 1]) if t in _EVERY and i + 1 < len(toks) and i + 1 not in timed else None
        if per:
            out["timing"].append((("per", per), said(i, i + 2)))
            timed.update((i, i + 1))
        elif any(s in _PER_ADVERB for s in stems(t)):
            out["timing"].append((("per", _key(PERIOD, t)), raw[i]))
            timed.add(i)
    for i, t in enumerate(toks):
        if i in timed or not t:
            continue
        rel_day = _key(RELATIVE_DAYS, t)
        if rel_day:
            out["timing"].append((("day", rel_day), raw[i]))
            continue
        tod = _key(TIME_OF_DAY, t)
        day = _key(DAYS, t)
        if day and next((s for s in _stems(t) if s in DAYS), t) in _DAY_NEEDS_CUE and \
                not (i > 0 and toks[i - 1] in _DAY_CUE):
            day = None
        if tod or day:
            out["timing"].append((("time", tod or day), raw[i]))
    return out


def compare(a_words, b_words) -> dict:
    """{} when two takes say the same numbers, negation and timing; else, per kind that differs, the words of each
    take that carry it ({"a": [...], "b": [...]}, as said, in order)."""
    ra, rb = reading(a_words), reading(b_words)
    out = {}
    for r, other in ((ra, rb), (rb, ra)):           # «واحد» (someone) counts only against a number in the other take
        if not other["numbers"]:
            r["numbers"] = [x for x in r["numbers"] if x[0][0] != "everyday"]
    for kind in _ORDER:
        ca, cb = Counter(k for k, _ in ra[kind]), Counter(k for k, _ in rb[kind])
        if ca == cb:
            continue
        if kind == "negation":                 # how many negations, not which word: «مش بيقلل» == «مبيقللش»
            out[kind] = {"a": [s for _, s in ra[kind]], "b": [s for _, s in rb[kind]]}
            continue
        only_a, only_b = ca - cb, cb - ca
        out[kind] = {"a": [s for k, s in ra[kind] if only_a.get(k)], "b": [s for k, s in rb[kind] if only_b.get(k)]}
    return out


def describe(diff: dict) -> tuple:
    """(ar, en) naming what differs, Arabic first: «توقيت: «الصبح» مقابل «بالليل»»; ("", "") when nothing does."""
    if not diff:
        return "", ""

    def side(ws, none):
        return "، ".join(f"«{w}»" for w in ws) if ws else none
    ar = "؛ ".join(f"{LABEL[k][0]}: {side(diff[k]['a'], '(مفيش)')} مقابل {side(diff[k]['b'], '(مفيش)')}"
                   for k in _ORDER if k in diff)
    en = "; ".join(f"{LABEL[k][1]}: {side(diff[k]['a'], '(none)')} vs {side(diff[k]['b'], '(none)')}"
                   for k in _ORDER if k in diff)
    return ar, en
