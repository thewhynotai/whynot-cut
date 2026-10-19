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
import math
import re

from ..cut_proposals_norm import prepare, strip_marks

_DIAC = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ]")      # harakat, Quranic marks
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ـ": "",
                       **{chr(0x660 + i): str(i) for i in range(10)}, **{chr(0x6F0 + i): str(i) for i in range(10)},
                       "٫": ".", "٬": ",", "٪": "%"})
_VULGAR = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅕": 0.2, "⅖": 0.4, "⅗": 0.6, "⅘": 0.8, "⅙": 1 / 6,
           "⅚": 5 / 6, "⅐": 1 / 7, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875, "⅑": 1 / 9, "⅒": 0.1}
FRAC = "_frac"           # a fraction written on its own («½», «3⁄4»): «3 ½» (two words) is 3.5, not 3 and 0.5
# superscript and subscript digits are never digits («3²» is not 32): a marker NFKC leaves alone, read as unsure
# «⅟» (one over) and «↉» (zero thirds) would become "1⁄" and "0⁄3" under NFKC and join the digits around them:
# marked too, so «1⅟2» is unsure, never 11/2
_SCRIPTS = str.maketrans({**{c: f"_sup{i}" for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")},
                          **{chr(0x2080 + i): f"_sub{i}" for i in range(10)}, "⅟": "_odd1", "↉": "_odd0"})
_EDGE = re.compile(r"^[^\w%.]+|[^\w%.]+$")
_CLITICS = ("وال", "بال", "فال", "لل", "ال", "و", "ب", "ف", "ل")


def _vulgar(s: str) -> str:
    """Written fractions and the marks a number is read by, before NFKC (which would turn ½ into "1⁄2" and ² into 2),
    after the hidden marks are gone («3‏½» is 3.5, not "3" + "0.5" = 30.5):
    - «3½» -> "3.5", «3⁄4» (the fraction slash) -> "0.75", «⅕» -> "0.2"; on its own a fraction carries FRAC, so the
      whole number said before it adds up («3 ½» = 3.5);
    - «٣،٥» (the Arabic comma between digits) is a decimal point -> "3.5"; before exactly three digits («٣،٥٠٠») it may
      group thousands too, so it stays and the number is read as unsure;
    - superscript and subscript digits become a marker, never digits («3²» is unsure, not 32)."""
    def vulgar(m):
        v = (int(m.group(1)) if m.group(1) else 0) + _VULGAR[m.group(2)]
        return f"{v:g}" + ("" if m.group(1) else FRAC)

    def slash(m):
        den = int(m.group(2))
        return f"{int(m.group(1)) / den:g}{FRAC}" if den else m.group(0)
    s = strip_marks(s).translate(_FOLD).translate(_SCRIPTS)
    s = re.sub(r"(?<=\d)،(?=\d{1,2}(?!\d)|\d{4,})", ".", s)
    s = re.sub(r"(?<![\d.])(\d+)⁄(\d+)(?![\d.])", slash, s)
    return re.sub(r"(\d*)([" + "".join(_VULGAR) + "])", vulgar, s)


def fold(s) -> str:
    """One spoken token, compared form: the shared normaliser (`cut_proposals_norm.prepare`: NFKC, bidi and zero-width
    marks dropped, ؤ ئ ی ک unified), no diacritics or tatweel, one alef/ta marbuta/ya, Western digits, lower case,
    edge punctuation dropped (a decimal point inside a number is kept)."""
    s = _DIAC.sub("", prepare(_vulgar(str(s or "")))).translate(_FOLD).lower().strip()
    if s in ("،", ",", "٬"):          # a comma on its own, between two numbers maybe («٣ ، ٥»)
        return ","
    if _MINUS.fullmatch(s):          # a minus on its own («- 5 mg»)
        return "-"
    if s in ("/", "⁄"):              # a slash on its own: «١ / ٢» (a half, said apart), "5 mg / day"
        return "/"
    minus = bool(re.match(r"[-−‐‒–](?=\d)", s))        # «-5 مجم»: never read as 5
    lead = bool(re.match(r"[،,٬](?=\d)", s))            # "3 ,5": the comma starts the next word
    comma = bool(re.search(r"\d[،,٬]$", s))              # «٣، ٥»: the comma stays, the reader decides
    slash_lead = bool(re.match(r"[/⁄](?=\d)", s))       # «١ /٢», «١/ ٢»: the slash stays, the reader decides
    slash_end = bool(re.search(r"\d[/⁄]$", s))
    s = _EDGE.sub("", s)
    if minus and s[:1].isdigit():
        s = "-" + s
    if lead and s[:1].isdigit():
        s = "," + s
    if comma and s[-1:].isdigit():
        s += ","
    if slash_lead and s[:1].isdigit():
        s = "/" + s
    if slash_end and s[-1:].isdigit():
        s += "/"
    if s in (".", ","):              # a decimal mark Whisper wrote as its own word ("3" "." "5")
        return s
    return s.rstrip(".") if not re.search(r"\d\.$", s) else s


_MINUS = re.compile("[-−‐‒–]")       # the minus signs and dashes a number may carry
_HOLD = chr(0x2215)      # holds a "/" that must not split while the text is split


SPLIT = "|"              # between two numbers the writer split («١٢٠/٨٠», «٣-٤»): two numbers, never one said apart


def tokens(text) -> list:
    """A written text (a graphic, a hook) in folded tokens; "/" and a dash between numbers split («١٢٠/٨٠», a reading
    of two numbers; SPLIT marks the place, so the two are never read as one number said apart), except a smaller
    number over a bigger one («1/2», «١ / ٢»: a half, a date or a score), kept whole and so read as unsure."""
    out, split = [], False
    text = re.sub(r"(?<![\d/])(?<!/\s)(\d+)\s*/\s*(\d+)(?!\s*[\d/])", lambda m: f"{m.group(1)}{_HOLD}{m.group(2)}"
                  if int(m.group(1)) < int(m.group(2)) else m.group(0), prepare(_vulgar(str(text or ""))))
    for k, t in enumerate(re.split(r"((?<=\d)\s*-\s*(?=\d)|[\s/]+)", text)):   # marks out first: «١٢٠‏-‏٨٠»
        if k % 2:
            split = split or "/" in t or "-" in t
            continue
        f = fold(t.replace(_HOLD, "/"))
        if f:
            if split and out and out[-1][:1].isdigit() and f[:1].isdigit():
                out.append(SPLIT)
            out.append(f)
            split = False
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
            "مليونين": 2000000, "تلاتلاف": 3000, "تلتلاف": 3000, "اربعتلاف": 4000, "ربعتلاف": 4000,
            "خمستلاف": 5000, "ستلاف": 6000, "ستتلاف": 6000, "سبعتلاف": 7000, "تمنتلاف": 8000, "تمانتلاف": 8000,
            "تسعتلاف": 9000, "عشرتلاف": 10000,
            "نص": 0.5, "نصف": 0.5, "ربع": 0.25, "تلت": 1 / 3, "ثلث": 1 / 3, "تلتين": 2 / 3, "ثلثين": 2 / 3,
            "ثلثي": 2 / 3, "ثلثا": 2 / 3}
