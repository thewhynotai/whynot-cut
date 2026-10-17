# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""K-T7 (Phase 4 Task 67): repeated takes, numbered keep/drop/undo.

Built on Task 25 (cut_proposals: the shared normaliser, the take similarity, the starting values). `reel takes` numbers
the sentences of a clip (1..N, from the words alone, so the same transcript always gives the same numbers), groups the
sentences said more than once («٤ و ٥ نفس الجملة: الأفضل ٥ — كاملة ومن غير تلعثم») and proposes the better take from
measured features only: closed by the transcript or not, covering the line, restarts and hesitation sounds inside,
clipping and level (only when audio is given), mean word confidence; a tie keeps the later take. The takes are read
for meaning with the reader Task 25 uses (differences.py: numbers and doses, negation, timing). When they differ in
meaning, NO take is proposed: the line names what differs, whatever else differs too («١ و ٢ نفس الجملة، بس مختلفين في
المعنى — ⚠ نفي: … — اسمعهم واختار انت»), and the editor decides. A content word that differs («السكر» / «الضغط», up to
four of them) is named with a ⚠ while the better take is still proposed (the same rule as Task 25: only the three
meaning kinds block a proposal).

`--drop 4,7 --keep 5` writes the choice into the plan's own cut list (edit-decisions.json global.cut_words, entries
"TK-<n> …" with the take's range), `--undo` goes back one step, as many times as there are steps; an undo never
overwrites a plan that changed after that step. The numbers must come from a listing of the same transcript and the
same groups (`reel takes` first). The plan changes, so `reel plan` and a new approval come before anything is cut.
A refusal writes nothing."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
from collections import Counter

from .. import cut_proposals as CP
from . import differences as D
from .numbers import fold
from .risk_words import _negation

FILE = "01_analysis/takes.json"
HISTORY = "01_analysis/takes-history.json"
ED = "01_analysis/edit-decisions.json"
WORDS = "02_transcription/words.json"
_PUNCT = re.compile(r"[.!?؟…]\s*$")
_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_TO_WESTERN = str.maketrans({**{chr(0x660 + i): str(i) for i in range(10)}, **{chr(0x6F0 + i): str(i) for i in range(10)}})
CLIP_LEVEL = 0.99          # a sample at or above this (of full scale) is clipped
CLIP_SHARE = 0.001         # a take clips when more than this share of its samples is clipped
QUIET_DB = 10.0            # a take this many dB below the group's loudest is "too quiet"


def _settings(cfg, ctx=None):
    return cfg or CP.settings(ctx)


def sentences(words, cfg=None) -> list:
    """The clip's sentences, numbered in time order: {n, word_ids, text, start_ms, end_ms, toks, punct, probs}. A
    sentence ends at «.»/«؟»/"?"/"!", at a pause of complete_pause_ms or more, or where the transcript's segment
    changes."""
    V = _settings(cfg)["values"]
    ws = CP.clean_words(words)
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        last = i == len(ws) - 1
        end = last or bool(_PUNCT.search(w["word"])) or ws[i + 1]["start_ms"] - w["end_ms"] >= V["complete_pause_ms"] \
            or w.get("segment_id") != ws[i + 1].get("segment_id")
        if end:
            out.append({"n": len(out) + 1, "word_ids": [x["id"] for x in cur],
                        "text": " ".join(x["word"].strip() for x in cur), "start_ms": cur[0]["start_ms"],
                        "end_ms": cur[-1]["end_ms"], "toks": [t for x in cur for t in [CP.norm_word(x["word"])] if t],
                        "said": [_said(x["word"]) for x in cur if CP.norm_word(x["word"])],
                        "punct": bool(_PUNCT.search(cur[-1]["word"])), "speaker": cur[0].get("speaker"),
                        "probs": [x.get("probability") for x in cur]})
            cur = []
    return out


def _said(word) -> str:
    """A word as the transcript writes it, without the sentence's marks («الضغط». -> الضغط; "doesn't" stays)."""
    return D._EDGE_PUNCT.sub("", str(word or "").strip())


