# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Review domains (3.0 Phase 4 Task 50 = Addendum M1-T1): medical, religious, business and ai, as data.

The registry (config/review-domains/registry.json) lists the domains. A domain is one entry there plus its checker
guidance (skills/medical-accuracy/references/<reference>), its trigger lexicon (config/review-domains/<lexicon>) and its
eval cases (evals/review-<id>-<name>/case.yaml, flat like every eval case, `name:` = the folder): a new one needs no
engine change (`structure_problems()` names what an entry lacks). Data never weakens an existing guard: medical and ai
must stay in the registry, always on, and medical keeps `needs-doctor-approval` (ALWAYS_ON is also a floor in code).

Two sets, kept apart so the review key stays stable:
- the CLIENT SET = the profile's `review_domains` ∪ the legacy `domain` (medical/religious) ∪ the always-on domains
  (medical, ai). It changes only when the profile changes; `review_domain_key()` makes the canonical key T4.13 stores as
  review-flags.json's `domain` (M1-T2): ids lower-cased, trimmed, de-duplicated, checked against the registry, sorted by
  code point and joined with `+`. A profile with no `review_domains` keeps today's checks: general/medical → ai+medical,
  religious → ai+medical+religious. When both are present the legacy domain is kept too (adding `business` never drops
  a religious client's religious review; dropping religious means changing `domain`, which also relabels the glossary);
- DETECTED domains, per plan line: the lexicons run over the line's on-screen text and the transcript evidence the plan
  cites for it (`evidence`), plus the asset manifest's `ai_generated: true` for the files the line shows. A detected
  domain outside the client set becomes a REQUIRED flag for that line only, and only under `review_detect: review` (the
  default); `suggest` lists it, `off` turns detection off. Detection is a floor, never a ceiling: the reviewer may flag any
  line for any registry domain, and still reads every line (a hint is a pointer, never a filter). Events that show an
  AI-generated file are listed in `ai_assets` too when they have no on-screen words (no review line can name them).

Matching is deterministic. Both sides are normalised the same way: NFKC (presentation forms such as lam-alef, ﷺ),
no diacritics, tatweel, bidi controls or invisible characters (zero-width spaces and joiners, variation selectors,
fillers, tags: inside a word they are stripped), Arabic and Latin letters split apart («الـAI»), one alef, ى→ي, ة→ه,
Arabic-Indic and Persian digits as 0-9, ٪ as %. A text is also read with a zero-width space or word joiner as a word gap
(«AI» + U+200B + «tools») and with the Quran-app dagger alef as an alef («ٱلْعَٰلَمِينَ»); such a reading adds only the
domains the first one missed. An Arabic term word also matches after one joined prefix (و ف ب ل ك ال and their pairs,
the Egyptian verb prefixes بـ هـ and ا ي ت ن).

A lexicon's `zones` count for that lexicon's domain. Only a CLOSED bracket zone (a verse between ﴿ ﴾) hides anything,
and only other domains' plain WORDS: a `terms` rule (unless it says `zone_hideable: false`, as the spelled 100 % and
rank rules do) or a pattern rule that says `zone_hideable: true`. A zone holding any digit, a percent or per-mille
sign, a letter of any script but Arabic or any currency sign (an amount, «١٠٠٪», «بس بـ ٩٩», «#1», «﷼», English or
Cyrillic words) hides nothing, whatever the lexicon says (no verse is written that way). Rules read the text with the
brackets as spaces, so a claim that runs past a bracket («﴿ خصم ﴾ ٥٠٪») is not inside the zone and shows. «﷼»
stays a currency sign in the matching form; a further reading spells it «ريال».
The same words are hidden in the speech's recitation of the verse (RECITED words in a row). An unclosed verse hides
nothing, and a quotation after a citation («قال تعالى «…»», «ربنا قال “…”») counts as religious but hides nothing:
«ربنا قال» is everyday speech, so a claim put in scripture's mouth reaches the business reviewer too. Verses quoted with
no brackets are found only from the religious lexicon's list of common verse phrases (a hint; anything else is a known
limit) and hide nothing. A text longer than WINDOW characters (after NFKC) is read in overlapping windows, so hostile
input costs linear time; a domain found in any window also gets its supporting rows from every window.
`reel review-scan` prints `scan()`; nothing here writes.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath

from .common import PLUGIN_DIR, Paths, load_config, read_json
from .errors import Guidance

