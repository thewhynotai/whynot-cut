# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Numbers, doses, units and durations in spoken words (K-T1; K-T6 reuses it for hook numbers).

Digits are Western, Arabic-Indic (٠-٩) or Persian (۰-۹); the decimal point is "." or the Arabic decimal separator «٫»
and is never dropped («3.5 مجم» stays 3.5, not 35 and not 3). A comma followed by exactly three digits groups thousands
(1,500); any other comma between digits is a decimal comma (3,5). «٣ ونص», "3 and a half" and «3½» are 3.5. Spelled
numbers are Egyptian and standard Arabic («خمسمية», «خمسميت», «ميتين وخمسين») and English ("five hundred"); dual
forms carry their 2 («حبايتين», «ساعتين»). Words that are also everyday words («ست» lady, «ميت» dead, «نص» text,
«واحد» someone, «سبع» lion) count as numbers only next to a unit or a time word.

The word lists are our own, written for this module from general Arabic and English usage."""
import re
import unicodedata

_DIAC = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ]")      # harakat, Quranic marks
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ـ": "",
                       **{chr(0x660 + i): str(i) for i in range(10)}, **{chr(0x6F0 + i): str(i) for i in range(10)},
                       "٫": ".", "٬": ",", "٪": "%"})
_VULGAR = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}
_EDGE = re.compile(r"^[^\w%.]+|[^\w%.]+$")
_CLITICS = ("وال", "بال", "فال", "لل", "ال", "و", "ب", "ف", "ل")


def _vulgar(s: str) -> str:
    """«3½» -> "3.5", «½» -> "0.5" (before NFKC, which would turn ½ into "1⁄2")."""
    def rep(m):
        v = (int(m.group(1)) if m.group(1) else 0) + _VULGAR[m.group(2)]
        return f"{v:g}"
    return re.sub(r"(\d*)([½¼¾⅓⅔])", rep, s.translate(_FOLD))


def fold(s) -> str:
    """One spoken token, compared form: NFKC, no diacritics or tatweel, one alef/ta marbuta/ya, Western digits, lower
    case, edge punctuation dropped (a decimal point inside a number is kept)."""
    s = _DIAC.sub("", unicodedata.normalize("NFKC", _vulgar(str(s or "")))).translate(_FOLD).lower().strip()
    s = _EDGE.sub("", s)
    if s in (".", ","):              # a decimal mark Whisper wrote as its own word ("3" "." "5")
        return s
    return s.rstrip(".") if not re.search(r"\d\.$", s) else s


def tokens(text) -> list:
    """A written text (a graphic, a hook) in folded tokens; "/" and a dash between numbers split («١٢٠/٨٠»)."""
    out = []
    for t in re.split(r"[\s/]+|(?<=\d)-(?=\d)", str(text or "")):
        f = fold(t)
        if f:
            out.append(f)
    return out


def stems(tok: str) -> list:
    """The token and the token without a leading Arabic clitic (و/ب/ف/ل/ال …), longest first, keeping 3+ letters."""
    out = [tok]
    for pre in _CLITICS:
        if tok.startswith(pre) and len(tok) - len(pre) >= 3:
            out.append(tok[len(pre):])
    return out


AR_UNITS = {"صفر": 0, "واحد": 1, "واحده": 1, "اتنين": 2, "اثنين": 2, "اثنان": 2, "تلاته": 3, "ثلاثه": 3, "تلات": 3,
            "ثلاث": 3, "اربعه": 4, "اربع": 4, "خمسه": 5, "خمس": 5, "سته": 6, "ست": 6, "سبعه": 7, "سبع": 7,
            "تمانيه": 8, "ثمانيه": 8, "تمن": 8, "ثمان": 8, "تسعه": 9, "تسع": 9, "عشره": 10, "عشر": 10,
            "حداشر": 11, "احداشر": 11, "احدعشر": 11, "اتناشر": 12, "اثناعشر": 12, "تلتاشر": 13, "ثلاثعشر": 13,
            "اربعتاشر": 14, "خمستاشر": 15, "ستاشر": 16, "سبعتاشر": 17, "تمنتاشر": 18, "تسعتاشر": 19,
            "عشرين": 20, "عشرون": 20, "تلاتين": 30, "ثلاثين": 30, "ثلاثون": 30, "اربعين": 40, "اربعون": 40,
            "خمسين": 50, "خمسون": 50, "ستين": 60, "ستون": 60, "سبعين": 70, "سبعون": 70, "تمانين": 80, "ثمانين": 80,
            "ثمانون": 80, "تسعين": 90, "تسعون": 90,
            "ميتين": 200, "مئتين": 200, "مائتين": 200, "مئتان": 200, "الفين": 2000, "الفان": 2000,
            "نص": 0.5, "نصف": 0.5, "ربع": 0.25, "تلت": 1 / 3, "ثلث": 1 / 3}
for _n, _forms in ((300, ("تلتميه", "تلاتميه", "ثلاثمائه", "ثلاثمئه", "تلتميت", "تلاتميت")),
                   (400, ("ربعميه", "اربعميه", "اربعمائه", "اربعمئه", "ربعميت", "اربعميت")),
                   (500, ("خمسميه", "خمسمائه", "خمسمئه", "خمسميت")),
                   (600, ("ستميه", "ستمائه", "ستمئه", "ستميت")),
                   (700, ("سبعميه", "سبعمائه", "سبعمئه", "سبعميت")),
                   (800, ("تمنميه", "تمانميه", "ثمانمائه", "ثمانمئه", "تمنميت", "تمانميت")),
                   (900, ("تسعميه", "تسعمائه", "تسعمئه", "تسعميت"))):
    AR_UNITS.update(dict.fromkeys(_forms, _n))
AR_HUNDRED = {"ميه", "مايه", "مائه", "مئه", "ميت"}
AR_THOUSAND = {"الف", "الاف", "تلاف"}
EN_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
            "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
            "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "half": 0.5, "quarter": 0.25}
EN_HUNDRED, EN_THOUSAND = {"hundred"}, {"thousand"}
# everyday words that are numbers only beside a unit or a time word
AMBIGUOUS = {"ست", "ميت", "نص", "نصف", "ربع", "تلت", "ثلث", "واحد", "واحده", "سبع", "تمن", "عشر", "خمس", "تسع", "one",
             "half", "quarter"}
# «٣ ونص», "3 and a half": a fraction joined to the number before it
AND_FRACTION = {"ونص": 0.5, "ونصف": 0.5, "وربع": 0.25, "وتلت": 1 / 3, "وثلث": 1 / 3}

UNITS = {"mg", "mcg", "μg", "ug", "g", "gm", "gram", "grams", "kg", "ml", "cc", "iu", "unit", "units", "%", "mmhg",
         "mmol", "tablet", "tablets", "pill", "pills", "capsule", "capsules", "drop", "drops", "puff", "puffs", "spoon",
         "spoons", "teaspoon", "teaspoons", "tablespoon", "tablespoons", "cm", "percent", "dose", "doses",
         "مجم", "ملجم", "مليجرام", "ملليجرام", "ملغ", "ملي", "مللي", "مل", "ملل", "ميكروجرام", "جرام", "جم", "كيلو",
         "لتر", "وحده", "وحدات", "حبايه", "حبايات", "حبه", "حبوب", "قرص", "اقراص", "كبسوله", "كبسولات", "نقطه", "نقط",
         "بخه", "بخات", "ملعقه", "معلقه", "معالق", "حقنه", "حقن", "امبول", "سم", "سنتي", "بالميه", "جرعه", "جرعات"}
TWO_WORD_UNITS = {("سي", "سي"), ("سم", "مكعب"), ("في", "الميه"), ("international", "units"), ("per", "cent")}
TIME = {"ساعه", "ساعات", "دقيقه", "دقايق", "دقائق", "يوم", "ايام", "اسبوع", "اسابيع", "شهر", "شهور", "اشهر", "سنه",
        "سنين", "سنوات", "مره", "مرات", "اليوم", "يوميا",
        "hour", "hours", "minute", "minutes", "day", "days", "week", "weeks", "month", "months", "year", "years",
        "time", "times", "daily", "weekly", "monthly", "hourly", "nightly", "night"}
# dual forms: the word itself says 2 («حبايتين» = two pills, «ساعتين» = two hours)
DUALS = {**dict.fromkeys(("حبايتين", "حبتين", "قرصين", "كبسولتين", "نقطتين", "بختين", "معلقتين", "ملعقتين",
                          "حقنتين", "جرعتين"), "dose"),
         **dict.fromkeys(("ساعتين", "يومين", "اسبوعين", "شهرين", "سنتين", "دقيقتين", "مرتين"), "duration")}
# a frequency on its own («مرتين», "twice", «يوميا»): a duration/frequency even without a number; the value it says
FREQUENCY = {"مرتين": 2, "twice": 2, "thrice": 3, "once": 1, "يوميا": None, "اسبوعيا": None, "شهريا": None,
             "daily": None, "weekly": None, "monthly": None, "hourly": None, "nightly": None}
# instructions of timing that are risky words in themselves
TIMING_PHRASES = [("يوم", "بعد", "يوم"), ("يوم", "ورا", "يوم"), ("قبل", "النوم"), ("بعد", "الاكل"), ("قبل", "الاكل"),
                  ("علي", "الريق"), ("بعد", "الفطار"), ("قبل", "الفطار"), ("بعد", "الغدا"), ("بعد", "العشا"),
                  ("every", "other", "day"), ("before", "bed"), ("after", "meals"), ("before", "meals"),
                  ("with", "food"), ("on", "an", "empty", "stomach")]
LINK = {"في", "كل", "a", "an", "per", "every", "each", "/"}


def _digit_value(tok: str):
    """'3.5' -> (3.5, ''), '1,500' -> 1500, '3,5' -> 3.5, '500mg' -> (500, 'mg'), '%70' -> (70, '%'). None when
    the token is not a number."""
    if re.fullmatch(r"%\d+(\.\d+)?", tok):
        v = _digit_value(tok[1:])
        return (v[0], "%") if v else None
    m = re.fullmatch(r"(\d+(?:[.,]\d+)*)(.*)", tok)
    if not m:
        return None
    num, rest = m.group(1), m.group(2)
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", num):
        num = num.replace(",", "")
    elif num.count(",") == 1 and "." not in num:
        num = num.replace(",", ".")
    if num.count(".") > 1 or "," in num:
        return None
    try:
        return float(num) if "." in num else int(num), rest.strip(".")
    except ValueError:
        return None


def _spelled(toks: list, i: int):
    """A spelled number starting at toks[i]: (value, tokens used) or None. Parts join with «و» («ميتين وخمسين») or
    "and"; «الف»/"thousand" multiplies what came before, «ميه»/"hundred" too when a small number came before."""
    total, cur, j, used = 0, 0, i, 0
    known = AR_UNITS.keys() | AR_HUNDRED | AR_THOUSAND
    while j < len(toks):
        t = toks[j]
        if used and t in ("و", "and") and j + 1 < len(toks) and (toks[j + 1] in known or toks[j + 1] in EN_UNITS) \
                and toks[j + 1] not in ("نص", "نصف", "ربع", "تلت", "ثلث", "half", "quarter"):
            j += 1
            continue
        base = t[1:] if used and t.startswith("و") and t[1:] in known and t not in AND_FRACTION else t
        if base in AR_UNITS or base in EN_UNITS:
            if used and base in ("نص", "نصف", "ربع", "تلت", "ثلث", "half", "quarter"):
                break                                  # a fraction after a number: _fraction_after adds it
            cur += AR_UNITS.get(base, EN_UNITS.get(base, 0))
        elif base in AR_HUNDRED or base in EN_HUNDRED:
            cur = (cur or 1) * 100
        elif base in AR_THOUSAND or base in EN_THOUSAND:
            total, cur = total + (cur or 1) * 1000, 0
        else:
            break
        used = j - i + 1
        j += 1
    if not used:
        return None
    return total + cur, used


def _fraction_after(toks: list, k: int):
    """(fraction, tokens used) for «ونص», «و نص», "and a half", "and half" at toks[k], else (0, 0)."""
    if k < len(toks) and toks[k] in AND_FRACTION:
        return AND_FRACTION[toks[k]], 1
    if k + 1 < len(toks) and toks[k] == "و" and toks[k + 1] in ("نص", "نصف", "ربع", "تلت", "ثلث"):
        return AR_UNITS[toks[k + 1]], 2
    if k + 2 < len(toks) and toks[k] == "and" and toks[k + 1] == "a" and toks[k + 2] in ("half", "quarter"):
        return EN_UNITS[toks[k + 2]], 3
    if k + 1 < len(toks) and toks[k] == "and" and toks[k + 1] in ("half", "quarter"):
        return EN_UNITS[toks[k + 1]], 2
    return 0, 0


def find_numbers(toks: list) -> list:
    """Every number in folded tokens: dicts {start, end (exclusive), value, kind: digits|spelled, unit_in_token,
    ambiguous}."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        dv = _digit_value(t)
        if dv is not None:
            val, rest = dv
            end = i + 1
            # Whisper may split a decimal: "3" "." "5", "3." "5", "3" ".5"
            if rest == "" and i + 2 < len(toks) and toks[i + 1] in (".", ",") and re.fullmatch(r"\d+", toks[i + 2]):
                val, end = float(f"{t}.{toks[i + 2]}"), i + 3
            elif t.endswith(".") and i + 1 < len(toks) and re.fullmatch(r"\d+", toks[i + 1]):
                val, end = float(f"{t[:-1]}.{toks[i + 1]}"), i + 2
            elif rest == "" and i + 1 < len(toks) and re.fullmatch(r"\.\d+", toks[i + 1]):
                val, end = float(f"{t}{toks[i + 1]}"), i + 2
            frac, n = _fraction_after(toks, end) if not rest else (0, 0)
            # "1.500" is 1.5 with a decimal point or 1500 with a dot grouping thousands: keep both readings
            digits = t[:len(t) - len(rest)] if rest else t
            alts = [int(digits.replace(".", ""))] if re.fullmatch(r"\d{1,3}\.\d{3}", digits) else []
            out.append({"start": i, "end": end + n, "value": val + frac, "kind": "digits",
                        "unit_in_token": rest or None, "ambiguous": False, "alts": alts})
            i = end + n
            continue
        sp = _spelled(toks, i)
        if sp:
            val, n = sp
            frac, m = _fraction_after(toks, i + n)
            out.append({"start": i, "end": i + n + m, "value": val + frac, "kind": "spelled", "unit_in_token": None,
                        "ambiguous": n == 1 and not m and t in AMBIGUOUS})
            i += n + m
            continue
        i += 1
    return out


