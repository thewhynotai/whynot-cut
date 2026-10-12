"""Remove what the speaker never said: Whisper loops, credit-line hallucinations, words sitting on silence."""
import numpy as np

from .rules import strip_diacritics, strip_punct

# credit lines Whisper invents on silence (normalized word sequences)
HALLUCINATIONS = [
    "ترجمة نانسي قنقر", "نانسي قنقر", "اشتركوا في القناة", "subtitles by the amara org community",
]


def _norm(w: str) -> str:
    return strip_diacritics(strip_punct(w)).lower()


def drop_loops(words: list, max_repeat: int = 3) -> list:
    """a run of the same word longer than max_repeat is a decoding loop: drop the whole run"""
    out, i = [], 0
    while i < len(words):
        j = i
        while j + 1 < len(words) and _norm(words[j + 1]["w"]) == _norm(words[i]["w"]):
            j += 1
        if j - i + 1 <= max_repeat:
            out.extend(words[i:j + 1])
        i = j + 1
    return out


def drop_hallucinations(words: list) -> list:
    seqs = [h.split(" ") for h in HALLUCINATIONS]
    norm = [_norm(w["w"]) for w in words]
    kill = set()
    for sq in seqs:
        for i in range(len(words) - len(sq) + 1):
            if norm[i:i + len(sq)] == sq:
                kill.update(range(i, i + len(sq)))
    return [w for k, w in enumerate(words) if k not in kill]


def speech_threshold(env_db: np.ndarray) -> float:
    """silence/speech threshold. The speech level comes only from frames clearly above the noise floor,
    so a long stretch of room tone with little dialogue cannot pull it down into the noise."""
    floor = max(-70.0, float(np.percentile(env_db, 10)))
    above = env_db[env_db > floor + 10.0]
    speech = float(np.percentile(above, 90)) if len(above) else floor + 10.0
    return floor + (speech - floor) * 0.30


def _has_arabic(t: str) -> bool:
    return any(0x600 <= ord(c) <= 0x6FF for c in t)


def _has_latin(t: str) -> bool:
    return any("a" <= c.lower() <= "z" for c in t)


def clean_garbled(words: list, mode: str = "ar") -> list:
    """Whisper junk: Arabic glued to Latin ("غيرqub") keeps its Arabic part, symbol-only tokens go,
    and in Arabic mode low-confidence Latin fragments ("g", "up") that come in a run or alone as a letter go."""
    out = []
    for w in words:
        t = w["w"]
        if not any(c.isalnum() for c in t):
            continue
        if _has_arabic(t) and _has_latin(t):
            t = "".join(c for c in t if not ("a" <= c.lower() <= "z")).strip()
            if not t:
                continue
            w = dict(w, w=t)
        out.append(w)
    if mode != "ar":
        return out

    def junk(w):
        t = w["w"].strip(".,!?;:")
        return _has_latin(t) and not _has_arabic(t) and w.get("score", 1.0) < 0.1
    keep = []
    for i, w in enumerate(out):
        if junk(w):
            single_letter = len(w["w"].strip(".,!?;:")) <= 1
            in_run = (i > 0 and junk(out[i - 1])) or (i + 1 < len(out) and junk(out[i + 1]))
            if single_letter or in_run:
                continue
        keep.append(w)
    return keep


_MUSIC = (chr(0x266A), chr(0x266B), chr(0x266C))


def drop_nonspeech_tags(words: list) -> list:
    """Whisper marks non-speech as [موسيقى], (Music), ♪ ... - never caption those"""
    out, depth = [], 0
    for w in words:
        t = w["w"].strip()
        opens, closes = t.count("[") + t.count("("), t.count("]") + t.count(")")
        inside = depth > 0 or opens > 0
        depth = max(0, depth + opens - closes)
        if inside or any(m in t for m in _MUSIC):
            continue
        out.append(w)
    return out


def drop_unspoken(words: list, env_db: np.ndarray, hop: float = 0.01) -> list:
    """drop a word only when its aligned span is silent AND the aligner had no confidence AND no speech is near"""
    th = speech_threshold(env_db)
    loud = env_db > th
    n = len(env_db)

    def fr(t):
        return int(min(n, max(0, round(t / hop))))

    def said(w):
        a, b = fr(w["s"]), max(fr(w["s"]) + 1, fr(w["e"]))
        if loud[a:b].mean() > 0.2 or w.get("score", 1.0) >= 0.1:
            return True
        near = loud[fr(w["s"] - 0.3):fr(w["e"] + 0.3)]
        return bool(near.any())
    return [w for w in words if said(w)]