for _n, _forms in ((300, ("تلتميه", "تلاتميه", "ثلاثمائه", "ثلاثمئه", "تلتميت", "تلاتميت")),
                   (400, ("ربعميه", "اربعميه", "اربعمائه", "اربعمئه", "ربعميت", "اربعميت")),
                   (500, ("خمسميه", "خمسمائه", "خمسمئه", "خمسميت")),
                   (600, ("ستميه", "ستمائه", "ستمئه", "ستميت")),
                   (700, ("سبعميه", "سبعمائه", "سبعمئه", "سبعميت")),
                   (800, ("تمنميه", "تمانميه", "ثمانمائه", "ثمانمئه", "تمنميت", "تمانميت")),
                   (900, ("تسعميه", "تسعمائه", "تسعمئه", "تسعميت"))):
    AR_UNITS.update(dict.fromkeys(_forms, _n))
AR_UNITS = {fold(k): v for k, v in AR_UNITS.items()}       # the lists are matched in fold()'s form («مئتين» → «ميتين»)
AR_HUNDRED = {fold(w) for w in ("ميه", "مايه", "مائه", "مئه", "ميت")}
AR_THOUSAND = {"الف", "الاف", "تلاف"}
# what a number before it is multiplied by: «٥ آلاف» 5000, «٥٠ ألف» 50 000, «٢ مليون» 2 000 000, "1.2 million"
SCALES = {**dict.fromkeys(AR_THOUSAND | {"thousand", "thousands"}, 1000),
          **dict.fromkeys(("مليون", "ملايين", "million", "millions"), 10 ** 6),
          **dict.fromkeys(("مليار", "مليارات", "billion", "billions"), 10 ** 9)}
# a count of parts after a number («تلاتة أرباع», «تلت تربع», "three quarters", "two thirds"): which whole the parts
# are of is not said for sure («تلت» is a third or a spoken three), so the number is read as unsure, never a guess
PLURAL_FRACTIONS = {"ارباع", "تربع", "اتلات", "اثلاث", "اخماس", "اسداس", "اتمان", "اثمان", "اعشار", "quarters",
                    "thirds", "fifths", "sixths", "eighths", "tenths"}
# a vague amount said before a count noun («كام حباية», «كذا حباية», "a few tablets"): an amount, never one
VAGUE = {"كام", "كذا", "شويه", "بعض", "عده", "few", "several", "some", "many", "multiple", "couple"}
EN_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
            "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
            "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "half": 0.5, "quarter": 0.25,
            "double": 2, "triple": 3}
EN_HUNDRED, EN_THOUSAND = {"hundred"}, {"thousand"}
# everyday words that are numbers only beside a unit or a time word
AMBIGUOUS = {"ست", "ميت", "نص", "نصف", "ربع", "تلت", "ثلث", "واحد", "واحده", "سبع", "تمن", "عشر", "خمس", "تسع", "one",
             "half", "quarter", "double", "triple", "ميه"}          # «اشربي مية»: water, not 100
# «٣ ونص», "3 and a half": a fraction joined to the number before it
AND_FRACTION = {"ونص": 0.5, "ونصف": 0.5, "وربع": 0.25, "وتلت": 1 / 3, "وثلث": 1 / 3}

UNITS = {"mg", "mcg", "μg", "ug", "g", "gm", "gram", "grams", "kg", "ml", "cc", "iu", "unit", "units", "%", "mmhg",
         "mmol", "tablet", "tablets", "pill", "pills", "capsule", "capsules", "drop", "drops", "puff", "puffs", "spoon",
         "spoons", "teaspoon", "teaspoons", "tablespoon", "tablespoons", "cm", "percent", "dose", "doses",
         "مجم", "ملجم", "مليجرام", "ملليجرام", "ملغ", "ملي", "مللي", "مل", "ملل", "ميكروجرام", "جرام", "جم", "كيلو",
         "لتر", "وحده", "وحدات", "حبايه", "حبايات", "حبه", "حبوب", "قرص", "اقراص", "كبسوله", "كبسولات", "نقطه", "نقط",
         "بخه", "بخات", "ملعقه", "معلقه", "معالق", "حقنه", "حقن", "امبول", "سم", "سنتي", "بالميه", "جرعه", "جرعات",
         "قطره", "قطرات", "لبوس", "injection", "injections", "milligram", "milligrams", "microgram", "micrograms",
         "kilo", "kilogram", "kilograms", "liter", "liters", "litre", "litres", "milliliter", "milliliters",
         "millilitre", "millilitres", "مكجم", "ميكرو", "كجم", "كيلوجرام", "ملليلتر", "mgs", "مج", "ملغم", "tsp",
         "tbsp", "cup", "cups", "glass", "glasses", "كوب", "كوبايه", "كوبايات", "فنجان", "فناجين", "كيس", "اكياس",
         "ساشيه", "sachet", "sachets"}
TWO_WORD_UNITS = {("سي", "سي"), ("سم", "مكعب"), ("في", "الميه"), ("international", "units"), ("per", "cent"),
                  ("ميكرو", "جرام")}