REGISTRY_DIR = PLUGIN_DIR / "config" / "review-domains"
REFERENCES_DIR = PLUGIN_DIR / "skills" / "medical-accuracy" / "references"
EVALS_DIR = PLUGIN_DIR / "evals"                     # a domain's cases: evals/review-<id>-<name>/case.yaml
REGISTRY = "registry.json"
SCHEMA = 1
MODES = ("review", "suggest", "off")
ALWAYS_ON = ("ai", "medical")          # a floor, whatever the registry says: existing guards are never weakened by data
LEGACY_DOMAINS = ("", "general", "medical", "religious")   # profile.json `domain` (common.content_domain)
TEMPLATE_DOMAIN = "medical | religious | general"      # profiles/_template until the client picks one: general
RECITED = 3                            # speech words in a row that repeat an on-screen verse count as its recitation
_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}")
NOTE = ("Hints point the reviewer at lines and domains; the reviewer still reads every line and may flag any line for "
        "any domain.")

# ---------------------------------------------------------------------------------------------- normalising
_DAGGER = chr(0x670)                   # the superscript (dagger) alef of Quran-app text, «ٱلْعَٰلَمِينَ»
_INVISIBLE = (                         # dropped before matching: marks, tatweel and characters that show nothing
    (0x610, 0x61a), (0x61c, 0x61c), (0x640, 0x640), (0x64b, 0x65f), (0x670, 0x670), (0x6d6, 0x6ed),   # Arabic
    (0xad, 0xad), (0x34f, 0x34f), (0x115f, 0x1160), (0x17b4, 0x17b5), (0x180b, 0x180f), (0x3164, 0x3164),  # fillers
    (0x200b, 0x200f), (0x202a, 0x202e), (0x2060, 0x2064), (0x2066, 0x2069), (0xfeff, 0xfeff),  # zero-width, bidi
    (0xfe00, 0xfe0f), (0xffa0, 0xffa0), (0x1d173, 0x1d17a), (0xe0000, 0xe007f))   # selectors, fillers, format, tags
_DROP = re.compile("[" + "".join(re.escape(chr(a)) + ("-" + re.escape(chr(b)) if b != a else "")
                                  for a, b in _INVISIBLE) + "]")
_MARKS = re.compile("[" + chr(0x64b) + "-" + chr(0x65f) + "]")
_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ک": "ك", "ی": "ي", "٪": "%",
                      "٫": ".", "٬": ",", **{chr(0x660 + i): str(i) for i in range(10)},
                      **{chr(0x6f0 + i): str(i) for i in range(10)}})
_PREFIXES = ("و", "ف", "ب", "ل", "ك", "ا", "ي", "ت", "ن", "ه", "ال", "وال", "فال", "بال", "كال", "لل", "ولل", "وب", "ول",
             "فب", "فل", "هي", "هت", "هن", "بي", "بت", "بن", "وهي", "وهت", "وهن", "وبي", "وبت", "وبن")
_WORD = re.compile(r"\w+")
_GAPS = re.compile("[" + chr(0x200b) + chr(0x2060) + "]")        # zero-width space, word joiner: also read as a gap
_ARABIC_BLOCKS = ((0x600, 0x6ff), (0x750, 0x77f), (0x870, 0x8ff), (0xfb50, 0xfdff), (0xfe70, 0xfeff),
                  (0x10e60, 0x10e7f), (0x1ee00, 0x1eeff))   # Arabic, its supplements and presentation forms
_NUMBER_SIGNS = frozenset("%‰‱؉؊")                 # percent and per-mille signs, Latin and Arabic
_RIAL = "\ufdfc"                                   # ﷼: NFKC would spell it as the plain word «ریال»; it stays a sign
WINDOW = 1000                                      # a longer text is read in overlapping windows of this many chars
_OVERLAP = 200                                     # chars two windows share, so no claim is lost at a cut
_SLACK = 50                                        # how far a cut may move to fall on a space
_SCRIPTS = re.compile(r"(?<=[ء-ي])(?=[A-Za-z])|(?<=[A-Za-z])(?=[ء-ي])")    # «الـAI» → «ال AI»


def _nfkc(text: str) -> str:
    return _RIAL.join(unicodedata.normalize("NFKC", part) for part in str(text).split(_RIAL))


def normalize(text: str) -> str:
    """The matching form of a text (lexicon terms and plan words alike); Latin case is kept (case rules need it)."""
    return _SCRIPTS.sub(" ", _DROP.sub("", _nfkc(text)).translate(_MAP))