def _fragments(toks: list) -> set:
    """Positions of cut-off starts restarted at once («مه مهم»)."""
    return {k for k in range(len(toks) - 1)
            if len(toks[k]) >= 2 and toks[k + 1].startswith(toks[k]) and toks[k + 1] != toks[k]}


def _content_words(toks: list, F: dict) -> set:
    frag = _fragments(toks)
    return {t for k, t in enumerate(toks) if k not in frag and CP._content(t, F)}


def _same(a: dict, b: dict, F: dict, V: dict) -> bool:
    """Two sentences are takes of one line: one speaker, the shorter matches the start of the longer (similarity of
    the retake rule) with enough shared content words."""
    if a.get("speaker") != b.get("speaker"):
        return False
    A, B = a["toks"], b["toks"]
    shared = {t for t in set(A) & set(B) if CP._content(t, F)}
    if len(shared) < V["retake_min_shared"]:
        return False
    sim = max(CP.similarity(A, B[:len(A) + 1]), CP.similarity(B, A[:len(B) + 1]))
    return sim >= V["retake_score"]


def _differences(takes: list, F: dict) -> dict:
    """What the takes do not share. Meaning, always (the shared reader, every pair of takes): "numbers", "negation",
    "timing" = the words that carry it, as said, and "pairs" = [{"takes": [n, m], kind: {"a": [...], "b": [...]}}].
    An earlier take cut short (not closed, fewer words) is read only as far as it goes: «خدي الـ vitamin D» then «… ألف
    وحدة كل يوم.» is not a difference ("cut_short" keeps that pair: the line names what it left out, and it counts
    if the cut-off take would be the proposal). A later shorter take is always read whole.
    Content words where the full takes overlap (an abandoned start is left out: it only stopped early), as said
    ("words"), only when four or fewer differ: a longer list means a
    reworded take, not a slip. A negation word is not a content word, and a negated verb is compared without its
    negation («مبيقللش» = «بيقلل» + a negation, which the meaning reader already counts)."""
    out, pairs, short, cut = {}, [], [], set()
    for i in range(len(takes)):
        for j in range(i + 1, len(takes)):
            a, b = takes[i], takes[j]
            d = D.compare(a["said"], b["said"])
            # an abandoned start: the rest is unsaid, not said otherwise (read only as far as it goes)
            stopped = _cut_short(a, b) is not None and not D.compare(a["said"], b["said"][:len(a["said"])])
            if stopped:
                cut.add(a["n"])
            if not d:
                continue
            if stopped:
                short.append({"takes": [a["n"], b["n"]], "cut_short": a["n"], **d})
                continue
            pairs.append({"takes": [a["n"], b["n"]], **d})
    for kind in D._ORDER:
        said = [w for p in pairs if kind in p for side in ("a", "b") for w in p[kind][side]]
        if said:
            out[kind] = list(dict.fromkeys(said))
    meaning = {w for kind in D._ORDER for phrase in out.get(kind, []) + [x for p in short if kind in p
                                                                           for side in ("a", "b") for x in p[kind][side]]
               for w in phrase.split()}
    full = [t for t in takes if t["n"] not in cut]       # an abandoned start's words are a start of the others'
    n = min((len(t["toks"]) for t in full), default=0)
    shown = {}                                       # compared without a clitic, shown as said («للسكر»)
    words = []
    for t in full if len(full) > 1 else []:
        s = set()
        frag = _fragments(t["toks"])
        for k, (w, said) in enumerate(zip(t["toks"][:n + 1], t["said"][:n + 1])):
            neg = _negation(fold(w))
            if k in frag or neg == "word" or said.lower().replace("’", "'").endswith("n't"):
                continue
            if neg == "verb":                            # «مبيقللش» -> «بيقلل», «ماتاخدش» -> «تاخد»
                w = w[2:-1] if w.startswith("ما") else w[1:-1]
            if CP._content(w, F) and not _is_number(w):
                shown.setdefault(_bare(w), said)
                s.add(_bare(w))
        words.append(s)
    common = set.intersection(*words) if words else set()
    apart = {w for s in words for w in s} - common
    differ = sorted(x for x in {shown[w] for w in apart} if x not in meaning)
    if differ and len(apart) <= 4:
        out["words"] = differ
    if pairs:
        out["pairs"] = pairs
    if short:
        out["cut_short"] = short
    return out