# what a unit measures: two writings of one unit compare the same («مجم» = "mg", «حباية» = «قرص» = "pill"), two
# units never do («مجم» / «جم», "mg" / "mcg", pill / capsule, teaspoon / tablespoon); «ملي» alone (ml or mg?) is its
# own
_UNIT_CLASS = {"mg": ("mg", "mgs", "milligram", "milligrams", "مجم", "ملجم", "مليجرام", "ملليجرام", "ملغ", "مج",
                      "ملغم"),
               "mcg": ("mcg", "μg", "ug", "microgram", "micrograms", "ميكروجرام", "مكجم", "ميكرو"),
               "g": ("g", "gm", "gram", "grams", "جرام", "جم"), "kg": ("kg", "kilo", "kilogram", "kilograms", "كيلو",
                                                                       "كجم", "كيلوجرام"),
               "ml": ("ml", "cc", "milliliter", "milliliters", "millilitre", "millilitres", "مل", "ملل", "ملليلتر"),
               "milli": ("ملي", "مللي"), "l": ("لتر", "liter", "liters", "litre", "litres"),
               "iu": ("iu", "unit", "units", "وحده", "وحدات"), "percent": ("%", "percent", "بالميه"),
               "tablet": ("tablet", "tablets", "pill", "pills", "حبايه", "حبايات", "حبه", "حبوب", "قرص", "اقراص"),
               "capsule": ("capsule", "capsules", "كبسوله", "كبسولات"),
               "drop": ("drop", "drops", "نقطه", "نقط", "قطره", "قطرات"), "puff": ("puff", "puffs", "بخه", "بخات"),
               "spoon": ("spoon", "spoons", "ملعقه", "معلقه", "معالق"), "teaspoon": ("teaspoon", "teaspoons", "tsp"),
               "tablespoon": ("tablespoon", "tablespoons", "tbsp"), "cup": ("cup", "cups", "كوب", "كوبايه", "كوبايات"),
               "glass": ("glass", "glasses"), "fincan": ("فنجان", "فناجين"),
               "sachet": ("كيس", "اكياس", "ساشيه", "sachet", "sachets"), "injection": ("injection", "injections", "حقنه", "حقن"),
               "ampoule": ("امبول",), "suppository": ("لبوس",), "dose": ("dose", "doses", "جرعه", "جرعات"),
               "cm": ("cm", "سم", "سنتي")}
UNIT_CLASS = {fold(w): k for k, words in _UNIT_CLASS.items() for w in words}
TWO_WORD_CLASS = {("سي", "سي"): "ml", ("سم", "مكعب"): "ml", ("في", "الميه"): "percent", ("international", "units"): "iu",
                  ("per", "cent"): "percent", ("ميكرو", "جرام"): "mcg"}
# a spoon's size said after it («معلقة صغيرة» a teaspoon, «معلقة كبيرة» a tablespoon)
SPOON_SIZE = {"صغيره": "teaspoon", "صغير": "teaspoon", "شاي": "teaspoon", "كبيره": "tablespoon", "كبير": "tablespoon",
              "اكل": "tablespoon", "شوربه": "tablespoon"}
# a dose by body weight: «٥ مجم لكل كيلو», "5 mg per kg", "5 mg / kg"
PER_WEIGHT = {"لكل", "كل", "per", "a", "/"}
KILO = {"كيلو", "كجم", "كيلوجرام", "kg", "kilo", "kilogram"}
TIME = {"ساعه", "ساعات", "دقيقه", "دقايق", "دقائق", "يوم", "ايام", "اسبوع", "اسابيع", "شهر", "شهور", "اشهر", "سنه",
        "سنين", "سنوات", "مره", "مرات", "اليوم", "يوميا", "يوما", "اياما", "اسبوعا", "شهرا", "عام", "عاما",
        "اعوام",
        "hour", "hours", "minute", "minutes", "day", "days", "week", "weeks", "month", "months", "year", "years",
        "time", "times", "daily", "weekly", "monthly", "hourly", "nightly", "night",
        # the short forms a transcript writes ("2 hrs", "5 min"); "h", "m" and "d" are left out: «vitamin D», "5 m"
        "hr", "hrs", "min", "mins", "sec", "secs", "seconds", "wk", "wks", "yr", "yrs"}
TIME = {fold(w) for w in TIME}
# which period a duration counts («خمس أيام» / «خمس أسابيع»)
_TIME_CLASS = {"hour": ("ساعه", "ساعات", "hour", "hours", "hourly", "ساعتين", "hr", "hrs"),
               "minute": ("دقيقه", "دقايق", "دقائق", "minute", "minutes", "دقيقتين", "min", "mins"),
               "second": ("sec", "secs", "seconds"),
               "day": ("يوم", "ايام", "اليوم", "يوميا", "يوما", "اياما", "day", "days", "daily", "يومين"),
               "week": ("اسبوع", "اسابيع", "اسبوعا", "week", "weeks", "weekly", "اسبوعين", "wk", "wks"),
               "month": ("شهر", "شهور", "اشهر", "شهرا", "month", "months", "monthly", "شهرين"),
               "year": ("سنه", "سنين", "سنوات", "عام", "عاما", "اعوام", "year", "years", "سنتين", "yr", "yrs"),
               "times": ("مره", "مرات", "time", "times", "مرتين"), "night": ("night", "nightly")}
TIME_CLASS = {fold(w): k for k, words in _TIME_CLASS.items() for w in words}
# dual forms: the word itself says 2 («حبايتين» = two pills, «ساعتين» = two hours)
DUALS = {**dict.fromkeys(("حبايتين", "حبتين", "قرصين", "كبسولتين", "نقطتين", "بختين", "معلقتين", "ملعقتين",
                          "حقنتين", "جرعتين", "قطرتين"), "dose"),
         **dict.fromkeys(("ساعتين", "يومين", "اسبوعين", "شهرين", "سنتين", "دقيقتين", "مرتين"), "duration")}
DUAL_UNIT = {"حبايتين": "tablet", "حبتين": "tablet", "قرصين": "tablet", "كبسولتين": "capsule", "نقطتين": "drop",
             "قطرتين": "drop", "بختين": "puff", "معلقتين": "spoon", "ملعقتين": "spoon", "حقنتين": "injection",
             "جرعتين": "dose", "كيسين": "sachet", "كوبايتين": "cup", "كوبين": "cup", "فنجانين": "fincan"}
DUALS.update(dict.fromkeys(("كيسين", "كوبايتين", "كوبين", "فنجانين"), "dose"))
# a frequency on its own («مرتين», "twice", «يوميا»): a duration/frequency even without a number; the value it says
FREQUENCY = {"مرتين": 2, "twice": 2, "thrice": 3, "once": 1, "يوميا": None, "اسبوعيا": None, "شهريا": None,
             "daily": None, "weekly": None, "monthly": None, "hourly": None, "nightly": None}