def _never_hidden(text: str) -> bool:
    """The code floor: a zone holding any digit or number (Unicode N*), a percent or per-mille sign, any currency sign
    (Unicode Sc) or a letter of any script but Arabic (Latin, Cyrillic, Greek…) hides nothing, whatever the lexicon
    says (no verse is written that way)."""
    for ch in text:
        cat = unicodedata.category(ch)
        if cat[0] == "N" or cat == "Sc" or ch in _NUMBER_SIGNS:
            return True
        if cat[0] == "L" and not any(a <= ord(ch) <= b for a, b in _ARABIC_BLOCKS):
            return True
    return False


def _windows(text: str) -> list:
    """The text itself, or (longer than WINDOW) overlapping windows of it, cut on a space where one is near: the
    matching cost stays linear on hostile input and nothing past a cut is ever dropped."""
    if len(text) <= WINDOW:
        return [text]
    out, i = [], 0
    while True:
        end = i + WINDOW
        if end >= len(text):
            out.append(text[i:])
            return out
        sp = max(text.rfind(c, end - _SLACK, end) for c in " \t\n")
        end = sp if sp > i else end
        out.append(text[i:end])
        i = end - _OVERLAP
        sp = min((x for x in (text.find(c, i, i + _SLACK) for c in " \t\n") if x >= 0), default=-1)
        i = sp + 1 if sp >= 0 else i


def _dagger_as_alef(raw: str) -> str:
    """Quran-app spelling: the dagger alef read as an alef (رَٰجِعُونَ → راجعون), except in the name of God (لِلَّٰهِ)."""
    s = _MARKS.sub("", _nfkc(raw))
    return s.replace("لل" + _DAGGER + "ه", "لله").replace(_DAGGER, "ا")


def _readings(text: str) -> list:
    """The matching forms of one text: normalised first; then, only when they differ, the text with a zero-width space
    or word joiner read as a word gap («AI» + U+200B + «tools»), with the dagger alef read as an alef, and with «﷼»
    spelled «ريال» (the sign stays beside it, so a zone holding it still hides nothing). A later reading adds only the
    domains the earlier ones did not find (so a split amount never yields a second, partial row)."""
    raw = str(text)
    out = [normalize(raw)]
    for alt in (_GAPS.sub(" ", raw), _dagger_as_alef(raw), raw.replace(_RIAL, " ريال " + _RIAL + " ")):
        n = normalize(alt)
        if n not in out:
            out.append(n)
    return out


def _arabic(word: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in word)


def _candidates(token: str) -> set:
    """An Arabic token and what is left after one joined prefix (at least two letters)."""
    return {token} | {token[len(p):] for p in _PREFIXES if token.startswith(p) and len(token) - len(p) >= 2}


# ---------------------------------------------------------------------------------------------- registry
def _bad_registry(problem: str):
    return Guidance(f"the review-domain registry is not usable: {problem}",
                    "Fix config/review-domains/registry.json (schema 1: each domain has label, reference, lexicon, "
                    "approver, verdicts with ok, always_on), or reinstall the plugin",
                    where=str(REGISTRY_DIR / REGISTRY))


def _bilingual(v) -> bool:
    return isinstance(v, dict) and all(isinstance(v.get(k), str) and v[k].strip() for k in ("ar", "en"))


def registry() -> dict:
    """id -> entry, validated; read now (a registry edit needs no restart)."""
    doc = read_json(REGISTRY_DIR / REGISTRY)
    if not isinstance(doc, dict):
        raise _bad_registry("the file is missing or is not a JSON object")
    if doc.get("schema") != SCHEMA:
        raise _bad_registry(f"schema {doc.get('schema')!r} (this engine reads schema {SCHEMA})")
    doms = doc.get("domains")
    if not isinstance(doms, dict) or not doms:
        raise _bad_registry("`domains` is empty or not an object")
    for did, e in doms.items():
        if not isinstance(did, str) or not _ID.fullmatch(did):
            raise _bad_registry(f"domain id {did!r} must be lower-case letters, digits, - or _ (no +)")
        bad = []
        if not isinstance(e, dict):
            raise _bad_registry(f"{did} is not an object")
        for k in ("label", "approver"):
            if not _bilingual(e.get(k)):
                bad.append(f"`{k}` needs Arabic and English text")
        for k in ("reference", "lexicon"):
            v = e.get(k)
            if not isinstance(v, str) or not v.strip() or any(".." in P(v).parts or P(v).anchor
                                                               for P in (PureWindowsPath, PurePosixPath)):
                bad.append(f"`{k}` must be a relative file name")
        v = e.get("verdicts")
        if not (isinstance(v, list) and v and all(isinstance(x, str) and x for x in v) and len(set(v)) == len(v)
                and "ok" in v):
            bad.append("`verdicts` must be distinct names including ok")
        elif did == "medical" and "needs-doctor-approval" not in v:
            bad.append("medical keeps the verdict needs-doctor-approval (an existing guard)")
        if not isinstance(e.get("always_on"), bool):
            bad.append("`always_on` must be true or false")
        elif did in ALWAYS_ON and not e["always_on"]:
            bad.append(f"{did} review stays on for every client (an existing guard)")
        if bad:
            raise _bad_registry(f"{did}: " + "; ".join(bad))
    missing = [d for d in ALWAYS_ON if d not in doms]
    if missing:
        raise _bad_registry(f"{' and '.join(missing)} must stay in the registry (always-on review)")
    return doms