def is_unit(tok: str) -> bool:
    return any(s in UNITS for s in stems(tok))


def is_time(tok: str) -> bool:
    return any(s in TIME or DUALS.get(s) == "duration" for s in stems(tok))


def is_frequency(tok: str) -> bool:
    return any(s in FREQUENCY for s in stems(tok))


def frequency_value(tok: str):
    for s in stems(tok):
        if s in FREQUENCY:
            return FREQUENCY[s]
    return None


def _unit_len(toks: list, k: int) -> int:
    """How many tokens at toks[k] make a unit: 2 for «سي سي», 1 for «مجم», 0 for none."""
    if k + 1 < len(toks) and (toks[k], toks[k + 1]) in TWO_WORD_UNITS:
        return 2
    return 1 if k < len(toks) and is_unit(toks[k]) else 0


def quantities(toks: list) -> list:
    """Numbers with what goes with them: {start, end, value, kind: dose|duration|number}. A unit right after the
    number (or fused into it, or right before it: «حباية واحدة») makes a dose; a time word within two tokens
    («٨ ساعات», «مرة في اليوم») a duration; a dual form («حبايتين», «ساعتين») is 2 of its own kind. An everyday
    word that is also a number («ست», «نص») is kept only with a unit or a time word."""
    out, taken = [], set()
    for n in find_numbers(toks):
        start, end, kind = n["start"], n["end"], "number"
        u = _unit_len(toks, end)
        if n["unit_in_token"] and is_unit(n["unit_in_token"]):
            kind = "dose"
        elif u:
            kind, end = "dose", end + u
        elif start > 0 and is_unit(toks[start - 1]) and start - 1 not in taken:
            kind, start = "dose", start - 1
        else:
            for k in (end, end + 1):
                if k < len(toks) and is_time(toks[k]) and (k == end or toks[end] in LINK):
                    kind, end = "duration", k + 1
                    break
        if kind == "number" and n["ambiguous"]:
            continue
        # «مرتين في اليوم», "twice a day", «كل ٨ ساعات»: take the frequency tail too
        if end + 1 < len(toks) and toks[end] in LINK and is_time(toks[end + 1]):
            end += 2
        out.append({"start": start, "end": end, "value": n["value"], "kind": kind, "alts": n.get("alts") or []})
        taken.update(range(start, end))
    for i, t in enumerate(toks):
        if i in taken:
            continue
        frac, m = _fraction_after(toks, i + 1)
        if is_unit(t) and m:                       # «حباية ونص»: one and a half pills
            out.append({"start": i, "end": i + 1 + m, "value": 1 + frac, "kind": "dose"})
            taken.update(range(i, i + 1 + m))
            continue
        if any(s in ("مره", "time") for s in stems(t)) and i + 2 < len(toks) and toks[i + 1] in LINK                 and is_time(toks[i + 2]):          # «مرة في اليوم», «مرة كل يومين»: once a day
            end = i + 3
            out.append({"start": i, "end": end, "value": 1, "kind": "duration"})
            taken.update(range(i, end))
            continue
        kind = next((DUALS[s] for s in stems(t) if s in DUALS), None)
        if kind:
            end = i + 1
            if end + 1 < len(toks) and toks[end] in LINK and is_time(toks[end + 1]):
                end += 2
            out.append({"start": i, "end": end, "value": 2, "kind": kind})
            taken.update(range(i, end))
    return sorted(out, key=lambda q: q["start"])


def timing_phrases(toks: list) -> list:
    """(start, end) of timing instructions («قبل النوم», «يوم بعد يوم», "with food")."""
    out = []
    for ph in TIMING_PHRASES:
        n = len(ph)
        for i in range(len(toks) - n + 1):
            if all(ph[k] in stems(toks[i + k]) for k in range(n)):
                out.append((i, i + n))
    return sorted(out)


def values_in(text: str) -> set:
    """Every number value said or written in a text (digits of any script, spelled, dual forms, «مرتين»), for
    comparing a hook or a graphic with the speech: «٣٫٥» == "3.5" == 3.5, «خمسمية» == "500", «نص حباية» == 0.5. An
    everyday word that is also a number counts only beside a unit or a time word, as in speech."""
    toks = tokens(text)
    vals = {canon(v) for q in quantities(toks) for v in [q["value"], *q.get("alts", [])]}
    vals |= {canon(v) for t in toks if (v := frequency_value(t)) is not None}
    return vals


def canon(v):
    return int(v) if float(v).is_integer() else round(float(v), 4)