# instructions of timing that are risky words in themselves
TIMING_PHRASES = [("يوم", "بعد", "يوم"), ("يوم", "ورا", "يوم"), ("قبل", "النوم"), ("بعد", "الاكل"), ("قبل", "الاكل"),
                  ("علي", "الريق"), ("بعد", "الفطار"), ("قبل", "الفطار"), ("بعد", "الغدا"), ("بعد", "العشا"),
                  ("every", "other", "day"), ("before", "bed"), ("after", "meals"), ("before", "meals"),
                  ("with", "food"), ("on", "an", "empty", "stomach")]
LINK = {"في", "كل", "a", "an", "per", "every", "each", "/"}
ARTICLES = {"a", "an", "the"}
# a dose counted by its noun alone («خدي حباية» is one pill): the singular count nouns, folded
COUNT_NOUNS = {"حبايه", "قرص", "كبسوله", "بخه", "حقنه", "جرعه", "معلقه", "ملعقه", "امبول", "لبوس", "قطره",
               "كوبايه", "فنجان", "كيس", "ساشيه",
               "tablet", "pill", "capsule", "dose", "puff", "spoon", "teaspoon", "tablespoon", "injection", "drop",
               "cup", "glass", "sachet"}
# which one, not how many: «الحباية دي», «كل حباية», «أي حباية», «نفس الحباية»
POINTERS = {"دي", "ده", "دا", "دول", "ديه", "كل", "اي", "نفس", "هذه", "هذا"}
_ARABIC_LETTER = re.compile("[ء-ي]")


def _digit_value(tok: str):
    """'3.5' -> (3.5, ''), '1,500' -> 1500, '3,5' -> 3.5, '500mg' -> (500, 'mg'), '%70' -> (70, '%'), '½' alone ->
    (0.5, FRAC). None when the token is not a number. (None, rest) when it is one the reader cannot read for sure:
    more digits after other marks («3..5», «1/2», «3²», «٣،٥٠٠», "3,5,7", "1.2.3"): a misread dose is worse than none,
    so the editor checks it (never a guess)."""
    if re.fullmatch(r"%\d+(\.\d+)?", tok):
        v = _digit_value(tok[1:])
        return (v[0], "%") if v else None
    if re.match(r"[-,/]\d|\.{2,}\d", tok):               # a minus, a leading comma or slash, two dots: not for sure
        return None, tok
    if re.match(r"\.\d", tok):                            # «.5 mg», «٫٥ مجم»: 0.5
        tok = "0" + tok
    m = re.fullmatch(r"(\d+(?:[.,]\d+)*)(.*)", tok)
    if not m:
        return None
    num, rest = m.group(1), m.group(2)
    if re.search(r"\d", rest):
        return None, rest
    if rest in SCALES:                                      # «٥٠ألف»: 50 000, as «٥٠ ألف»
        v = _digit_value(num)
        return (v[0] * SCALES[rest] if v and v[0] is not None else None), ""
    if rest in AND_FRACTION:                                # «٣ونص»: 3.5, as «٣ ونص»; «١٠٠ونص» 100.5 or 150?
        v = _digit_value(num)
        return (v[0] + AND_FRACTION[rest] if v and v[0] is not None and v[0] < 100 else None), ""
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", num):
        num = num.replace(",", "")
    elif num.count(",") == 1 and "." not in num:
        num = num.replace(",", ".")
    if num.count(".") > 1 or "," in num:
        return None, rest
    try:
        v = float(num) if "." in num else int(num)
        return (v if not isinstance(v, float) or math.isfinite(v) else None), rest.strip(".,")
    except ValueError:
        return None, rest


_FRACTION_WORDS = {"نص", "نصف", "ربع", "تلت", "ثلث", "half", "quarter"}
# a count said in the plural: after a fraction word («تلت حبايات», «تلت ساعات») the fraction word is a spoken three
# or a third, not for sure
PLURAL_NOUNS = {"حبايات", "اقراص", "كبسولات", "نقط", "قطرات", "بخات", "معالق", "جرعات", "حقن", "وحدات", "ايام",
                "اسابيع", "شهور", "ساعات", "سنين", "دقايق", "مرات", "tablets", "pills", "capsules", "drops", "doses",
                "days", "weeks", "hours", "months", "years", "times"}


def _spelled(toks: list, i: int):
    """A spelled number starting at toks[i]: (value, tokens used, bare, odd) or None. Parts join with «و» («ميتين
    وخمسين») or "and"; «الف» / "thousand" / «مليون» multiplies what came before («نص مليون», "half a million"),
    «ميه» / "hundred" too when a small number came before; after a scale the next part may come without «و» («ألف
    خمسمية»), and digits smaller than it join it after «و» («ألف و ٥٠٠», «ألف و500»). bare: the number is one scale word
    alone («مية», «ألف», «مليون»), so a half said after it is half of it («مية ونص» is 150). odd: the words do not make
    one number for sure, the reader stops there and the number is unsure: two small numbers said together («تلاتة
    أربعة» three or four, "three four"; "twenty five" is one), a hundred or a scale said twice («مية مية», «ألف
    ألف»), «تلت» / «ثلث» before a hundred or a scale («تلت تلاف»: a third or a spoken three?), digits after a scale
    with no «و» («ألف ٥٠٠»)."""
    total, cur, j, used = 0, 0, i, 0
    small = None                      # the scale of the last part: digits after it must be smaller
    joined = False                    # «و» / "and" came right before this part
    last = None                       # the last part read
    known = AR_UNITS.keys() | AR_HUNDRED | SCALES.keys()

    def digits(t):
        return int(t) if small and re.fullmatch(r"\d+", t) and int(t) < small else None
    while j < len(toks):
        t = toks[j]
        if used and t in ("و", "and") and j + 1 < len(toks) and (toks[j + 1] in known or toks[j + 1] in EN_UNITS
                                                                   or digits(toks[j + 1]) is not None) \
                and toks[j + 1] not in _FRACTION_WORDS:
            j, joined = j + 1, True
            continue
        if used and t == "a" and last in ("half", "quarter") and j + 1 < len(toks) \
                and (toks[j + 1] in SCALES or toks[j + 1] in EN_HUNDRED):
            j += 1                                     # "half a million"
            continue
        glued = used and t.startswith("و") and (t[1:] in known or digits(t[1:]) is not None) and t not in AND_FRACTION
        base = t[1:] if glued else t
        joined = joined or glued
        if used and re.fullmatch(r"\d+", base):
            if digits(base) is None or not joined:     # «ألف ٥٠٠», «تلاتة ٤»: not one number for sure
                return total + cur, j - i + 1, False, True
            cur, small = cur + int(base), 1
        elif base in AR_UNITS or base in EN_UNITS:
            if used and base in _FRACTION_WORDS:
                break                                  # a fraction after a number: _fraction_after adds it
            v = AR_UNITS.get(base, EN_UNITS.get(base, 0))
            tens = last in EN_UNITS and EN_UNITS[last] in (20, 30, 40, 50, 60, 70, 80, 90) and base in EN_UNITS \
                and 1 <= v <= 9                        # "twenty five"
            if used and not joined and small == 1 and v < 100 and not tens:
                return total + cur, j - i + 1, False, True       # «تلاتة أربعة», "three four": a range
            cur += v
            small = 1000 if v >= 1000 else 100 if v >= 100 and v % 100 == 0 else 1
        elif base in AR_HUNDRED or base in EN_HUNDRED:
            if cur >= 100 or last in ("تلت", "ثلث"):
                return total + cur, j - i + 1, False, True       # «مية مية», «تلت مية»
            cur, small = (cur or 1) * 100, 100
        elif base in SCALES:
            if used and (not cur or joined) or last in ("تلت", "ثلث"):
                return total + cur, j - i + 1, False, True       # «ألف ألف», «تلت تلاف», «خمسمية وألف»
            total, cur, small = total + (cur or 1) * SCALES[base], 0, SCALES[base]
        else:
            break
        used, last, joined = j - i + 1, base, False
        j += 1
    if not used:
        return None
    return total + cur, used, used == 1 and (toks[i] in AR_HUNDRED or toks[i] in EN_HUNDRED or toks[i] in SCALES), \
        False