def lexicon(domain: str) -> dict:
    """A domain's trigger lexicon, validated (rules: terms or a pattern; optional supporting rules and zones)."""
    entry = registry().get(domain)
    if entry is None:
        raise Guidance(f"{domain!r} is not a review domain", f"Use one of: {', '.join(sorted(registry()))}")
    f = REGISTRY_DIR / entry["lexicon"]
    doc = read_json(f)
    where = str(f)
    how = "Fix the lexicon file (schema 1: rules with an id and terms or a pattern), or reinstall the plugin"
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise Guidance(f"the {domain} trigger lexicon is missing or not schema {SCHEMA}", how, where=where)
    for part in ("rules", "supporting"):
        rules = doc.get(part, [])
        if not isinstance(rules, list) or (part == "rules" and not rules):
            raise Guidance(f"the {domain} lexicon's `{part}` is not a list of rules", how, where=where)
        for r in rules:
            ok = isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"]
            if ok and "pattern" in r:
                try:
                    re.compile(r["pattern"])
                except (re.error, TypeError):
                    ok = False
            elif ok:
                ok = isinstance(r.get("terms"), list) and all(isinstance(t, str) and _WORD.search(t)
                                                              for t in r["terms"])
            if not ok:
                raise Guidance(f"the {domain} lexicon has a bad rule: {str(r)[:120]}", how, where=where)
    for r in doc.get("rules", []) + doc.get("supporting", []):
        if not isinstance(r.get("zone_hideable", False), bool):
            raise Guidance(f"the {domain} lexicon's rule {r['id']} has zone_hideable {r['zone_hideable']!r}",
                           how + " (zone_hideable is true or false)", where=where)
    for z in doc.get("zones", []):
        if isinstance(z, dict) and not isinstance(z.get("hides", True), bool):
            raise Guidance(f"the {domain} lexicon's zone {z.get('id')!r} has hides {z['hides']!r}",
                           how + " (hides is true or false)", where=where)
        if not (isinstance(z, dict) and isinstance(z.get("id"), str) and
                ((isinstance(z.get("open"), str) and isinstance(z.get("close"), str) and z["open"] and z["close"]) or
                 (isinstance(z.get("after"), list) and isinstance(z.get("quotes"), list) and
                  all(isinstance(q, str) and len(q) == 2 for q in z["quotes"])))):
            raise Guidance(f"the {domain} lexicon has a bad zone: {str(z)[:120]}", how, where=where)
    return doc


def structure_problems() -> list:
    """What each registry entry lacks: its checker guidance, its lexicon or an eval case (`[]` = complete)."""
    out = []
    for did, e in sorted(registry().items()):
        ref = REFERENCES_DIR / e["reference"]
        if not ref.is_file():
            out.append({"domain": did, "missing": "reference", "path": ref.as_posix()})
        try:
            lexicon(did)
        except (Guidance, ValueError):
            out.append({"domain": did, "missing": "lexicon", "path": (REGISTRY_DIR / e["lexicon"]).as_posix()})
        if not any(_eval_case(p) for p in sorted(EVALS_DIR.glob(f"review-{did}-*/case.yaml"))):
            out.append({"domain": did, "missing": "eval",
                        "path": (EVALS_DIR / f"review-{did}-*" / "case.yaml").as_posix()})
    return out


def _eval_case(f: Path) -> bool:
    """A case file the eval runner reads: flat under evals/ (tests/test_evals.py) and named after its folder."""
    try:
        text = f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return re.search(rf"(?m)^name:\s*['\"]?{re.escape(f.parent.name)}['\"]?\s*$", text) is not None


