"""Caption rules that code enforces after the language model (deterministic, always applied)."""
import re

FATHATAN = chr(0x64B)
TATWEEL = chr(0x640)
_ALEF, _HAMZA_ALEFS = chr(0x627), chr(0x623) + chr(0x625)

# Arabic marks: honorifics, harakat, dagger alef, Quranic marks (fathatan is kept separately)
_DIACRITICS = re.compile("[" + "".join(
    "%s-%s" % (chr(a), chr(b)) for a, b in [(0x610, 0x61A), (0x64C, 0x65F), (0x6D6, 0x6ED)]
) + chr(0x670) + "]")

_PUNCT_CHARS = '.,!?:;"()[]{}*_~`\\/|<>' + "".join(chr(c) for c in (
    0x60C, 0x61B, 0x61F, 0x6D4,          # Arabic comma, semicolon, question mark, full stop
    0x2026, 0x201C, 0x201D, 0x2018,      # ellipsis, curly quotes
    0xAB, 0xBB,                          # guillemets
))
_PUNCT = re.compile("[" + re.escape(_PUNCT_CHARS) + "]")
_DASHES = re.compile("[-" + chr(0x2013) + chr(0x2014) + "]")
# apostrophes are dropped unless they sit inside a Latin word (don't)
_APOS = re.compile("(?<![A-Za-z])['" + chr(0x2019) + "]|['" + chr(0x2019) + "](?![A-Za-z])")
_SPACES = re.compile(r"\s+")

# انت / انتو / انتي / انتم / انتن (with optional و ف ب prefix) never take a hamza
_INTA = re.compile(r"(?<!\w)([وفب]?)[" + _HAMZA_ALEFS + r"](نت(?:و|ي|م|ن)?)(?!\w)")


def strip_punct(text: str) -> str:
    text = _DASHES.sub(" ", text)
    text = _APOS.sub("", text)
    text = _PUNCT.sub("", text)
    return _SPACES.sub(" ", text).strip()


def strip_diacritics(text: str) -> str:
    """remove every Arabic diacritic except fathatan (جدًا، مثلًا); shadda goes too"""
    text = _DIACRITICS.sub("", text)
    return text.replace(chr(0x651), "")


def capitalize_latin(text: str) -> str:
    def cap(tok: str) -> str:
        if not re.search("[A-Za-z]", tok) or tok.isupper():
            return tok
        i = next(k for k, c in enumerate(tok) if c.isalpha())
        return tok[:i] + tok[i].upper() + tok[i + 1:]
    return " ".join(cap(t) for t in text.split(" "))


def apply_glossary(text: str, glossary: dict) -> str:
    for correct, variants in glossary.items():
        for v in sorted(variants, key=len, reverse=True):
            if not v.strip():
                continue
            pat = re.compile(r"(?<!\w)" + re.escape(v.strip()) + r"(?!\w)", re.IGNORECASE)
            text = pat.sub(correct, text)
    return text


def enforce(text: str, glossary: dict, mode: str = "ar") -> str:
    """mode "ar": Latin words are terms -> Capital Case each word; other modes keep the model's casing"""
    text = strip_punct(text)
    text = strip_diacritics(text)
    text = _INTA.sub(lambda m: m.group(1) + _ALEF + m.group(2), text)
    text = apply_glossary(text, glossary or {})
    if mode == "ar":
        text = capitalize_latin(text)
    return _SPACES.sub(" ", text).strip()