def _scaled(toks: list, k: int, val):
    """(value, end, odd) for a scale word at toks[k] after a number said in digits («٥ آلاف» 5000, «٥٠ ألف», "1.2
    million") and a smaller number joined to it («٥ آلاف و ٥٠٠», «٥ آلاف وخمسمية», «٢ مليون و ٥٠٠ ألف»); (val, k,
    False) when none is there. odd: digits right after the scale with no «و» («٥ آلاف ٥٠٠»): unsure."""
    if k >= len(toks) or toks[k] not in SCALES:
        return val, k, False
    scale = SCALES[toks[k]]
    val, k = val * scale, k + 1
    if k < len(toks) and re.fullmatch(r"\d+", toks[k]):
        return val, k + 1, True
    j = k + 1 if k < len(toks) and toks[k] in ("و", "and") else k
    if j < len(toks) and (j > k or toks[j].startswith("و")):
        part = toks[j] if j > k else toks[j][1:]
        if re.fullmatch(r"\d+", part) and int(part) < scale:
            nxt = toks[j + 1] if j + 1 < len(toks) else ""
            if nxt in SCALES and SCALES[nxt] < scale:  # «٢ مليون و ٥٠٠ ألف»
                return val + int(part) * SCALES[nxt], j + 2, False
            return val + int(part), j + 1, False
        sp = _spelled([part] + toks[j + 1:], 0) if part not in _FRACTION_WORDS else None
        if sp and sp[0] < scale:
            return val + sp[0], j + sp[1], sp[3]
    return val, k, False


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


def _joined_digits(toks: list, k: int, value) -> int:
    """Tokens of «و 500» / «و500» / "and 500" at toks[k] after a whole number below 100 or a round one («1000 و 500»,
    «خمسة و٢٠», «٥ و ٢٠»): 1500 / 25 or two numbers is not said for sure; 0 when no such tail is there."""
    if not isinstance(value, int) or isinstance(value, bool) or (value >= 100 and value % 100):
        return 0
    nxt = toks[k] if k < len(toks) else ""
    if nxt in ("و", "and") and k + 1 < len(toks) and re.fullmatch(r"\d+", toks[k + 1]):
        return 2
    return 1 if re.fullmatch(r"و\d+", nxt) else 0


def _unsure(toks: list, start: int, end: int, kind: str) -> dict:
    """A number that is said but cannot be read for sure: no value, flagged for the editor (never a guess)."""
    return {"start": start, "end": end, "value": None, "kind": kind, "unit_in_token": None, "ambiguous": False,
            "alts": [], "unsure": True, "text": " ".join(toks[start:end])}


# two halves, two quarters («نصين حباية», «ربعين»): a whole or a half? unsure
DUAL_FRACTIONS = {"نصين", "ربعين"}


GLUED = ("و", "ب", "ف", "ل", "ك")      # a clitic written onto a number: «و٢٠», «بربع ساعة», «ب٥», «لعشرة», «كتسعة»


def _glued_and(t: str) -> bool:
    """«و», «ب», «ف», «ل» or «ك» written onto a number («و٢٠», «ونص حباية», «وخمسة», «بربع ساعة», «بخمستاشر يوم»,
    «ب٥ دقايق»; lane 5 b563d74 P1-4): read as the number («حباية ونص», «ساعة ونص» stay a half added to what comes
    before). An everyday word left over stays one («لست» is «ست», read only beside a unit or a time word)."""
    return len(t) > 1 and t[0] in GLUED and (t[1].isdigit() or t[1:] in AR_UNITS or t[1:] in AR_HUNDRED
                                             or t[1:] in SCALES)