def _cut_short(t: dict, other: dict):
    """t when it is an earlier take abandoned before the end and said again in full by the later one (not closed by
    the transcript, fewer words). A LATER shorter take is a correction that leaves something out: never cut short,
    whatever the transcript's full stops."""
    return t if not t["punct"] and len(t["said"]) < len(other["said"]) else None


def _bare(w: str) -> str:
    """A content word without a leading Arabic clitic («والدواء» = «الدواء»), when enough of it is left."""
    for pre in ("و", "ف", "ب", "ل"):
        if w.startswith(pre) and len(w) - 1 >= 3:
            return w[1:]
    return w


def _is_number(w: str) -> bool:
    """Digits or a spelled number: compared by value already (values_in), never as a word."""
    from .numbers import find_numbers
    return bool(find_numbers([fold(w)]))


def _features(s: dict, all_content: set, F: dict, lang: str, samples, sr) -> dict:
    toks = s["toks"]
    restarts = len(_fragments(toks))
    fillers = sum(1 for t in toks if CP._always(t, F, lang))
    mine = _content_words(toks, F)
    cover = round(len(mine & all_content) / max(1, len(all_content)), 3)
    probs = [p for p in s["probs"] if isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p)]
    f = {"complete": bool(s["punct"]), "covers": cover, "restarts": restarts, "fillers": fillers,
         "confidence": round(sum(probs) / len(probs), 3) if probs else None}
    if samples is not None and sr:
        import numpy as np
        a, b = int(s["start_ms"] * sr / 1000), int(s["end_ms"] * sr / 1000)
        seg = np.asarray(samples[a:b], dtype=np.float64)
        if seg.size:
            f["clipping"] = round(float(np.mean(np.abs(seg) >= CLIP_LEVEL)), 4)
            rms = float(np.sqrt(np.mean(seg * seg)))
            f["level_db"] = round(20 * math.log10(rms), 1) if rms > 0 else -120.0
    return f


def _rank_key(f: dict, idx: int, loudest_db):
    """Higher is better: closed by the transcript, covers the line, fewer restarts and hesitation sounds, no
    clipping, not much quieter than the other takes, clearer; then the later take."""
    clips = f.get("clipping") is not None and f["clipping"] > CLIP_SHARE
    quiet = loudest_db is not None and f.get("level_db") is not None and f["level_db"] < loudest_db - QUIET_DB
    return (f["complete"], f["covers"], -f["restarts"], -f["fillers"], not clips, not quiet, f["confidence"] or 0, idx)


def _ar(n) -> str:
    return str(n).translate(_AR_DIGITS)


def _why(f: dict, tie: bool) -> tuple:
    ar, en = [], []
    if f["complete"]:
        ar.append("كاملة")
        en.append("complete")
    if not f["restarts"] and not f["fillers"]:
        ar.append("من غير تلعثم")
        en.append("no stumbles")
    if f.get("clipping") is not None and f["clipping"] <= CLIP_SHARE:
        ar.append("الصوت مش مقطوع")
        en.append("no clipping")
    if not ar:
        ar.append("أوضح واحدة")
        en.append("the clearest one")
    text_ar = " و".join(ar) if len(ar) < 3 else "، ".join(ar[:-1]) + " و" + ar[-1]
    if tie:
        text_ar += "؛ ولما اتساووا اخترنا الأخيرة"
        en.append("the later take on a tie")
    return text_ar, ", ".join(en)


def _named(p: dict, takes: int, lang: str) -> str:
    """What one pair of takes differs in («نفي: (مفيش) مقابل «مبيقللش»»), with the take numbers when there are more
    than two takes."""
    d_ar, d_en = D.describe({x: p[x] for x in D._ORDER if x in p})
    if takes == 2:
        return d_ar if lang == "ar" else d_en
    a, b = p["takes"]
    return f"{_ar(a)} مقابل {_ar(b)}: {d_ar}" if lang == "ar" else f"{a} vs {b}: {d_en}"


