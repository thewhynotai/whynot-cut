"""People, gender and honorifics (3.0): the profile's `people[]` and the check that an Arabic honorific (or a verb)
written with a person's name agrees with that person's gender in the profile.

profile.json `people`: [{"name", "role", "gender": "male" | "female" | "unknown", "honorific_ar", "honorific_en",
"pronouns"}], filled by the client-researcher only from the client's own material. `unknown` means: ask the editor.
Gender is never inferred from a name (a real run wrote «الدكتورة» for a male client from his first name alone).

The check is deterministic: normalise (tashkeel, tatweel, direction marks and ZWJ/ZWNJ stripped, alef forms unified,
ة -> ه, ى -> ي), split into clauses at punctuation (except / : - « “ ( right after an honorific: «الدكتورة/ كريم»),
find a gendered honorific (الدكتور/الدكتورة, دكتور/دكتورة, الأستاذ/الأستاذة, الشيخ/الشيخة, المهندس/المهندسة, with or
without «ال» and the clitics و ف ب ل ك) or the ungendered «د.» / «د/» / "Dr.", skip any further honorifics («الأستاذة
الدكتور كريم»), and read the name run after it. A run that names a profile person:
  * honorific of the other gender                    -> error
    (a warning instead when the only name word is also a common word after folding: «الدكتورة على حق» vs علي)
  * person's gender `unknown` + gendered honorific    -> warning (ask the editor)
  * a past-tense verb of the other gender right before the honorific (VSO: «قالت الدكتور كريم»), or right after the
    name when the mention opens the clause («الدكتور كريم قالت») and no new subject follows -> warning
`check_nameless` (used by `reel plan` only): every profile person has one gender and the text uses the other gender's
honorific with no known name after it («صور الدكتورة المعتمدة» for an all-male profile) -> warning.
"""
from __future__ import annotations

import re
import unicodedata

GENDERS = ("male", "female", "unknown")
# normalised stem -> (masculine, feminine) as written in a suggestion
HONORIFICS = {"دكتور": ("الدكتور", "الدكتورة"), "استاذ": ("الأستاذ", "الأستاذة"), "شيخ": ("الشيخ", "الشيخة"),
              "مهندس": ("المهندس", "المهندسة")}
_HON = re.compile(r"^(?P<conj>[وف])?(?P<pre>[بلك]?ال|لل|[بلك])?(?P<stem>" + "|".join(HONORIFICS) + r")(?P<fem>ه)?$")
# past-tense verbs that take the person as subject: normalised (masculine, feminine). Verbs whose masculine form is
# also a common noun before a name (شرح "explanation", كشف "examination", رد "reply", ذكر) are left out on purpose.
VERBS = [("قال", "قالت"), ("اكد", "اكدت"), ("اوضح", "اوضحت"), ("حكي", "حكت"), ("نصح", "نصحت"), ("اضاف", "اضافت"),
         ("اشار", "اشارت"), ("تحدث", "تحدثت"), ("اتكلم", "اتكلمت"), ("جاوب", "جاوبت")]
VERB_GENDER = {**{m: "male" for m, _ in VERBS}, **{f: "female" for _, f in VERBS}}
# words inside a name that never identify a person by themselves (عبد الرحمن, أبو بكر, El-Sayed ...)
PARTICLES = {"عبد", "ابو", "ابي", "ام", "ابن", "بن", "بنت", "ال", "el", "al", "abu", "abd", "bin", "ibn", "bint", "de",
             "van", "von"}
# normalised function words that a name can fold into (على -> علي, منّي -> مني, إلى -> الي ...): a name run made only of
# these is too ambiguous for an error
FUNCTION_WORDS = {"علي", "مني", "الي", "حتي", "في", "الا", "عن", "من", "ما", "لا", "لو", "يا", "او", "ان", "انا", "انت",
                  "هو", "هي", "كل", "بس", "مع", "عند", "زي", "اللي", "ده", "دي", "لي", "له", "ليه", "ايه", "كان", "بعد",
                  "قبل", "فوق", "تحت", "بين", "غير", "مش", "متي", "لما", "اذا", "اما", "ثم"}
TITLES = {"dr", "mr", "mrs", "ms", "miss", "prof", "eng", "sheikh", "د", "م", "ا", "ش"}
ABBR = "drabbr"                                   # «د.» «د/» "Dr." after normalisation: a title with no gender
SOFT = set("/:-–—«“\"(")                          # after an honorific these don't end the clause («الدكتورة: كريم»)