def find_numbers(toks: list) -> list:
    """Every number in folded tokens: dicts {start, end (exclusive), value, kind: digits|spelled, unit_in_token,
    ambiguous}; one that cannot be read for sure has no value and carries unsure and its text: two numbers said
    together («50 000», «٢ ٣ حبايات», «تلاتة أربعة»), a fraction said apart («١ / ٢»), "10k", "10 k", a count of parts
    («تلاتة أرباع», "three quarter"), a half after a big number («٥ آلاف ونص», «١٠٠ ونص»: of what?) or before a
    scale ("one and a half thousand"), a fraction word before a plural («تلت حبايات»), «نصين». A «و» written onto
    a number is read through («و٢٠»)."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        view = toks
        if _glued_and(t) and not (t in AND_FRACTION and i and (is_unit(toks[i - 1]) or is_time(toks[i - 1]))):
            t = t[1:]
            view = toks[:i] + [t] + toks[i + 1:]
        if t in DUAL_FRACTIONS:
            out.append(_unsure(toks, i, i + 1, "spelled"))
            i += 1
            continue
        dv = _digit_value(t)
        # «٣، ٥» / «٣ ، ٥»: a decimal comma or a list of two numbers, said apart: unsure, as one number
        split = 0
        if dv is not None and dv[0] is not None and i + 1 < len(view):
            nxt = view[i + 1]
            nv = _digit_value(nxt)
            if t.endswith(",") and re.fullmatch(r"\d+", nxt) or re.fullmatch(r",\d+", nxt):
                split = 2
            elif nxt == "," and i + 2 < len(view) and re.fullmatch(r"\d+", view[i + 2]):
                split = 3
            elif t.endswith("/") and nxt[:1].isdigit():                       # «١/ ٢»
                split = 2
            elif re.fullmatch(r"\d+", t) and nxt == "/" and i + 2 < len(view) and view[i + 2][:1].isdigit():
                split = 3                                                     # «١ / ٢»
            elif re.fullmatch(r"\d+", t) and nxt != t and (re.fullmatch(r"\d+", nxt) or (nv and nv[0] is None)):
                split = 2                         # «50 000», «٢ ٣», «١ /٢», "1 1/2" («٣ ٣» is the same said again)
            elif re.fullmatch(r"[\d.]+", t) and nxt in ("k", "ك"):
                split = 2                                                     # "10 k"
        # «. 5», «- 5», «- ½»: a dot or a minus said on its own before a number (no number before it)
        if t in (".", "-") and i + 1 < len(view) and view[i + 1][:1].isdigit():
            dv, split = (None, ""), 2
        if dv is not None and (dv[0] is None or split or dv[1] in ("k", "ك")):  # "10k": 10 000 or 10 km? unsure
            end = i + (split or 1)
            out.append(_unsure(toks, i, end, "digits"))
            i = end
            continue
        if dv is not None:
            val, rest = dv
            rest = "" if rest == FRAC else rest
            end = i + 1
            # Whisper may split a decimal: "3" "." "5", "3." "5", "3" ".5"
            if rest == "" and i + 2 < len(view) and view[i + 1] == "." and re.fullmatch(r"\d+", view[i + 2]):
                val, end = float(f"{t}.{view[i + 2]}"), i + 3
            elif t.endswith(".") and i + 1 < len(view) and re.fullmatch(r"\d+", view[i + 1]):
                val, end = float(f"{t[:-1]}.{view[i + 1]}"), i + 2
            elif rest == "" and i + 1 < len(view) and re.fullmatch(r"\.\d+", view[i + 1]):
                val, end = float(f"{t}{view[i + 1]}"), i + 2
            elif rest == "" and isinstance(val, int) and i + 1 < len(view) and view[i + 1].endswith(FRAC):
                nv = _digit_value(view[i + 1])          # «3 ½», «1 3⁄4»: a whole number and a written fraction
                if nv and nv[0] is not None and nv[1] == FRAC and nv[0] < 1:
                    val, end = val + nv[0], i + 2
            whole, odd = end, False
            if not rest:
                val, end, odd = _scaled(view, end, val)  # «٥ آلاف», «٥٠ ألف و ٥٠٠», "2 million"
            joined = _joined_digits(view, end, val) if not rest and end == whole else 0
            frac, n = _fraction_after(view, end) if not rest else (0, 0)
            after = view[end + n] if end + n < len(view) else ""
            # «1000 و 500», «٥ آلاف ٥٠٠», «٥ آلاف ونص», «١٠٠ ونص», «٣ أرباع», «٣ ربع», «٣ ونص ألف»: unsure
            if odd or joined or n and (end > whole or val >= 100 or after in SCALES) or after in PLURAL_FRACTIONS \
                    or not n and not rest and after in _FRACTION_WORDS:
                stop = end + (joined or n) + (after in PLURAL_FRACTIONS or after in SCALES
                                              or (not n and after in _FRACTION_WORDS))
                out.append(_unsure(toks, i, stop, "digits"))
                i = stop
                continue
            # "1.500" is 1.5 with a decimal point or 1500 with a dot grouping thousands: keep both readings
            digits = t[:len(t) - len(rest)] if rest else t
            alts = [int(digits.replace(".", ""))] if re.fullmatch(r"\d{1,3}\.\d{3}", digits) and end == whole else []
            # "1.500" may be 1.5 or 1500: both readings kept (a graphic showing either is matched), and flagged
            out.append({"start": i, "end": end + n, "value": val + frac, "kind": "digits",
                        "unit_in_token": rest or None, "ambiguous": False, "alts": alts,
                        **({"unsure": True, "text": " ".join(toks[i:end + n])} if alts else {})})
            i = end + n
            continue
        sp = _spelled(view, i)
        if sp:
            val, n, bare, odd = sp
            frac, m = _fraction_after(view, i + n) if not odd else (0, 0)
            end = i + n + m
            tail = 0 if odd or m else _joined_digits(view, end, val)           # «خمسة و٢٠»: 25 or 5 and 20?
            odd, end = odd or bool(tail), end + tail
            after = view[end] if end < len(view) else ""
            if m and bare:                              # «مية ونص» 150, «ألف ونص» 1500, «مليون ونص»
                val, frac = val * (1 + frac), 0
            elif odd or m and (val >= 100 or after in SCALES) or after in PLURAL_FRACTIONS \
                    or (not m and val >= 1 and after in _FRACTION_WORDS) \
                    or (n == 1 and not m and val < 1 and any(s in PLURAL_NOUNS for s in stems(after))):
                stop = end + (after in PLURAL_FRACTIONS or (m and after in SCALES)
                              or (not odd and not m and val >= 1 and after in _FRACTION_WORDS))
                out.append(_unsure(toks, i, stop, "spelled"))
                i = stop
                continue
            out.append({"start": i, "end": end, "value": val + frac, "kind": "spelled", "unit_in_token": None,
                        "ambiguous": n == 1 and not m and t in AMBIGUOUS})
            i = end
            continue
        i += 1
    return out


def is_unit(tok: str) -> bool:
    """A unit, also one written over another ("mg/kg", «مجم/كجم»)."""
    return any(s in UNITS for s in stems(tok)) or ("/" in tok and any(s in UNITS for s in stems(tok.split("/")[0])))


def is_time(tok: str) -> bool:
    return any(s in TIME or DUALS.get(s) == "duration" for s in stems(tok))


def is_frequency(tok: str) -> bool:
    return any(s in FREQUENCY for s in stems(tok))


def frequency_value(tok: str):
    for s in stems(tok):
        if s in FREQUENCY:
            return FREQUENCY[s]
    return None


def _less_a_part(toks: list, k: int) -> bool:
    """«الا ربع» / «الا تلت» at toks[k]: a count less a part («ساعتين الا ربع», «حباية الا ربع»)."""
    return k + 1 < len(toks) and toks[k] == "الا" and toks[k + 1] in _FRACTION_WORDS


def _unit_len(toks: list, k: int) -> int:
    """How many tokens at toks[k] make a unit: 2 for «سي سي», 1 for «مجم», 0 for none."""
    if k + 1 < len(toks) and (toks[k], toks[k + 1]) in TWO_WORD_UNITS:
        return 2
    return 1 if k < len(toks) and is_unit(toks[k]) else 0


def _unit_name(toks: list, k: int, u: int) -> str:
    """What the unit at toks[k:k + u] measures (UNIT_CLASS: «مجم» and "mg" are "mg"); an unlisted unit is its word."""
    if u == 2:
        return TWO_WORD_CLASS.get((toks[k], toks[k + 1]), f"{toks[k]} {toks[k + 1]}")
    if "/" in toks[k]:
        return _token_unit(toks[k]) or toks[k]                      # "mg/kg"
    st = stems(toks[k])
    return next((UNIT_CLASS[s] for s in st if s in UNIT_CLASS), next((s for s in st if s in UNITS), toks[k]))


def _token_unit(rest: str):
    """The unit written onto a number («500mg» "mg", "5mg/kg" "mg/kg"), None when what is written is no unit."""
    parts = [p for p in str(rest or "").split("/") if p]
    if not parts or not is_unit(parts[0]):
        return None
    return "/".join(_unit_name([q], 0, 1) for q in parts[:2])


def _unit_tail(toks: list, k: int, unit: str) -> tuple:
    """(unit, tokens used) for what may follow a dose's unit at toks[k]: a spoon's size («معلقة صغيرة» a teaspoon,
    «معلقة كبيرة» a tablespoon), a body weight («لكل كيلو», "per kg", "/ kg": a dose by weight)."""
    n = 0
    if unit == "spoon" and k < len(toks) and toks[k] in SPOON_SIZE:
        unit, n = SPOON_SIZE[toks[k]], 1
    j = k + n
    if j + 1 < len(toks) and toks[j] in PER_WEIGHT and any(s in KILO for s in stems(toks[j + 1])):
        unit, n = f"{unit}/kg", n + 2
    return unit, n


# 1–3 letters right after a number written in digits are its unit, even one no list knows ("5 m" / "5 h", "2 d", «٥ د» /
# «٥ س», "5h"): compared by what is written, so "5 m" ≠ "5 h" (executor ruling, review e4ed4c6 P2-1). Never a word that
# only links («٢ او ٣», "2 or 3", "5 a day"), a pronoun or an ordinal ending ("1st"). «vitamin D», "D3", "B12": the
# letter comes before the digit, so they are never read so.
_NOT_A_UNIT = {fold(w) for w in (
    "و", "او", "أو", "ولا", "في", "فى", "من", "عن", "على", "علي", "الى", "إلى", "مع", "بس", "ده", "دي", "دا", "يا", "لو",
    "ان", "إن", "أن", "انا", "هو", "هي", "كل", "كام", "لا", "مش", "ما", "ثم", "بعد", "قبل", "لكل", "عشان",
    "or", "and", "to", "of", "in", "on", "at", "by", "for", "is", "are", "was", "be", "it", "its", "x", "so", "as", "if",
    "no", "not", "a", "an", "the", "per", "each", "or", "nor", "but", "yet", "up", "off", "out", "via", "vs",
    "i", "me", "my", "we", "us", "our", "you", "he", "him", "his", "she", "her", "they", "all", "any", "few",
    "st", "nd", "rd", "th")} | LINK | ARTICLES | PER_WEIGHT
_UNIT_LETTERS = re.compile(r"[^\W\d_]{1,3}")


def digit_unit(tok) -> str | None:
    """The 1–3 letters (folded) that are a digit number's unit, written apart or onto it; None otherwise."""
    t = str(tok or "")
    return t if _UNIT_LETTERS.fullmatch(t) and t not in _NOT_A_UNIT else None