# ---------------------------------------------------------------------------------------------- client set and key
def _canon(ids, reg: dict, where: str) -> list:
    if isinstance(ids, (str, bytes)) or not isinstance(ids, (list, tuple, set, frozenset)):
        raise Guidance(f"{where} must be a list of review domains, got {ids!r}",
                       f"Use a list such as [\"business\"]; the domains are: {', '.join(sorted(reg))}")
    out = set()
    for x in ids:
        d = x.strip().lower() if isinstance(x, str) else None
        if not d or d not in reg:
            raise Guidance(f"{where} names {x!r}, which is not a review domain",
                           f"Use only: {', '.join(sorted(reg))} (a new domain is added to the registry first)")
        out.add(d)
    return sorted(out)


def review_domain_key(ids) -> str:
    """The canonical key of a client set: `ai+business+medical` (M1-T2). Unknown ids are refused, never mapped."""
    got = _canon(ids, registry(), "the review-domain list")
    if not got:
        raise Guidance("the review-domain list is empty", "Pass the client set (it always holds the always-on domains)")
    missing = [d for d in ALWAYS_ON if d not in got]
    if missing:                          # a raw profile list must never drop an always-on review from the key
        raise Guidance(f"the review-domain list {got} lacks the always-on {' and '.join(missing)}",
                       "Pass client_set(), which adds the always-on domains (medical and ai review every client)")
    return "+".join(got)


def _profile(profile) -> dict:
    p = load_config("profile.json") if profile is None else profile
    return p if isinstance(p, dict) else {}


def client_set(profile: dict | None = None) -> tuple:
    """The profile's domains ∪ the legacy `domain` ∪ the always-on ones, sorted. Refuses an unknown id, naming it."""
    reg = registry()
    p = _profile(profile)
    ids: list = []
    if p.get("review_domains") is not None:
        ids += _canon(p["review_domains"], reg, "profile.json `review_domains`")
    legacy = p.get("domain")
    lv = " ".join(legacy.split()).lower() if isinstance(legacy, str) else None
    if legacy is not None and lv not in (*LEGACY_DOMAINS, TEMPLATE_DOMAIN):
        raise Guidance(f"profile.json `domain` is {legacy!r}, which is not a subject area",
                       "Use general, medical or religious; other review domains (business, ai) go in `review_domains`")
    if lv in reg:
        ids.append(lv)
    ids += [d for d, e in reg.items() if e["always_on"]] + list(ALWAYS_ON)
    return tuple(sorted(set(ids)))


def detect_mode(profile: dict | None = None) -> str:
    """profile.json `review_detect`: review (default) | suggest | off."""
    v = _profile(profile).get("review_detect")
    if v is None:
        return "review"
    m = v.strip().lower() if isinstance(v, str) else None
    if m not in MODES:
        raise Guidance(f"profile.json `review_detect` is {v!r}", "Use review (the default), suggest or off")
    return m


# ---------------------------------------------------------------------------------------------- matching
def _term_words(term: str, case: bool) -> list:
    out = []
    for w in re.findall(r"\w+\*?", normalize(term)):
        stem = w.endswith("*")
        w = w.rstrip("*")
        ar = _arabic(w)
        out.append((w if (case or ar) else w.casefold(), stem, ar))
    return out


def _compile_rules(rules: list) -> list:
    """(id, pattern, terms, case, zone-hideable): a terms rule is hideable inside a verse unless it says
    `zone_hideable: false`; a pattern rule only when it says `zone_hideable: true` (a new pattern shows more)."""
    out = []
    for r in rules:
        if "pattern" in r:
            out.append((r["id"], re.compile(r["pattern"], re.IGNORECASE if "i" in str(r.get("flags", "")) else 0),
                        None, False, r.get("zone_hideable") is True))
        else:
            case = bool(r.get("case"))
            out.append((r["id"], None, [_term_words(t, case) for t in r["terms"]], case,
                        r.get("zone_hideable") is not False))
    return out