_DIAC = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")   # tashkeel, Quranic marks, tatweel
_INVISIBLE = re.compile(r"[‌‍‎‏‪-‮⁦-⁩]")  # ZWNJ/ZWJ, direction marks
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"})
_ABBR_RE = re.compile(r"(?<!\w)(?:د|dr)\s*[./](?=\s*\w)", re.I)
_TOKEN = re.compile(r"\w+|[^\w\s]+|\n")


def _clean(s: str) -> str:
    """Display form: NFKC, tashkeel/tatweel/invisible marks stripped, hashtag underscores as spaces, abbreviated
    titles as one token."""
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = _DIAC.sub("", _INVISIBLE.sub("", s)).replace("_", " ")     # #الدكتور_كريم
    return _ABBR_RE.sub(f" {ABBR} ", s)


def _norm(tok: str) -> str:
    return tok.translate(_FOLD).lower()


def _clauses(text: str) -> list[list[tuple[str, str]]]:
    """[[(display, normalised) token, ...] per clause]."""
    out, cur = [], []
    for m in _TOKEN.finditer(_clean(text)):
        t = m.group()
        if t[0].isalnum() or t[0] == "_":
            cur.append(("د." if t.lower() == ABBR else t, _norm(t)))
        elif cur and t != "\n" and set(t) <= SOFT and honorific(cur[-1][1]):
            continue
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def honorific(tok: str) -> dict | None:
    """A normalised token -> {"stem", "gender" (None = «د.»), "object" (a ب/ل/ك clitic: not the subject)}."""
    if tok == ABBR:
        return {"stem": None, "gender": None, "object": False, "article": False}
    m = _HON.match(tok)
    if not m:
        return None
    pre = m.group("pre") or ""
    return {"stem": m.group("stem"), "gender": "female" if m.group("fem") else "male",
            "object": pre[:1] in ("ب", "ل", "ك"), "article": pre.endswith("ال") or pre == "لل"}


def name_tokens(name: str) -> set[str]:
    """Normalised tokens that identify the person: the name minus titles, honorifics and particles."""
    toks = set()
    for clause in _clauses(name):
        for _d, t in clause:
            if t == ABBR or t in TITLES or t in PARTICLES or honorific(t) or len(t) < 2:
                continue
            toks.add(t)
    return toks


def load_people(cfg: dict | None = None) -> tuple[list[dict], list[str]]:
    """profile.json `people` -> (people with `tokens`, problems). A missing or invalid gender counts as unknown."""
    if cfg is None:
        from .common import load_config
        cfg = load_config("profile.json")
    raw = cfg.get("people") or []
    people, issues = [], []
    if not isinstance(raw, list):
        return [], ["profile.json people must be a list of {name, role, gender, honorific_ar, honorific_en, pronouns}"]
    for k, p in enumerate(raw):
        if not isinstance(p, dict) or not str(p.get("name") or "").strip():
            issues.append(f"profile.json people[{k}]: needs a name (and gender male | female | unknown)")
            continue
        g = str(p.get("gender") or "unknown").strip().lower()
        if g not in GENDERS:
            issues.append(f"profile.json people[{k}] ({p['name']}): gender {p.get('gender')!r} must be male, female or "
                          "unknown; treated as unknown (ask the editor, never guess from the name)")
            g = "unknown"
        hon = str(p.get("honorific_ar") or "")
        hg = {h["gender"] for c in _clauses(hon) for _d, t in c if (h := honorific(t)) and h["gender"]}
        if hg and (hg != {g}):
            issues.append(f"profile.json people[{k}] ({p['name']}): honorific_ar «{hon}» does not match gender {g!r}: "
                          "fix whichever is wrong from the client's material (ask the editor if unsure)")
        toks = name_tokens(p["name"])
        if not toks:
            issues.append(f"profile.json people[{k}] ({p['name']}): no usable name word to match")
            continue
        people.append(dict(p, gender=g, tokens=toks))
    return people, issues


def _who(clause: list, j: int, people: list) -> tuple[int, dict | None, bool]:
    """The name run starting at token j -> (index after the run, the person it names or None when none/ambiguous,
    True when the only name words matched are common function words such as «على»)."""
    known = set().union(*(p["tokens"] for p in people)) if people else set()
    run, k = [], j
    while k < len(clause) and (clause[k][1] in known or clause[k][1] in PARTICLES):
        run.append(clause[k][1])
        k += 1
    while run and run[-1] in PARTICLES:
        run.pop()
        k -= 1
    hits = [(len(p["tokens"] & set(run)), p) for p in people]
    best = max((n for n, _p in hits), default=0)
    if not best:
        return j, None, False
    top = [p for n, p in hits if n == best]
    if len({p["gender"] for p in top}) > 1:
        return k, None, False                    # two people with these words and different genders: can't tell
    return k, top[0], (top[0]["tokens"] & set(run)) <= FUNCTION_WORDS