def _time_name(tok: str) -> str:
    """Which period a time word counts (TIME_CLASS: «أيام» and "days" are "day")."""
    return next((TIME_CLASS[s] for s in stems(tok) if s in TIME_CLASS), tok)


def quantities(toks: list) -> list:
    """Numbers with what goes with them: {start, end, value, kind: dose|duration|number, unit}. A unit right after the
    number (or fused into it, or right before it: «حباية واحدة», or after "of": "three quarters of a tablet") makes a
    dose; a time word within two tokens («٨ ساعات», «مرة في اليوم») a duration; a dual form («حبايتين», «ساعتين») is
    2 of its own kind. An everyday word that is also a number («ست», «نص») is kept only with a unit or a time word.
    unit: what a dose is counted in (UNIT_CLASS: «مجم» = "mg", «حباية» = «قرص» = "tablet", «معلقة صغيرة» =
    "teaspoon", «لكل كيلو» adds "/kg") or the period a duration counts ("day", "week"). A number that cannot be read
    for sure, or a vague amount («كام حباية»), has no value and carries its text."""
    out, taken = [], set()

    def add(start, end, value, kind, unit, **extra):
        if kind != "number" and _less_a_part(toks, end):     # «حباية الا ربع», «ساعتين الا ربع»: a count less a
            end, value, extra = end + 2, None, {**extra, "unsure": True}    # part, never the count
            extra.pop("text", None)
        out.append({"start": start, "end": end, "value": value, "kind": kind, "unit": unit, **extra,
                    **({"text": " ".join(toks[start:end])} if value is None and "text" not in extra else {})})
        taken.update(range(start, end))
    for n in find_numbers(toks):
        start, end, kind, unit = n["start"], n["end"], "number", None
        u = _unit_len(toks, end)
        written = _token_unit(n["unit_in_token"]) if n["unit_in_token"] else None
        if written:
            kind, unit = "dose", written
        elif u:
            kind, unit, end = "dose", _unit_name(toks, end, u), end + u
        elif start > 0 and is_unit(toks[start - 1]) and start - 1 not in taken:
            kind, unit, start = "dose", _unit_name(toks, start - 1, 1), start - 1
        elif end + 1 < len(toks) and toks[end] in ARTICLES and _unit_len(toks, end + 1):
            u = _unit_len(toks, end + 1)
            kind, unit, end = "dose", _unit_name(toks, end + 1, u), end + 1 + u      # "half a tablet", "half the dose"
        elif end + 1 < len(toks) and toks[end] == "of" and (_unit_len(toks, end + 1) or (
                end + 2 < len(toks) and toks[end + 1] in ARTICLES and _unit_len(toks, end + 2))):
            k = end + 1 + (toks[end + 1] in ARTICLES)                           # "three quarters of a tablet"
            kind, unit, end = "dose", _unit_name(toks, k, _unit_len(toks, k)), k + _unit_len(toks, k)
        else:
            for k in (end, end + 1):
                if k < len(toks) and is_time(toks[k]) and (k == end or toks[end] in LINK):
                    kind, unit, end = "duration", _time_name(toks[k]), k + 1
                    break
        if kind == "number" and n["kind"] == "digits" and n["value"] is not None:
            tag = digit_unit(n["unit_in_token"]) if n["unit_in_token"] else None
            if not n["unit_in_token"] and end < len(toks) and digit_unit(toks[end]):
                tag, end = toks[end], end + 1
            if tag:
                unit = "?" + tag                    # a unit no list knows: compared by its letters ("?m" ≠ "?h")
        if kind == "number" and n["ambiguous"]:
            continue
        if kind == "dose":
            unit, more = _unit_tail(toks, end, unit)
            end += more
        value, extra = n["value"], {}
        frac, m = _fraction_after(toks, end) if kind != "number" and value is not None else (0, 0)
        if m:                                       # «تلات حبايات ونص» 3.5, «٥ أيام ونص»; «٥٠٠ مجم ونص»: of what?
            value, end = (value + frac if value < 100 else None), end + m
            extra = {} if value is not None else {"unsure": True, "text": " ".join(toks[start:end])}
        # «مرتين في اليوم», "twice a day", «كل ٨ ساعات»: take the frequency tail too
        if end + 1 < len(toks) and toks[end] in LINK and is_time(toks[end + 1]):
            end += 2
        add(start, end, value, kind, unit, alts=n.get("alts") or [],
            **({"unsure": True, "text": n["text"]} if n.get("unsure") else extra))
    for i, t in enumerate(toks):
        if i in taken:
            continue
        frac, m = _fraction_after(toks, i + 1)
        if is_unit(t) and m:                       # «حباية ونص»: one and a half pills
            add(i, i + 1 + m, 1 + frac, "dose", _unit_name(toks, i, 1))
            continue
        if is_time(t) and m and not any(s in DUALS for s in stems(t)):     # «ساعة ونص», "an hour and a half"
            a = i - 1 if i and toks[i - 1] in ARTICLES else i
            add(a, i + 1 + m, 1 + frac, "duration", _time_name(t))
            continue
        if any(s in ("مره", "time") for s in stems(t)) and i + 2 < len(toks) and toks[i + 1] in LINK \
                and is_time(toks[i + 2]):          # «مرة في اليوم», «مرة كل يومين»: once a day
            add(i, i + 3, 1, "duration", "times")
            continue
        if any(s in ("مره", "once") for s in stems(t)) and i + 1 < len(toks) and (
                toks[i + 1] in ("او", "ولا", "or") or any(s in DUALS or s in FREQUENCY for s in stems(toks[i + 1]))):
            add(i, i + 1, 1, "duration", "times")   # «مرة أو مرتين», «مرة مرتين»: once is said
            continue
        dual = next((s for s in stems(t) if s in DUALS), None)
        if dual:
            end, unit = i + 1, DUAL_UNIT.get(dual) or _time_name(dual)
            if DUALS[dual] == "dose":
                unit, more = _unit_tail(toks, end, unit)
                end += more
            frac, m = _fraction_after(toks, end)
            if m:                                   # «ساعتين ونص», «كبسولتين ونص»
                add(i, end + m, 2 + frac, DUALS[dual], unit)
                continue
            if end + 1 < len(toks) and toks[end] in LINK and is_time(toks[end + 1]):
                end += 2
            add(i, end, 2, DUALS[dual], unit)
            continue
        one = _one_dose(toks, i)
        if one and not taken & set(range(*one[:2])):
            unit, more = _unit_tail(toks, one[1], _unit_name(toks, one[3], 1))
            add(one[0], one[1] + more, one[2], "dose", unit)
    return sorted(out, key=lambda q: q["start"])