def _zone_finder(zones: list):
    """norm -> [(start, end, zone id, hides)]. Every zone counts for its domain; only a CLOSED bracket zone hides (a
    lexicon may say `hides: false` on one). A zone left open hides nothing (an unclosed ﴿ must never swallow a price
    after it), nor does a quotation after a citation («ربنا قال» is everyday speech)."""
    brackets, quoted = [], []
    for z in zones:
        if "after" in z:
            phrases = "|".join(re.escape(normalize(a)) for a in z["after"])
            opens = "".join(re.escape(q[0]) for q in z["quotes"])
            between = "|".join(re.escape(normalize(b)) for b in sorted(z.get("between", []), key=len, reverse=True))
            gap = rf"(?:\s+(?:{between})){{0,2}}" if between else ""
            quoted.append((z["id"], re.compile(rf"(?:{phrases}){gap}\s*[:،,]?\s*([{opens}])"),
                           {q[0]: q[1] for q in z["quotes"]}))
        else:
            brackets.append((z["id"], normalize(z["open"]), normalize(z["close"]), z.get("hides") is not False))

    def find(norm: str) -> list:
        spans = []
        for zid, opener, closer, hides in brackets:
            i = norm.find(opener)
            while i >= 0:
                j = norm.find(closer, i + len(opener))
                k = norm.find(opener, i + len(opener))
                if j < 0 or 0 <= k < j:          # never closed, or opened again first: this one is left open
                    spans.append((i, len(norm) if j < 0 else k, zid, False))
                    i = k
                    continue
                spans.append((i, j + len(closer), zid, hides))
                i = norm.find(opener, j + len(closer))
        for zid, pat, closers in quoted:
            starts = [m for m in pat.finditer(norm)]
            for n, m in enumerate(starts):
                q = m.start(1)
                j = norm.find(closers[m.group(1)], q + 1)
                k = norm.find(m.group(1), q + 1)
                nxt = starts[n + 1].start() if n + 1 < len(starts) else -1
                stop = min(x for x in (k, nxt, len(norm)) if x >= 0)
                spans.append((q, j + 1 if 0 <= j < stop else stop, zid, False))
        return spans
    find.marks = tuple(sorted({m for _z, opener, closer, _h in brackets for m in (opener, closer)}))   # ﴿ ﴾
    return find


def matchers() -> list:
    """Every registry domain's compiled lexicon: (domain, rules, supporting, zone finder). Built once per scan."""
    out = []
    for did in sorted(registry()):
        lex = lexicon(did)
        out.append((did, _compile_rules(lex["rules"]), _compile_rules(lex.get("supporting", [])),
                    _zone_finder(lex.get("zones", []))))
    return out


def _word_ok(form: tuple, word: str, stem: bool, ar: bool, case: bool) -> bool:
    """`form` = (token, its candidates, its case-folded form), worked out once per token."""
    tok, cands, folded = form
    if ar:
        return any(c.startswith(word) for c in cands) if stem else word in cands
    t = tok if case else folded
    return t == word or (stem and t.startswith(word))


def _token_forms(tokens: list):
    """(forms, index): each token's form for _word_ok, and where each exact word can start a term (an Arabic word by
    any candidate, a Latin one as written and case-folded), so a term is tried only where its first word fits."""
    forms, index = [], {}
    for i, (tok, _a, _b) in enumerate(tokens):
        form = (tok, _candidates(tok), tok.casefold())
        forms.append(form)
        for key in {("ar", c) for c in form[1]} | {("case", tok), ("fold", form[2])}:
            index.setdefault(key, []).append(i)
    return forms, index


def _rule_hits(norm: str, tokens: list, rules: list) -> list:
    """[(start, end, rule, hideable)]."""
    hits = []
    forms = index = None
    for rid, pat, terms, case, hideable in rules:
        if pat is not None:
            spans = [(m.start(), m.end()) for m in pat.finditer(norm) if m.group(0).strip()]
        else:
            if forms is None:
                forms, index = _token_forms(tokens)
            spans = []
            for words in terms:
                n = len(words)
                word, stem, ar = words[0]
                starts = (range(len(tokens)) if stem else
                          index.get(("ar" if ar else "case" if case else "fold", word), ()))
                for i in starts:
                    if i + n <= len(tokens) and all(_word_ok(forms[i + k], *words[k], case) for k in range(n)):
                        spans.append((tokens[i][1], tokens[i + n - 1][2]))
        hits += [(a, b, rid, hideable) for a, b in spans]
    return hits


def _recited(tokens: list, words: dict) -> list:
    """[(start, end, owner)]: runs of speech words that repeat an on-screen zone's words (a recited verse): at least
    RECITED words in a row, or the whole evidence."""
    out = []
    for owner, ws in sorted(words.items()):
        run: list = []
        for t in tokens + [None]:
            if t is not None and t[0] in ws:
                run.append(t)
                continue
            if run and (len(run) >= RECITED or len(run) == len(tokens)):
                out.append((run[0][1], run[-1][2], owner))
            run = []
    return out


