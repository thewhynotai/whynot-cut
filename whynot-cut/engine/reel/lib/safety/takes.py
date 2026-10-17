# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""K-T7 (Phase 4 Task 67): repeated takes, numbered keep/drop/undo.

Built on Task 25 (cut_proposals: the shared normaliser, the take similarity, the starting values). `reel takes` numbers
the sentences of a clip (1..N, from the words alone, so the same transcript always gives the same numbers), groups the
sentences said more than once («٤ و ٥ نفس الجملة: الأفضل ٥ — كاملة ومن غير تلعثم») and proposes the better take from
measured features only: closed by the transcript or not, covering the line, restarts and hesitation sounds inside,
clipping and level (only when audio is given), mean word confidence; a tie keeps the later take. When the takes differ
in a number, a dose, a negation or a content word, the line says so («⚠ النسختين مختلفين في: …»): the editor decides.

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

from .. import cut_proposals as CP
from .numbers import fold, values_in

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
NEGATIONS = {"مش", "لا", "ما", "مفيش", "ممنوع", "بلاش", "لم", "لن", "ليس", "بدون", "no", "not", "never", "dont",
             "don't", "without"}


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
                        "punct": bool(_PUNCT.search(cur[-1]["word"])), "speaker": cur[0].get("speaker"),
                        "probs": [x.get("probability") for x in cur]})
            cur = []
    return out


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
    """What the takes do not share where they overlap: numbers and doses (by value), negations, content words."""
    vals = [values_in(t["text"]) for t in takes]
    negs = [{fold(w) for w in t["text"].split()} & NEGATIONS for t in takes]
    n = min(len(t["toks"]) for t in takes)
    shown = {}                                       # compared without a clitic, shown as said («للسكر»)
    words = []
    for t in takes:
        s = set()
        for w in _content_words(t["toks"][:n + 1], F):
            if not _is_number(w):
                shown.setdefault(_bare(w), w)
                s.add(_bare(w))
        words.append(s)
    common = set.intersection(*words) if words else set()
    out = {}
    if len({frozenset(v) for v in vals}) > 1:
        out["numbers"] = sorted({str(x) for v in vals for x in v})
    if len({frozenset(x) for x in negs}) > 1:
        out["negation"] = True
    differ = sorted(shown[w] for w in {w for s in words for w in s} - common)
    if differ and len(differ) <= 4:
        out["words"] = differ
    return out


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


def groups(words, cfg=None, samples=None, sr=0, lang: str = "ar") -> list:
    """Take groups: [{"takes": [sentence + features], "best": n, "differ": {...}, "line_ar", "line_en"}], in time
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
        best = max(range(len(takes)), key=lambda k: keys[k])
        tie = sum(1 for k in keys if k[:-1] == keys[best][:-1]) > 1
        nums = [t["n"] for t in takes]
        why_ar, why_en = _why(takes[best]["features"], tie)
        differ = _differences([ss[i] for i in g], F)
        warn_ar, warn_en = "", ""
        if differ:
            bits_ar, bits_en = [], []
            if differ.get("numbers"):
                bits_ar.append("الأرقام/الجرعة (" + "، ".join(differ["numbers"]) + ")")
                bits_en.append("numbers/dose (" + ", ".join(differ["numbers"]) + ")")
            if differ.get("negation"):
                bits_ar.append("النفي")
                bits_en.append("a negation")
            if differ.get("words"):
                bits_ar.append("الكلام (" + "، ".join(differ["words"]) + ")")
                bits_en.append("words (" + ", ".join(differ["words"]) + ")")
            warn_ar = " — ⚠ النسخ مختلفة في: " + "؛ ".join(bits_ar) + "، اسمعهم قبل ما تختار"
            warn_en = " — ⚠ the takes differ in: " + "; ".join(bits_en) + "; listen before choosing"
        out.append({"takes": takes, "best": nums[best], "differ": differ,
                    "line_ar": f"{' و '.join(_ar(n) for n in nums)} نفس الجملة: الأفضل {_ar(nums[best])} — {why_ar}"
                               + warn_ar,
                    "line_en": (f"{', '.join(map(str, nums[:-1]))} and {nums[-1]} are the same sentence: best "
                                f"{nums[best]} — {why_en}" + warn_en)})
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
        new.append({"word_ids": list(t["word_ids"]), "range_ms": [int(start), int(end)],
                    "reason": f"TK-{n} take dropped (best take: {best})", "by": by})
        cut_now |= words_of(n)
    for g in res:                  # a line never disappears whole by this step, whoever cut its other takes
        nums = [t["n"] for t in g["takes"]]
        if not set(nums) & set(drop) or all(words_of(n) <= cut_before for n in nums):
            continue                                     # not touched now, or already gone before this step
        if all(words_of(n) <= cut_now for n in nums):
            raise Guidance(f"كده كل نسخ الجملة {' و '.join(_ar(n) for n in nums)} هتتشال والجملة هتختفي / every "
                           f"take of {', '.join(map(str, nums))} would be cut and the line would be gone",
                           f"Keep one of them (the proposed best is {g['best']})")
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