def _after_titles(clause: list, i: int) -> int:
    """Index of the first token after the honorific at i and any honorifics chained to it («الأستاذة الدكتور كريم»)."""
    j = i + 1
    while j < len(clause) and honorific(clause[j][1]):
        j += 1
    return j


def _form(stem: str, gender: str, article: bool) -> str:
    w = HONORIFICS[stem][0 if gender == "male" else 1]
    return w if article else w[2:]


def check_text(where: str, text: str, people: list) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one piece of on-screen text or copy."""
    errors, warnings = [], []
    if not people or not text:
        return errors, warnings
    for clause in _clauses(text):
        for i, (disp, tok) in enumerate(clause):
            h = honorific(tok)
            if not h:
                continue
            end, p, vague = _who(clause, _after_titles(clause, i), people)
            if p is None:
                continue
            said = " ".join(d for d, _t in clause[i:end])
            g = p["gender"]
            if h["gender"] and g in ("male", "female") and h["gender"] != g:
                fix = f"write «{_form(h['stem'], g, h['article'])}», not «{disp}»"
                if vague:
                    words = " ".join(d for d, t in clause[i + 1:end] if t in p["tokens"])
                    warnings.append(f"{where}: «{said}» — «{words}» is also a common word; if it is {p['name']}, they "
                                    f"are {g} in the client profile (people[]): {fix}")
                else:
                    errors.append(f"{where}: «{said}» — {p['name']} is {g} in the client profile (people[]): {fix}")
            elif h["gender"] and g == "unknown" and not vague:
                warnings.append(f"{where}: «{said}» — the gender of {p['name']} is unknown in the client profile: ask "
                                "the editor and record it in people[] (or write «د.» / the name alone); never guess "
                                "it from the name")
            if vague:
                continue
            verbs = []
            if i > 0 and not h["object"] and not honorific(clause[i - 1][1]):
                verbs.append(clause[i - 1])
            # «الدكتور كريم قالت الدكتورة سارة»: the verb after the name has a new subject
            if i == 0 and end < len(clause) and not (end + 1 < len(clause) and honorific(clause[end + 1][1])):
                verbs.append(clause[end])
            for vd, vt in verbs:
                vg = VERB_GENDER.get(vt)
                if vg and vg != g:
                    hint = (f"{p['name']} is {g} in the client profile" if g != "unknown" else
                            f"the gender of {p['name']} is unknown in the client profile: ask the editor")
                    warnings.append(f"{where}: «{vd}» next to «{said}» — {hint} (check the verb agrees)")
    return errors, warnings


def check_many(items, people: list) -> tuple[list[str], list[str]]:
    """[(where, text), ...] -> (errors, warnings)."""
    errors, warnings = [], []
    for where, text in items:
        e, w = check_text(where, text, people)
        errors += e
        warnings += w
    return errors, warnings


def check_nameless(where: str, text: str, people: list) -> list[str]:
    """Warnings for an honorific with no known name when every profile person has the other gender («صور الدكتورة
    المعتمدة» for an all-male profile: the incident's own sentence). Nothing when genders are mixed or unknown."""
    genders = {p["gender"] for p in people}
    if len(genders) != 1 or "unknown" in genders or not text:
        return []
    g = genders.pop()
    out = []
    for clause in _clauses(text):
        for i, (disp, tok) in enumerate(clause):
            h = honorific(tok)
            if not h or not h["gender"] or h["gender"] == g:
                continue
            if _who(clause, _after_titles(clause, i), people)[1] is None:
                out.append(f"{where}: «{disp}» with no known name, but everyone in the client profile (people[]) is "
                           f"{g}: write «{_form(h['stem'], g, h['article'])}», or name the person and add them to "
                           "people[] if they are someone else")
    return out


def profile_notice(root=None) -> str | None:
    """The `reel next` hint when the client has a profile but no people[] (the gender checks have nothing to use)."""
    from .common import load_config, profile_dirs
    if not profile_dirs(root) or load_config("profile.json").get("people"):
        return None
    return ("fill people[] in reel-profile/profile.json (name, gender, honorifics, from the client's material only) — "
            "gender/honorific checks are off until then")