def _detect(text: str, ms: list, recited_words: dict | None = None):
    """{domain: [(start, end, rule, words)]} and the hiding-zone words per owning domain, over every reading of the
    text (a later reading adds only new domains). `recited_words` (owner -> words, from the screen's hiding
    zones) hides another domain's hideable hit inside the speech's recitation of that zone. A text longer than WINDOW
    is read window by window and the rows are merged (a row seen in two windows counts once); a second pass then adds
    the supporting rows of every domain found, from every window."""
    out: dict = {}
    zone_words: dict = {}
    recited_words = recited_words or {}

    def merge(did, rows):
        have = out.setdefault(did, [])
        seen = {(r[2], r[3]) for r in have}
        have += [r for r in rows if (r[2], r[3]) not in seen]

    parts = _windows(_nfkc(text))
    for part in parts:
        found: dict = {}
        for norm in _readings(part):
            for did, rows in _detect_one(norm, ms, recited_words, zone_words).items():
                found.setdefault(did, rows)
        for did, rows in found.items():
            merge(did, rows)
    support = frozenset(did for did, _r, sup, _f in ms if did in out and sup)
    if len(parts) > 1 and support:
        for part in parts:
            for norm in _readings(part):
                for did, rows in _detect_one(norm, ms, recited_words, zone_words, support).items():
                    merge(did, rows)
    return {d: out[d] for d in sorted(out)}, zone_words


def _detect_one(norm: str, ms: list, recited_words: dict, zone_words: dict, support_only: frozenset | None = None):
    """{domain: rows} for one reading. With `support_only` (domains found elsewhere in the text), only those domains'
    supporting rules are matched. Rules read the text with the zone brackets as spaces (same length), so a claim that
    runs past a bracket («﴿ خصم ﴾ ٥٠٪») is matched whole and, reaching outside the zone, is never hidden by it."""
    scan = norm
    for mark in sorted({m for *_x, find in ms for m in getattr(find, "marks", ())}):
        scan = scan.replace(mark, " " * len(mark))
    tokens = [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(scan)]
    zones = []
    for did, _r, _s, find in ms:
        for a, b, zid, hides in find(norm):
            hides = hides and not _never_hidden(norm[a:b])           # a "verse" with an amount: a code floor
            zones.append((a, b, did, zid, hides))
            if hides:
                zone_words.setdefault(did, set()).update(_WORD.findall(norm[a:b]))
    hide = [(a, b, owner) for a, b, owner, _z, hides in zones if hides] + _recited(tokens, recited_words)
    out: dict = {}
    for did, rules, supporting, _f in ms:
        def keep(h):
            return not (h[3] and any(za <= h[0] and h[1] <= zb for za, zb, owner in hide if owner != did))
        if support_only is not None:
            hits = [h for h in _rule_hits(scan, tokens, supporting) if keep(h)] if did in support_only else []
        else:
            hits = [h for h in _rule_hits(scan, tokens, rules) if keep(h)]
            hits += [(a, b, zid, False) for a, b, owner, zid, _h in zones if owner == did]
            if hits:
                hits += [h for h in _rule_hits(scan, tokens, supporting) if keep(h)]
        if hits:
            seen, rows = set(), []
            for a, b, rid, _h in sorted(hits, key=lambda h: (h[0], h[1], h[2])):
                words = norm[a:b].strip()
                if (rid, words) not in seen:
                    seen.add((rid, words))
                    rows.append((a, b, rid, words))
            out[did] = rows
    return out


def detect(text: str, ms: list | None = None) -> dict:
    """{domain: [{"rule", "match"}]} for one text, in text order (match = the normalised words that hit)."""
    found, _z = _detect(text, ms if ms is not None else matchers())
    return {d: [{"rule": r, "match": w} for _a, _b, r, w in rows] for d, rows in sorted(found.items())}


# ---------------------------------------------------------------------------------------------- the plan
def _plan_events(paths: Paths, kind: str) -> dict:
    """event id -> the compiled event (a clip) or scene (a motion video), for its evidence and the files it shows."""
    from .review_flags import MOTION_PLAN, TIMELINE_SPEC
    from .stamps import read_compiled
    doc = read_compiled(paths.p(TIMELINE_SPEC if kind == "timeline" else MOTION_PLAN)) or {}
    out: dict = {}
    for e in doc.get("events" if kind == "timeline" else "scenes") or []:
        eid = (e.get("event_id") if kind == "timeline" else e.get("id")) if isinstance(e, dict) else None
        if isinstance(eid, str) and eid and eid not in out:
            out[eid] = e
    return out


def _shown_files(e: dict) -> list:
    """The files one event shows: a graphic's image or B-roll video, a motion scene's image elements."""
    params = e.get("params") if isinstance(e.get("params"), dict) else {}
    files = [params[k] for k in ("image", "video") if isinstance(params.get(k), str)]
    files += [el["path"] for el in e.get("elements") or []
              if isinstance(el, dict) and el.get("kind") == "image" and isinstance(el.get("path"), str)]
    return files


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _real(p: Path) -> str:
    """A comparable real path: NFC (macOS folder names come back in NFD); case folded where the file system usually
    ignores case (Windows, macOS)."""
    r = _nfc(str(Path(p).resolve()))
    return r.casefold() if sys.platform in ("win32", "darwin") else r