def groups(words, cfg=None, samples=None, sr=0, lang: str = "ar") -> list:
    """Take groups: [{"takes": [sentence + features], "best": n or None (the takes differ in meaning), "differ": {...},
    "line_ar", "line_en"}], in time
    order. A sentence joins the first group whose first take it matches within the retake window (no chains: A~B and
    B~C never pull in a C unlike A)."""
    cfg = _settings(cfg)
    V, F = cfg["values"], cfg["fillers"]
    ss = sentences(words, cfg)
    members = []                      # [[sentence indexes]] with the first take as the group's reference
    for j, s in enumerate(ss):
        for g in members:
            ref = ss[g[0]]
            if s["start_ms"] - ss[g[-1]]["end_ms"] <= V["retake_window_s"] * 1000 and _same(ref, s, F, V):
                g.append(j)
                break
        else:
            members.append([j])
    out = []
    for g in members:
        if len(g) < 2:
            continue
        content = {t for i in g for t in _content_words(ss[i]["toks"], F)}
        takes = []
        for i in g:
            t = {x: ss[i][x] for x in ("n", "word_ids", "text", "start_ms", "end_ms")}
            t["features"] = _features(ss[i], content, F, lang, samples, sr)
            takes.append(t)
        levels = [t["features"].get("level_db") for t in takes if t["features"].get("level_db") is not None]
        loudest = max(levels) if levels else None
        keys = [_rank_key(t["features"], k, loudest) for k, t in enumerate(takes)]
        nums = [t["n"] for t in takes]
        differ = _differences([ss[i] for i in g], F)
        listed = f"{' و '.join(_ar(n) for n in nums)} نفس الجملة"
        listed_en = f"{', '.join(map(str, nums[:-1]))} and {nums[-1]} are the same sentence"
        words_ar = "الكلام (" + "، ".join(differ["words"]) + ")" if differ.get("words") else ""
        words_en = "words (" + ", ".join(differ["words"]) + ")" if differ.get("words") else ""
        best = max(range(len(takes)), key=lambda k: keys[k])
        for p in differ.get("cut_short", []):           # the proposal would be the cut-off take: never past a meaning
            if p["cut_short"] == nums[best]:
                differ.setdefault("pairs", []).append({x: v for x, v in p.items() if x != "cut_short"})
                for kind in D._ORDER:
                    if kind in p:
                        differ[kind] = list(dict.fromkeys(differ.get(kind, []) + p[kind]["a"] + p[kind]["b"]))
        if differ.get("pairs"):                          # the meaning differs: the editor listens and chooses
            what_ar = " | ".join(_named(p, len(nums), "ar") for p in differ["pairs"]) + ("؛ " + words_ar if words_ar else "")
            what_en = " | ".join(_named(p, len(nums), "en") for p in differ["pairs"]) + ("; " + words_en if words_en else "")
            out.append({"takes": takes, "best": None, "differ": differ,
                        "line_ar": f"{listed}، بس مختلفين في المعنى — ⚠ {what_ar} — مش هنقترح أفضل واحدة: "
                                   "اسمعهم واختار انت",
                        "line_en": f"{listed_en}, but they differ in meaning — ⚠ {what_en} — no take is proposed: "
                                   "listen and choose"})
            continue
        tie = sum(1 for k in keys if k[:-1] == keys[best][:-1]) > 1
        why_ar, why_en = _why(takes[best]["features"], tie)
        warn_ar = f" — ⚠ النسخ مختلفة في: {words_ar}، اسمعهم قبل ما تختار" if words_ar else ""
        warn_en = f" — ⚠ the takes differ in: {words_en}; listen before choosing" if words_en else ""
        left = {}                                        # what each abandoned start did not get to say
        for p in differ.get("cut_short", []):
            mine, other = ("a", "b") if p["takes"][0] == p["cut_short"] else ("b", "a")
            for kind in D._ORDER:
                if kind in p:                            # negation lists every word on both sides: only the new ones,
                    said = Counter(p[kind][mine])         # by count («not … and not with milk»: the second is new)
                    new = []
                    for w in p[kind][other]:
                        if said[w]:
                            said[w] -= 1
                        else:
                            new.append(w)
                    left.setdefault(p["cut_short"], {}).setdefault(kind, []).extend(new)
        for n, kinds in left.items():
            said = {k: list(dict.fromkeys(v)) for k, v in kinds.items() if v}
            if said:
                warn_ar += f" — ⚠ {_ar(n)} اتقطعت قبل: " + "؛ ".join(
                    f"{D.LABEL[k][0]} " + "، ".join(f"«{w}»" for w in said[k]) for k in D._ORDER if k in said)
                warn_en += f" — ⚠ {n} stopped before: " + "; ".join(
                    f"{D.LABEL[k][1]} " + ", ".join(f"\"{w}\"" for w in said[k]) for k in D._ORDER if k in said)
        out.append({"takes": takes, "best": nums[best], "differ": differ,
                    "line_ar": f"{listed}: الأفضل {_ar(nums[best])} — {why_ar}" + warn_ar,
                    "line_en": f"{listed_en}: best {nums[best]} — {why_en}" + warn_en})
    return out