def _one_dose(toks: list, i: int):
    """(start, end, value, noun index) for a dose said without a number: a count noun on its own is one («خدي حباية»,
    "take a tablet"), said again it is two («حباية وحباية», «حباية و حباية»); after a vague amount («كام حباية»,
    «كذا حباية», "a few tablets") it has no value (an amount, never one). Not with the article or a pointer
    («الحباية دي», «كل حباية»: which pill, not how many); «حبة» (also "a little") and «نقطة» (also "a point") are never
    counted so."""
    t = toks[i]
    if not any(s in COUNT_NOUNS for s in stems(t)) or t.startswith(("ال", "وال", "بال", "فال", "لل")):
        return None
    base = next(s for s in stems(t) if s in COUNT_NOUNS)
    nxt = toks[i + 1] if i + 1 < len(toks) else ""
    prev = toks[i - 1] if i > 0 else ""
    if prev in VAGUE:
        return i - 1, i + 1, None, i
    if nxt in ("و", "and") and i + 2 < len(toks) and base in stems(toks[i + 2]) and toks[i + 2] == t:
        return i, i + 3, 2, i
    if nxt.startswith("و") and nxt[1:] == base:
        return i, i + 2, 2, i
    if _ARABIC_LETTER.search(t):
        if nxt in POINTERS or prev in POINTERS:
            return None
        return i, i + 1, 1, i
    return (i - 1, i + 1, 1, i) if prev in ("a", "an") else None


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
    vals = {canon(v) for q in quantities(toks) for v in [q["value"], *q.get("alts", [])] if v is not None}
    vals |= {canon(v) for t in toks if (v := frequency_value(t)) is not None}
    return vals


def canon(v):
    if isinstance(v, int) and not isinstance(v, bool):
        return v                                       # a whole number of any length (float() would overflow)
    return int(v) if float(v).is_integer() else round(float(v), 4)