def _ai_files(paths: Paths, events: dict) -> dict:
    """event id -> the files it shows that the asset manifest marks `ai_generated: true` (M4), in plan order. A file
    matches by its client-relative path, or by the real path of the asset or of its display copy."""
    from . import client_db
    man = client_db.load(paths, "asset-manifest.json", {}) or {}
    gen: set = set()
    for a in man.get("assets") or []:
        if isinstance(a, dict) and isinstance(a.get("rel"), str) and a.get("ai_generated") is True:
            gen.add(_nfc(a["rel"]))
            gen.update(_real(paths.root / f) for f in (a["rel"], a.get("display_derivative")) if isinstance(f, str) and f)
    out: dict = {}
    for eid, e in events.items():
        files = [f for f in _shown_files(e) if _nfc(f) in gen or _real(paths.root / f) in gen]
        if files:
            out[eid] = list(dict.fromkeys(files))
    return out


def line_requirements(paths: Paths, kind: str, index: dict, cs: tuple | None = None, mode: str | None = None):
    """(lines, ai_assets) for a plan the caller already read (review-flags passes its own `_current` result, so the
    check and the write see one plan). Each line: event_id, text, evidence, start_s, end_s, detected, extra, required,
    suggested. `ai_assets` lists every event that shows an AI-generated file, with or without on-screen words (`line`
    false: no review-flags row can name it today; the disclosure check covers it, M1-T2/M1-T4)."""
    cs = client_set() if cs is None else cs
    mode = detect_mode() if mode is None else mode
    events = _plan_events(paths, kind)
    ai_files = _ai_files(paths, events)
    ms = matchers() if mode != "off" else []
    lines = []
    for eid, line in index.items():
        if not line["text"]:
            continue
        ev = events.get(eid, {}).get("evidence")
        ev = ev if isinstance(ev, str) and ev.strip() else None
        detected: dict = {}
        if mode != "off":
            screen, zone_words = _detect(line["text"], ms)
            speech = _detect(ev, ms, zone_words)[0] if ev else {}
            for src, found in (("screen", screen), ("speech", speech)):
                for d, rows in found.items():
                    detected.setdefault(d, []).extend({"rule": r, "match": w, "in": src} for _a, _b, r, w in rows)
            for f in ai_files.get(eid, []):
                detected.setdefault("ai", []).append({"rule": "ai-generated-asset", "match": f, "in": "asset"})
        detected = {d: detected[d] for d in sorted(detected)}
        extra = sorted(set(detected) - set(cs))
        lines.append({"event_id": eid, "text": line["text"], "evidence": ev, "start_s": line["start_s"],
                      "end_s": line["end_s"], "detected": detected, "extra": extra,
                      "required": sorted(set(cs) | set(extra if mode == "review" else [])),
                      "suggested": extra if mode == "suggest" else []})
    texts = {x["event_id"] for x in lines}
    assets = [{"event_id": eid, "file": f, "line": eid in texts} for eid, fs in ai_files.items() for f in fs]
    return lines, assets


def scan(paths: Paths) -> dict:
    """`reel review-scan`: per plan line with on-screen text, the domains whose triggers hit and why, and the flags the
    reviewer must cover on it; plus every AI-generated file the plan shows. Deterministic and read-only."""
    from .review_flags import _current
    cs = client_set()
    key = review_domain_key(cs)
    mode = detect_mode()
    try:
        kind, index, fp = _current(paths)
    except Guidance as g:                 # the same refusals as review-flags, with this command's next step
        raise Guidance(g.error, g.how.replace("send the review again", "run `reel review-scan` again"),
                       g.where) from None
    lines, assets = line_requirements(paths, kind, index, cs, mode)
    return {"schema": SCHEMA, "plan_kind": kind, "plan_fingerprint": fp, "key": key, "client_set": list(cs),
            "review_detect": mode, "lines_total": len(lines), "lines": lines, "ai_assets": assets, "note": NOTE}


def required_flags(paths: Paths) -> dict:
    """event id -> the flags a review must cover on that line (the client set + its detected required domains)."""
    return {x["event_id"]: x["required"] for x in scan(paths)["lines"]}


def review_domains_detected(paths: Paths) -> dict:
    """event id -> the domains detected in that line (whatever the client set), for the reviewer's hints."""
    return {x["event_id"]: sorted(x["detected"]) for x in scan(paths)["lines"]}