# --- project -----------------------------------------------------------------------------------------------------------
def _words(paths):
    from ..errors import Guidance
    f = paths.p(WORDS)
    try:
        data = f.read_bytes()
        doc = json.loads(data.decode("utf-8-sig"))
        if not isinstance(doc.get("words"), list):
            raise TypeError("words is not a list")
    except Exception:  # noqa: BLE001
        raise Guidance("مفيش تفريغ صالح للفيديو ده / no usable transcript for this item "
                       "(02_transcription/words.json is missing or damaged)",
                       "Run `reel transcribe` (or fix the file), then `reel takes` again", where=str(f)) from None
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    lang = "en" if str(meta.get("language") or "").lower().startswith("en") else "ar"
    return doc["words"], hashlib.sha1(data).hexdigest(), lang


def _load(path):
    try:
        s = json.loads(path.read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else None
    except FileNotFoundError:
        return {}
    except Exception:  # noqa: BLE001
        return None


def _write_atomic(path, data: bytes):
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _save(path, doc: dict):
    _write_atomic(path, (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _shape(res: list) -> list:
    return [[t["n"] for t in g["takes"]] for g in res]


def report(paths, ctx=None, samples=None, sr=0) -> dict:
    """The numbered take groups of this item, and the plain lines for the editor (Arabic first). Records which
    transcript, settings and groups the numbers belong to (takes.json), so a later --drop/--keep never points at
    other words."""
    ws, sha, lang = _words(paths)
    cfg = CP.settings(ctx)
    res = groups(ws, cfg, samples, sr, lang)
    _save(paths.p(FILE), {"schema": 2, "words_sha1": sha, "settings_sha1": _cfg_sha(cfg), "groups": _shape(res),
                          "best": [g["best"] for g in res]})
    return {"groups": res, "lines": [g["line_ar"] for g in res], "lines_en": [g["line_en"] for g in res],
            "how": "اختار بالأرقام: `reel takes --drop ٤ --keep ٥`، وتقدر ترجع خطوة بـ `reel takes --undo`. مفيش حاجة "
                   "تتقص قبل ما توافق على الخطة من جديد / choose by number: `reel takes --drop 4 --keep 5`; "
                   "`reel takes --undo` goes back one step; nothing is cut before you approve the plan again"}


def _cfg_sha(cfg: dict) -> str:
    return hashlib.sha1(json.dumps([cfg["values"], cfg["fillers"]], sort_keys=True, ensure_ascii=False)
                        .encode("utf-8")).hexdigest()


def _ints(values, what: str) -> list:
    from ..errors import Guidance
    out = []
    for v in values or []:
        for part in re.split(r"[,،\s]+", str(v)):
            part = part.strip().translate(_TO_WESTERN)
            if not part:
                continue
            if not (part.isascii() and part.isdecimal()):
                raise Guidance(f"«{part}» مش رقم جملة / {what}: «{part}» is not a sentence number",
                               "Use the numbers `reel takes` lists, e.g. --drop 4,7")
            if int(part) not in out:
                out.append(int(part))
    return out


def apply(paths, drop=(), keep=(), by: str = "editor", ctx=None) -> dict:
    """Drop and keep takes by number in one step (one undo step). Refused, with nothing written: no number given, no
    current listing (`reel takes` first: same transcript, settings and groups), a number that is not a take, the same
    number dropped and kept, every take of a line gone, or no usable edit-decisions.json."""
    from ..errors import Guidance
    drop, keep = _ints(drop, "--drop"), _ints(keep, "--keep")
    if not drop and not keep:
        raise Guidance("مفيش أرقام / no take numbers given", "e.g. `reel takes --drop 4 --keep 5`")
    ws, sha, lang = _words(paths)
    cfg = CP.settings(ctx)
    res = groups(ws, cfg, lang=lang)
    state = _load(paths.p(FILE))
    if not state or state.get("words_sha1") != sha or state.get("settings_sha1") != _cfg_sha(cfg) \
            or state.get("groups") != _shape(res):
        changed = bool(state) and state.get("words_sha1") != sha
        raise Guidance(("التفريغ اتغير بعد ما الجمل اترقمت، فالأرقام ممكن تكون اتغيرت" if changed else
                        "الأرقام دي مش من آخر قائمة") + " / the numbers do not come from a current listing "
                       "(the transcript, the settings or the groups changed)",
                       "Run `reel takes` and choose from the numbers it lists", where=str(paths.p(FILE)))
    by_n = {t["n"]: (g, t) for g in res for t in g["takes"]}
    unknown = [n for n in drop + keep if n not in by_n]
    if unknown:
        raise Guidance(f"الجمل دي مش تكرار لجملة تانية: {', '.join(map(str, unknown))} / not a repeated take: "
                       f"{', '.join(map(str, unknown))}", "Use the take numbers `reel takes` lists")
    both = sorted(set(drop) & set(keep))
    if both:
        raise Guidance(f"نفس الرقم اتشال واتساب: {', '.join(map(str, both))} / dropped and kept at once: "
                       f"{', '.join(map(str, both))}", "Give each number once")
    ef = paths.p(ED)
    try:
        before = ef.read_bytes()
        ed = json.loads(before.decode("utf-8-sig"))
        g0 = ed.setdefault("global", {}) if isinstance(ed, dict) else None
        cw = g0.setdefault("cut_words", []) if isinstance(g0, dict) else None
        if not isinstance(cw, list):
            raise TypeError
    except Exception:  # noqa: BLE001
        raise Guidance("مفيش قرارات مونتاج صالحة لسه / no usable edit decisions yet (01_analysis/edit-decisions.json)",
                       "The story editor writes them first, then choose the takes", where=str(ef)) from None

    def words_of(n):
        return set(by_n[n][1]["word_ids"])

    def is_tk_of(c, n):
        return isinstance(c, dict) and str(c.get("reason", "")).startswith("TK-") \
            and set(c.get("word_ids") or []) == words_of(n)
    cut_before = {w for c in cw if isinstance(c, dict) for w in (c.get("word_ids") or [])}
    # keep: remove this lane's take entries for exactly that take's words
    new = [c for c in cw if not any(is_tk_of(c, n) for n in keep)]
    cut_now = {w for c in new if isinstance(c, dict) for w in (c.get("word_ids") or [])}
    # a kept take that is still cut by another entry (a cut proposal, the editor's own cut) is said plainly
    blocked = [n for n in keep if words_of(n) & cut_now]
    best_of = dict(zip(map(tuple, state.get("groups") or []), state.get("best") or []))
    clean = CP.clean_words(ws)
    pos = {w["id"]: k for k, w in enumerate(clean)}
    pad = cfg["values"]["pad_ms"]
    already = []
    for n in drop:
        g, t = by_n[n]
        if words_of(n) <= cut_now:                       # cut already (this lane, a cut proposal, the editor)
            already.append(n)
            continue
        a, b = pos[t["word_ids"][0]], pos[t["word_ids"][-1]]
        start = max(clean[a]["start_ms"] - pad, clean[a - 1]["end_ms"] if a > 0 else 0)
        end = max(clean[b]["end_ms"], clean[b + 1]["start_ms"] - pad if b + 1 < len(clean) else clean[b]["end_ms"])
        best = best_of.get(tuple(x["n"] for x in g["takes"]), g["best"])      # the best the editor was shown
        why = f"best take: {best}" if best is not None else "no best proposed: the takes differ in meaning"
        new.append({"word_ids": list(t["word_ids"]), "range_ms": [int(start), int(end)],
                    "reason": f"TK-{n} take dropped ({why})", "by": by})
        cut_now |= words_of(n)
    for g in res:                  # a line never disappears whole by this step, whoever cut its other takes
        nums = [t["n"] for t in g["takes"]]
        if not set(nums) & set(drop) or all(words_of(n) <= cut_before for n in nums):
            continue                                     # not touched now, or already gone before this step
        if all(words_of(n) <= cut_now for n in nums):
            raise Guidance(f"كده كل نسخ الجملة {' و '.join(_ar(n) for n in nums)} هتتشال والجملة هتختفي / every "
                           f"take of {', '.join(map(str, nums))} would be cut and the line would be gone",
                           "Keep one of them" + (f" (the proposed best is {g['best']})" if g["best"] is not None
                                                 else " (they differ in meaning: listen to them first)"))
    note = ({"blocked_by_other_cuts": blocked,
             "note": f"الجمل {'، '.join(_ar(n) for n in blocked)} لسه متشالة بقص تاني (اقتراح قص أو قص المونتير)، "
                     "شيله من قائمة القص لو عايزها ترجع / still cut by another entry (a cut proposal or the "
                     "editor's own cut): remove that entry to bring the take back"} if blocked else {})
    if new == cw:
        return {"changed": False, "dropped": drop, "kept": keep, "already": already, "next": "nothing changed",
                **note}
    g0["cut_words"] = new
    data = (json.dumps(ed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    hist = _load(paths.p(HISTORY))
    if hist is None:
        raise Guidance("سجل الرجوع (takes-history.json) بايظ، فمش هعمل خطوة جديدة عليه / the undo history "
                       "(takes-history.json) is damaged, so no new step is written on top of it",
                       "Move it aside (the editor can keep it), then run the command again",
                       where=str(paths.p(HISTORY)))
    steps = list(hist.get("steps") or [])
    steps.append({"before": base64.b64encode(before).decode("ascii"), "after_sha1": hashlib.sha1(data).hexdigest()})
    _write_atomic(ef, data)                            # the plan first: a lost history step never blocks an undo
    _save(paths.p(HISTORY), {"schema": 1, "steps": steps})
    return {"changed": True, "dropped": [n for n in drop if n not in already], "already": already, "kept": keep,
            "next": "`reel plan`, then the editor approves the plan again (nothing is cut before that); "
                    "`reel takes --undo` goes back one step"}


def undo(paths) -> dict:
    """Restore edit-decisions.json exactly as it was before the last --drop/--keep, unless the plan changed after
    that step (then nothing is overwritten)."""
    from ..errors import Guidance
    hist = _load(paths.p(HISTORY))
    if hist is None:
        raise Guidance("سجل الرجوع (takes-history.json) بايظ / the undo history (takes-history.json) is damaged",
                       "Undo the takes by hand in edit-decisions.json (entries whose reason starts with TK-)",
                       where=str(paths.p(HISTORY)))
    steps = list(hist.get("steps") or [])
    if not steps:
        raise Guidance("مفيش خطوة ترجعها / nothing to undo", "Takes were not changed with `reel takes` yet",
                       where=str(paths.p(HISTORY)))
    last = steps[-1]
    ef = paths.p(ED)
    try:
        current = ef.read_bytes()
        data = base64.b64decode(last["before"], validate=True)
    except Exception:  # noqa: BLE001
        raise Guidance("مش قادر أقرا آخر خطوة / the last step cannot be read",
                       "Undo the takes by hand in edit-decisions.json (entries whose reason starts with TK-)",
                       where=str(paths.p(HISTORY))) from None
    if hashlib.sha1(current).hexdigest() != last.get("after_sha1"):
        raise Guidance("الخطة اتغيرت بعد آخر خطوة، فمش هرجع فوق التغييرات دي / the plan changed after the last takes "
                       "step, so undo would overwrite those changes",
                       "Change the takes again with `reel takes --drop/--keep` instead", where=str(ef))
    _write_atomic(ef, data)
    steps.pop()
    _save(paths.p(HISTORY), {"schema": 1, "steps": steps})
    return {"undone": True, "steps_left": len(steps)}
