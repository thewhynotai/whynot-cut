# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""What two takes of one line do not share in meaning: numbers and doses, negation, timing, a condition or an
exception, a different medical word (Task 25 retakes and K-T7 takes read it the same way).

- numbers, doses, ordinals («الشهر التالت», "first trimester"; not the openers «أول حاجة», «أول ما», "first of
  all") and «تاني» / "again" (one dose more?): K-T1's number reader (`quantities`: «حباية واحدة», «٥٠٠ مجم» == "500 mg", «حبايتين»), a
  frequency word («مرتين», "daily"), compared by kind and value; an everyday word that is also a number («واحد»
  someone, «ست» lady) counts only when the other take says a number too («خمسة» → «ست»);
- negation: K-T1's negation reader (a negation word, a negated verb «مبيقللش», "doesn't", "isn't") plus «غير»
  («غير آمن», «من غير أكل»); «ما» after «قبل», «زي», «لحد» … is a connector, and «ولا» is "or" unless it opens the
  take, follows a negation («لا ده ولا ده»), comes before «حاجة», «حد», «مرة» or a verb («ولا تاخدي»). Compared by
  what each negates (the negated word and the next one, small words skipped), not by which negation word: «مش
  بيقلل الضغط», «ما بيقللش الضغط» and «مبيقللش الضغط» say the same, and so do "not" and "never"; a negation that
  moves («مش بيقلل الضغط وبيقلل السكر» / «بيقلل الضغط ومش بيقلل السكر») differs;
- a condition or an exception: «لو», «إلا», «بشرط», «طالما», "if", "unless", "only", "except", and a "but" clause
  («بس», «لكن», "but" after the first word), compared by kind and count («لو سمحت», "please", is none);
- a different medical word: a medicine (the shipped names, a generic-name ending) said in one take only or swapped,
  an opposite on one scale («آمن» / «خطر», «بيقلل» / «بيرفع»), an organ for another («الكبد» / «الكلى»);
- timing: a time of day («الصبح», «بالليل»), a day («السبت», «النهارده», «بكرة», «بعد بكرة»), how often («كل أسبوع», «يوميا»,
  "once a week" == "weekly"), and before/after/with a meal or sleep within three words («بعد الفطار», «قبل ما
  تنامي», "with a full meal" == "with food"); a clitic does not make another time («بالليل» == «الليل»).

`compare` returns {} when the takes agree, else {kind: {"a": [as said in take a], "b": [as said in take b]}}.
Nothing here reads a file or raises for odd input (G10)."""
import re
from collections import Counter

from .numbers import canon, find_numbers, fold, frequency_value, is_frequency, quantities, stems, timing_phrases
from .risk_words import _drug_spans, _lexicon_index, _negation, negated_core

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
# a meal or sleep said as an instruction («… وبعدين نامي», «… وبعدين اتغدي»): timing even with no «قبل» / «بعد» (a
# noun alone, "you need sleep", is no instruction)
EVENTS = {"نام": "sleep", "نامي": "sleep", "ناموا": "sleep", "اتغدي": "lunch", "اتغدوا": "lunch", "تتغدي": "lunch",
          "اتعشي": "dinner", "اتعشوا": "dinner", "تتعشي": "dinner", "افطري": "breakfast", "افطروا": "breakfast",
          "تفطري": "breakfast"}
MEALS.update(EVENTS)
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
# which one of a period: «الشهر ده» / «الشهر الجاي», "next week" / "this week", «لمدة أسبوع» / «لمدة شهر»
PERIOD_AFTER = {"ده": "this", "دي": "this", "دا": "this", "الجاي": "next", "الجايه": "next", "القادم": "next",
                "القادمه": "next", "الماضي": "last", "الماضيه": "last", "فات": "last", "جاي": "next", "جايه": "next"}
PERIOD_BEFORE = {"next": "next", "this": "this", "last": "last", "coming": "next", "past": "last", "previous": "last",
                 "for": "for", "لمده": "for", "طول": "for"}
# the same claim said the opposite way: (axis, side)
OPPOSITES = {"امن": ("safe", 1), "امان": ("safe", 1), "سليم": ("safe", 1), "safe": ("safe", 1),
             "خطر": ("safe", -1), "خطير": ("safe", -1), "خطيره": ("safe", -1), "مضر": ("safe", -1),
             "ضار": ("safe", -1), "dangerous": ("safe", -1), "harmful": ("safe", -1), "unsafe": ("safe", -1),
             "فعال": ("works", 1), "مفيد": ("works", 1), "effective": ("works", 1), "useful": ("works", 1),
             "useless": ("works", -1), "ineffective": ("works", -1),
             "بيقلل": ("level", -1), "يقلل": ("level", -1), "تقلل": ("level", -1), "بتقلل": ("level", -1),
             "بينزل": ("level", -1), "ينزل": ("level", -1), "بيخفض": ("level", -1), "يخفض": ("level", -1),
             "lowers": ("level", -1), "lower": ("level", -1), "reduces": ("level", -1), "reduce": ("level", -1),
             "decreases": ("level", -1), "decrease": ("level", -1),
             "بيزود": ("level", 1), "يزود": ("level", 1), "تزود": ("level", 1), "بيرفع": ("level", 1),
             "يرفع": ("level", 1), "بيزيد": ("level", 1), "يزيد": ("level", 1), "raises": ("level", 1),
             "raise": ("level", 1), "increases": ("level", 1), "increase": ("level", 1),
             "حلو": ("good", 1), "كويس": ("good", 1), "كويسه": ("good", 1), "good": ("good", 1),
             "وحش": ("good", -1), "وحشه": ("good", -1), "bad": ("good", -1),
             "عالي": ("high", 1), "مرتفع": ("high", 1), "high": ("high", 1), "واطي": ("high", -1),
             "منخفض": ("high", -1), "low": ("high", -1)}
# an organ by name («الكبد» / «الكلى», liver / kidney)
ORGANS = {"كبد": "liver", "liver": "liver", "كلي": "kidney", "كلاوي": "kidney", "كليه": "kidney", "kidney": "kidney",
          "kidneys": "kidney", "قلب": "heart", "heart": "heart", "ريه": "lung", "ريتين": "lung",
          "lung": "lung", "lungs": "lung", "معده": "stomach", "stomach": "stomach", "مخ": "brain", "brain": "brain",
          "بنكرياس": "pancreas", "pancreas": "pancreas", "thyroid": "thyroid", "درقيه": "thyroid", "رحم": "uterus",
          "uterus": "uterus", "مثانه": "bladder", "bladder": "bladder", "عضم": "bone", "عظم": "bone", "bone": "bone",
          "bones": "bone"}
# "un-" + a word the other take says ("safe" / "unsafe"): a negation
NEG_PREFIXES = ("non", "un", "in", "im", "ir", "il", "dis")
# a condition or an exception (kind of each); «بس» / «لكن» / "but" open a clause only after the first word
CONDITIONS = {"لو": "if", "ولو": "if", "فلو": "if", "بشرط": "if", "طالما": "if", "اذا": "if", "if": "if",
              "provided": "if", "لما": "when", "ولما": "when", "when": "when", "whenever": "when",
              "الا": "except", "والا": "except", "ماعدا": "except", "عدا": "except", "باستثناء": "except",
              "unless": "except", "except": "except", "excluding": "except", "only": "only", "فقط": "only",
              "وفقط": "only", "بس": "but", "لكن": "but", "ولكن": "but", "انما": "but", "but": "but", "however": "but"}
# two or three words: «في حالة», «وقت ما», "in case", "just in case", "even if", «حتى لو»
CONDITION_PHRASES = {("في", "حاله"): "if", ("وقت", "ما"): "when", ("اول", "ما"): "when", ("as", "soon", "as"): "when",
                     ("in", "case"): "if",
                     ("just", "in", "case"): "precaution", ("even", "if"): "even_if", ("حتي", "لو"): "even_if",
                     ("حتي", "اذا"): "even_if", ("even", "when"): "even_if"}
_BUT = {"بس", "لكن", "ولكن", "انما", "but", "however"}
_BUT_ENDS = {"كده", "خلاص", "بقي"}        # «بس كده», «بس خلاص»: "that's all", no clause («بعد الأكل بس يا …»: only)
_PLEASE = {"سمحت", "سمحتي", "سمحتوا", "سمحتم"}           # «لو سمحت»: please, no condition
# skipped when naming what a negation negates («مش خالص بيقلل», "not at all safe", "not safe for kids")
_SMALL = {"ده", "دي", "دا", "دول", "خالص", "ابدا", "اصلا", "يا", "حتي", "كمان", "في", "علي", "من", "عن", "ل", "مع",
          "the", "a", "an", "is", "are", "be", "been", "at", "all", "to", "of", "it", "that", "this", "for", "with",
          "so", "really", "even", "ever", "on", "in"}
LABEL = {"negation": ("نفي", "negation"), "numbers": ("رقم أو جرعة", "number or dose"),
         "timing": ("توقيت", "timing"), "condition": ("شرط أو استثناء", "a condition or an exception"),
         "claim": ("كلام طبي مختلف", "a different medical word")}
_ORDER = ("negation", "numbers", "timing", "condition", "claim")
_EDGE_PUNCT = re.compile(r"^[\s\"'«»“”(\[]+|[\s.,!?؟…،؛:\"'«»“”)\]]+$")    # shown as said, without the sentence's marks


def _stems(tok: str) -> list:
    """stems(), and a second clitic off too: «وبالليل» = و + بال + ليل."""
    return list(dict.fromkeys(x for s in stems(tok) for x in stems(s)))


def _key(table: dict, tok: str):
    for s in _stems(tok):
        if s in table:
            return table[s]
    return None


NEGATION_EXTRA = {"غير", "بلا", "عدم"}
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
    if _negation(tok, nxt_) or any(s in NEGATION_EXTRA for s in stems(tok)):
        return True
    low = str(raws[i] or "").lower().replace("’", "'").strip(".,!?؟…\"'«»")
    return low.endswith("n't") or bool(_negation(low))


def _value(n: dict):
    """A number's value; one the reader cannot read for sure («3²», «1/2») by its written form, so the same writing
    in both takes agrees and nothing else does."""
    return ("unsure", n.get("text")) if n.get("unsure") or n.get("value") is None else canon(n["value"])


_DRUGS = None


def _drug_index() -> dict:
    """term -> group of the shipped medicine names (lexicon.load_sources), read once."""
    global _DRUGS
    if _DRUGS is None:
        from .lexicon import load_sources
        _DRUGS = _lexicon_index(load_sources()["groups"])[0]
    return _DRUGS


def _base(tok: str) -> str:
    """A word without its clitics, its negation or its "n't" («للضغط» -> «ضغط», «مبيقللش» -> «بيقلل»)."""
    core = negated_core(tok)
    core = core[:-3] if core.endswith("n't") else core
    return _stems(core)[-1] if core else core


def _negated(toks: list, i: int) -> tuple:
    """(what the negation at i negates, the index after it): the negated word itself («مبيقللش» -> «بيقلل») or
    the words after it, small words and other negations skipped, two at most («مش بيقلل الضغط» -> («بيقلل», «ضغط»);
    «ما بيقللش الضغط» the same)."""
    t = toks[i]
    out = []
    if _negation(t) == "verb":
        out.append(_base(t))
    k, end = i + 1, i + 1
    while k < len(toks) and len(out) < 2:
        w = toks[k]
        k += 1
        if not w or w in _SMALL or _negation(w) == "word":
            continue
        core = negated_core(w, toks[k - 2]) if k >= 2 else w
        out.append(_base(core))
        end = k
    return tuple(out), end


def reading(words) -> dict:
    """{kind: [(key, words as said)]} for one take (a list of spoken words, as written in the transcript)."""
    raw = [_EDGE_PUNCT.sub("", str(w or "").strip()) for w in (words or [])]
    toks = [fold(str(w or "")) for w in (words or [])]     # folded from the word as written: «٣،» keeps its comma
    out = {"numbers": [], "negation": [], "timing": [], "condition": [], "claim": [], "negated": []}
    said = lambda a, b: " ".join(raw[a:b])                      # noqa: E731
    taken = set()
    for q in quantities(toks):
        out["numbers"].append(((q["kind"], _value(q)), said(q["start"], q["end"])))
        taken.update(range(q["start"], q["end"]))
    for n in find_numbers(toks):                               # a number word with no unit («خمسة», «ست»)
        if not taken & set(range(n["start"], n["end"])):
            kind = "everyday" if n["ambiguous"] else "number"
            out["numbers"].append(((kind, _value(n)), said(n["start"], n["end"])))
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
            what, end = _negated(toks, i)
            out["negation"].append((("not",) + what, raw[i]))
            out["negated"].append(said(i, end))
    used = set()
    for n in (3, 2):
        for i in range(len(toks) - n + 1):
            cond = CONDITION_PHRASES.get(tuple(toks[i:i + n]))
            if cond and not used & set(range(i, i + n)):
                out["condition"].append((("cond", cond), said(i, i + n)))
                used.update(range(i, i + n))
    for i, t in enumerate(toks):
        cond = CONDITIONS.get(t)
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if not cond or i in used or (cond == "if" and nxt in _PLEASE):
            continue
        if t in _BUT and (i == 0 or nxt in _BUT_ENDS):          # «بعد الأكل بس» (only) counts, «بس كده» not
            continue
        out["condition"].append((("cond", cond), raw[i]))
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
        per = _key(PERIOD, toks[i + 1]) if t in _EVERY and i + 1 < len(toks) and i + 1 not in timed \
            and not (i > 0 and PERIOD_BEFORE.get(toks[i - 1]) == "for") else None      # "for a week" is how long
        if per:
            out["timing"].append((("per", per), said(i, i + 2)))
            timed.update((i, i + 1))
        elif any(s in _PER_ADVERB for s in stems(t)):
            out["timing"].append((("per", _key(PERIOD, t)), raw[i]))
            timed.add(i)
    for i, t in enumerate(toks):                   # a period: which one («الشهر الجاي», "next week"), how long
        per = _key(PERIOD, t) if t and i not in timed and i not in taken else None
        if not per:
            continue
        j = i - 2 if i > 1 and toks[i - 1] in ("a", "an", "the") else i - 1      # "for a week"
        which = PERIOD_BEFORE.get(toks[j]) if j >= 0 and j not in timed and j not in taken else None
        a, b = (j, i + 1) if which else (i, i + 1)
        if not which and i + 1 < len(toks):
            which = PERIOD_AFTER.get(toks[i + 1])
            b = i + 2 if which else b
        out["timing"].append((("period", per, which), said(a, b)))
        timed.update(range(a, b))
    for i, t in enumerate(toks):                   # a meal or sleep said as an instruction («… وبعدين نامي»)
        meal = _key(EVENTS, t) if t and i not in timed and i not in taken else None
        if meal:
            out["timing"].append((("event", meal), raw[i]))
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
    for a, b, g in _drug_spans(toks, [False] * len(toks), _drug_index(), False, False):
        out["claim"].append((("drug", g if g is not None else " ".join(toks[a:b])), said(a, b)))
    for i, t in enumerate(toks):
        core = negated_core(t, toks[i - 1] if i else "")      # «مبيقللش» says «بيقلل»; the negation counts apart
        side = _key(OPPOSITES, core) if t else None
        organ = _key(ORGANS, core) if t else None
        if side:
            out["claim"].append((("says",) + side, raw[i]))
        elif organ:
            out["claim"].append((("organ", organ), raw[i]))
    return out


def compare(a_words, b_words) -> dict:
    """{} when two takes say the same numbers, negation and timing; else, per kind that differs, the words of each
    take that carry it ({"a": [...], "b": [...]}, as said, in order)."""
    ra, rb = reading(a_words), reading(b_words)
    _prefixed(a_words, b_words, ra)
    _prefixed(b_words, a_words, rb)
    out = {}
    for r, other in ((ra, rb), (rb, ra)):           # «واحد» (someone) counts only against a number in the other take
        if not other["numbers"]:
            r["numbers"] = [x for x in r["numbers"] if x[0][0] != "everyday"]
    for r, other in ((ra, rb), (rb, ra)):
        # an opposite word counts against the other side of its own scale only («آمن» / «خطر», not «كويس» added as
        # "well"), an organ against another organ («الكبد» / «الكلى»); a medicine always (a name said or not is a
        # different instruction)
        axes = {k[1] for k, _ in other["claim"] if k[0] == "says"}
        organs = any(k[0] == "organ" for k, _ in other["claim"])
        r["claim"] = [x for x in r["claim"] if x[0][0] == "drug" or (x[0][0] == "says" and x[0][1] in axes)
                      or (x[0][0] == "organ" and organs)]
    for kind in _ORDER:
        ca, cb = Counter(k for k, _ in ra[kind]), Counter(k for k, _ in rb[kind])
        if ca == cb:
            continue
        if kind == "negation":                 # every negation of each take; when both say the same words
            a, b = [s for _, s in ra[kind]], [s for _, s in rb[kind]]      # («مش» / «مش»), what each negates
            if sorted(a) == sorted(b):
                a, b = ra["negated"], rb["negated"]
            out[kind] = {"a": a, "b": b}
            continue
        out[kind] = {"a": _extra(ra[kind], cb), "b": _extra(rb[kind], ca)}
    return out


def _extra(items: list, other: Counter) -> list:
    """The words of this take whose meaning the other take does not say, in order: a key said twice here and once
    there names only the second («حباية واحدة … وحباية» against «حباية واحدة»: «وحباية»)."""
    left = Counter(other)
    out = []
    for k, said in items:
        if left[k]:
            left[k] -= 1
        else:
            out.append(said)
    return out


def _prefixed(mine, other, r: dict) -> None:
    """A word that is a word of the other take with a negating prefix ("unsafe" / "safe", "ineffective" /
    "effective") negates it: counted as a negation of this take."""
    theirs = {fold(w) for w in (other or [])}
    for w in mine or []:
        t = fold(w)
        if not t or t in theirs or not t.isascii():
            continue
        if any(t.startswith(p) and len(t) - len(p) >= 4 and t[len(p):] in theirs for p in NEG_PREFIXES):
            r["negation"].append((("not",), _EDGE_PUNCT.sub("", str(w or "").strip())))


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
