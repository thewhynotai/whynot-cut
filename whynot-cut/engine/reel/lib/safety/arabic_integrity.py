# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""K-T5 (Phase 4 Task 65): Arabic integrity QC.

Arabic letters join, so animating them one by one breaks the word. These checks keep every on-screen Arabic text
whole and readable:
- per_letter: kinetic text with Arabic (and a Latin run inside an Arabic line) animates by whole words, lines or items,
  never by character (any unit naming a character, letter, glyph or typewriter is refused with the scene id);
- split_word: a word is never cut across lines or animation units (the element's lines and tokens, and the script's
  own words for that scene) and never across two captions (the caption files and the plan's captions, against the
  transcript);
- readback_unit: the After Effects read-back reports each text animator's unit (`animators[].based_on`, a field the
  AE library adds); a character-based unit on a layer with Arabic fails; a font After Effects substituted on an Arabic
  layer is a broken fallback;
- text hygiene: pasted presentation forms («ﺍﻟﻀﻐﻂ»: shaping, search and captions break; the verse brackets «﴾ ﴿» and the
  single-character words «ﷺ ﷲ ﷽» are fine), a direction override that reverses a run (an error; isolates and embeddings
  are a warning), a zero-width joiner or non-joiner inside an Arabic word (a warning), a font without Arabic, and vowel
  or Quranic marks lost on the way from the script to the plan.
Today's plan reveals by word, line or item and the AE build makes one layer per word, so the unit checks guard the
future; the text checks matter now. Eastern Arabic digits are fine (their drawing order is the renderer's job: the
hb_text fix sent with K-T5). Nothing here writes a file; a missing input means nothing to check, said plainly.
In `reel motion-qc` the line appears only behind its switch (switches.ARABIC_QC_IN_MOTION_QC, off until the Gate 4
tag) and only when there is a finding."""
from __future__ import annotations

import json
import re
import unicodedata

ARABIC = re.compile("[؀-ۿݐ-ݿࢠ-ࣿ]")
LETTER = re.compile("[ء-يٮ-ۓۺ-ۿ]")
# letters that never join to the next one: a zero-width non-joiner after them changes nothing
NON_JOINING = set("اآأإٱدذرزوؤةىءژۀ")
MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ]")
# presentation forms pasted from a PDF; the ornate verse brackets (FD3E-FD3F) and the single-character words
# (FDF0-FDFD: ﷲ ﷺ ﷽ …) are standard writing and stay allowed
PRESENTATION = re.compile("[ﭐ-ﴽ﵀-﷯ﹰ-ﻼ]")
OVERRIDE = re.compile("[‭‮]")                       # LRO / RLO: they reverse a run
EMBED_ISOLATE = re.compile("[‪-‬⁦-⁩]")    # embeddings and isolates: legitimate, but worth a look
ZERO_WIDTH = "‌‍"
UNIT_WORDS = ("char", "letter", "glyph", "typewriter")
AE_BASED_ON = {1: "characters", 2: "characters", 3: "words", 4: "lines"}


def _f(rule, ar, en, level="error", **where) -> dict:
    return {"rule": rule, "level": level, "ar": ar, "en": en, **where}


def is_per_letter(unit) -> bool:
    """A unit that names a character, a letter, a glyph or a typewriter, however it is written ("by_char",
    "Characters Excluding Spaces", "per-letter")."""
    u = str(unit or "").strip().lower().replace(" ", "_").replace("-", "_")
    return any(w in u for w in UNIT_WORDS)


# --- text --------------------------------------------------------------------------------------------------------------
def check_text(text, where="") -> list:
    """Hygiene of one on-screen text with Arabic: presentation forms, direction controls, zero-width (non-)joiners
    inside a word."""
    t = str(text or "")
    out = []
    if not ARABIC.search(t) and not PRESENTATION.search(t):
        return out
    if PRESENTATION.search(t):
        out.append(_f("presentation_forms",
                      f"{where}: النص فيه حروف «أشكال عرض» منسوخة (زي ﺍﻟﻀﻐﻂ) بدل الحروف العادية؛ الكلمة مش هتتشكل صح "
                      "ومش هتتلاقى في البحث: اكتبها تاني بحروف عادية",
                      f"{where}: the text holds pasted Arabic presentation forms instead of normal letters (shaping, "
                      "search and captions break): retype it", where=where))
    if OVERRIDE.search(t):
        out.append(_f("bidi_override",
                      f"{where}: النص فيه علامة اتجاه مخفية بتعكس ترتيب الكلام: امسحها",
                      f"{where}: the text holds a hidden direction override that reverses its order: remove it",
                      where=where))
    elif EMBED_ISOLATE.search(t):
        out.append(_f("bidi_isolate",
                      f"{where}: النص فيه علامة اتجاه مخفية (عزل أو تضمين)؛ غالبًا سليمة، بس اتأكد إن الترتيب ظاهر صح",
                      f"{where}: the text holds a hidden direction isolate or embedding; usually fine, check the order "
                      "on screen", level="warning", where=where))
    for k, ch in enumerate(t):
        if ch in ZERO_WIDTH and 0 < k < len(t) - 1 and LETTER.match(t[k - 1]) and LETTER.match(t[k + 1]) \
                and not (ch == "‌" and t[k - 1] in NON_JOINING):
            out.append(_f("zero_width_joiner",
                          f"{where}: فيه فاصل/واصل خفي (ZWNJ/ZWJ) جوه كلمة، والحروف مش هتتوصل زي العادي: اتأكد إنه مقصود",
                          f"{where}: a zero-width (non-)joiner inside a word changes how its letters join: check it "
                          "is intended", level="warning", where=where))
            break
    return out


def _words(s: str) -> list:
    return unicodedata.normalize("NFC", str(s or "")).replace("\r", " ").replace("\n", " ").split()


def _base(s: str) -> str:
    return " ".join(MARKS.sub("", w) for w in _words(s))


def _contiguous(part: list, whole: list) -> bool:
    n = len(part)
    return any(whole[i:i + n] == part for i in range(len(whole) - n + 1))


# --- motion plan -------------------------------------------------------------------------------------------------------
def _script_texts(script) -> dict:
    """{scene id: [every text string the script gives that scene]}."""
    out = {}

    def walk(x, acc):
        if isinstance(x, str):
            acc.append(x)
        elif isinstance(x, list):
            for y in x:
                walk(y, acc)
        elif isinstance(x, dict):
            for k, y in x.items():
                if k not in ("id", "type", "beat", "at", "captions", "recipe_note", "sfx", "reveal"):
                    walk(y, acc)
    for sc in (script or {}).get("scenes") or [] if isinstance(script, dict) else []:
        if isinstance(sc, dict) and sc.get("id"):
            acc = []
            walk(sc, acc)
            out[sc["id"]] = acc
    return out


def _font_has_arabic(ps: str):
    """True / False from the installed font index; None when the font is not found (nothing said: G10)."""
    try:
        from .. import fonts
        face = fonts.find(ps)
        return None if not face else bool(face.get("arabic"))
    except Exception:  # noqa: BLE001
        return None


def _split_against_script(elem_words: list, sources: list) -> bool:
    """The element's words are a piece of a script text only when its words are cut differently (a word split)."""
    if not elem_words:
        return False
    ew = [MARKS.sub("", w) for w in elem_words]
    srcs = [[MARKS.sub("", w) for w in _words(s)] for s in sources]
    if any(_contiguous(ew, sw) for sw in srcs):
        return False                     # the element's words are the script's words, whole
    joined = "".join(ew)
    for sw in srcs:                      # a run of whole script words, the same letters, cut at other places
        for i in range(len(sw)):
            acc = ""
            for j in range(i, len(sw)):
                acc += sw[j]
                if acc == joined:
                    return sw[i:j + 1] != ew
                if len(acc) >= len(joined):
                    break
    return False


def check_motion_plan(plan, script=None, font_has_arabic=None) -> list:
    """Findings for every text element of the motion plan (scenes[].elements[] with kind "text")."""
    fha = font_has_arabic or _font_has_arabic
    texts = _script_texts(script)
    out = []
    for sc in (plan or {}).get("scenes") or [] if isinstance(plan, dict) else []:
        if not isinstance(sc, dict):
            continue
        sid = str(sc.get("id") or "?")
        for e in sc.get("elements") or []:
            if not isinstance(e, dict) or e.get("kind") != "text":
                continue
            name = str(e.get("name") or "?")
            lines = [str(x) for x in (e.get("lines") or [])]
            text = str(e.get("text") or "\r".join(lines))
            where = f"{sid}/{name}"
            arabic = bool(ARABIC.search(text))
            unit = e.get("reveal") or e.get("unit")
            if arabic and is_per_letter(unit):
                out.append(_f("per_letter",
                              f"المشهد {sid}: النص العربي «{text[:40]}» متحرك حرف حرف ({unit})؛ الحروف العربي بتتوصل، "
                              "فلازم الحركة تكون بالكلمة أو بالسطر",
                              f"scene {sid}: the Arabic text is animated letter by letter ({unit}); Arabic letters "
                              "join, so it must animate by word or line", scene=sid, element=name))
            toks = [str(t.get("text")) for t in (e.get("tokens") or []) if isinstance(t, dict) and t.get("text")]
            line_words = _words(" ".join(lines)) if lines else _words(text)
            split = bool(toks) and line_words != [w for t in toks for w in _words(t)]
            split = split or _split_against_script(line_words, texts.get(sid, []))
            if split:
                out.append(_f("split_word",
                              f"المشهد {sid}: كلمة اتقسمت بين سطرين أو بين جزأين من الحركة في «{text[:40]}»؛ الكلمة "
                              "لازم تفضل كاملة",
                              f"scene {sid}: a word is cut across lines or animation units in this text; a word "
                              "stays whole", scene=sid, element=name))
            out += [dict(f, scene=sid, element=name) for f in check_text(text, f"المشهد {sid}")]
            if arabic and e.get("font_ps") and fha(str(e["font_ps"])) is False:
                out.append(_f("font_no_arabic",
                              f"المشهد {sid}: الخط {e['font_ps']} مافيهوش حروف عربي، فالنص هيظهر بخط بديل أو مربعات",
                              f"scene {sid}: the font {e['font_ps']} has no Arabic, so the text falls back or shows "
                              "boxes", scene=sid, element=name))
            marked = [s for s in texts.get(sid, []) if MARKS.search(s)]
            if marked and not any(text.replace("\r", " ") in s or text in s for s in texts.get(sid, [])):
                if any(_base(text) and _base(text) in _base(s) for s in marked):
                    out.append(_f("marks_lost",
                                  f"المشهد {sid}: التشكيل أو علامات المصحف اللي في النص الأصلي اتشالت أو اتغيرت؛ النص "
                                  "لازم يفضل زي ما هو حرفيًا",
                                  f"scene {sid}: the vowel or Quranic marks of the script's text were lost or changed; "
                                  "the text must stay verbatim", scene=sid, element=name))
    return out


# --- captions ----------------------------------------------------------------------------------------------------------
def check_cues(cues, words) -> list:
    """Every caption cue shows whole words: with word ids, exactly its words and no word in two cues; without ids
    (an SRT, the plan's captions), the cues' words read in order must be the transcript's words, never a word cut at
    a cue or line boundary."""
    by_id = {w.get("id"): str(w.get("word") or "").strip() for w in words or [] if isinstance(w, dict)}
    out, seen = [], {}
    plain = []
    for k, c in enumerate(cues or [], 1):
        if not isinstance(c, dict):
            continue
        ids = [i for i in c.get("word_ids") or [] if i in by_id]
        if not ids:
            plain.append((k, _words(c.get("text"))))
            continue
        twice = [i for i in ids if i in seen]
        for i in ids:
            seen.setdefault(i, k)
        if twice or _words(c.get("text")) != [w for i in ids for w in _words(by_id[i])]:
            out.append(_f("split_word", f"الكابشن {k}: كلمة اتقسمت بين كابشنين أو بين سطرين",
                          f"caption {k}: a word is cut across two captions or two lines", cue=k))
    if plain:
        vocab = {MARKS.sub("", w) for i in by_id for w in _words(by_id[i])}
        flat = [(k, MARKS.sub("", w)) for k, ws in plain for w in ws]
        for j in range(len(flat) - 1):
            (k1, a), (k2, b) = flat[j], flat[j + 1]
            if a not in vocab and b not in vocab and (a + b) in vocab:
                # a warning: without word ids this is a reading of the text (an editor's spacing fix, «5 mg» for the
                # transcript's «5mg», looks the same)
                out.append(_f("split_word", f"الكابشن {k1}: الكلمة «{a + b}» شكلها اتقسمت بين سطرين أو كابشنين",
                              f"caption {k1}: the word «{a + b}» looks cut across two lines or captions",
                              level="warning", cue=k1))
    return out


# --- After Effects read-back -------------------------------------------------------------------------------------------
def _unit(v) -> str | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return AE_BASED_ON.get(int(v))
    if is_per_letter(v):
        return "characters"
    s = str(v or "").strip().lower()
    return s if s in ("words", "lines") else None


def readback_units(readback) -> dict:
    """{text layer name: [unit of each animator]}: "characters", "words" or "lines". No `animators` field (the AE
    library does not report it yet): an empty list, nothing judged."""
    out = {}
    for sc in (readback or {}).get("scenes") or [] if isinstance(readback, dict) else []:
        for ly in (sc.get("layers") or []) if isinstance(sc, dict) else []:
            if isinstance(ly, dict) and ly.get("kind") == "text":
                out[str(ly.get("name"))] = [u for a in (ly.get("animators") or []) if isinstance(a, dict)
                                            for u in [_unit(a.get("based_on"))] if u]
    return out


def check_readback(readback) -> list:
    """QC fails on a character-based text animator, or a font After Effects substituted, for any layer with Arabic."""
    out = []
    units = readback_units(readback)
    for sc in (readback or {}).get("scenes") or [] if isinstance(readback, dict) else []:
        for ly in (sc.get("layers") or []) if isinstance(sc, dict) else []:
            if not isinstance(ly, dict) or ly.get("kind") != "text" or not ARABIC.search(str(ly.get("text") or "")):
                continue
            name = str(ly.get("name"))
            if "characters" in units.get(name, []):
                out.append(_f("readback_unit",
                              f"المشهد {sc.get('id')}: طبقة {name} في After Effects متحركة بالحرف؛ لازم بالكلمة أو بالسطر",
                              f"scene {sc.get('id')}: layer {name} in After Effects animates by character; it must be "
                              "by word or line", scene=sc.get("id"), layer=name))
            if ly.get("substitute") is True:
                out.append(_f("font_no_arabic",
                              f"المشهد {sc.get('id')}: After Effects بدّل خط طبقة {name} بخط تاني، والعربي ممكن يظهر غلط",
                              f"scene {sc.get('id')}: After Effects substituted the font of layer {name}; the Arabic "
                              "may show wrong", scene=sc.get("id"), layer=name))
    return out


# --- a project ---------------------------------------------------------------------------------------------------------
def _read(path):
    try:
        return True, json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return False, None
    except Exception:  # noqa: BLE001
        return True, None


def run(paths) -> dict:
    """{"ok", "findings", "notes"} over the motion plan (with its script and captions), the caption files and the AE
    read-back of this item. Reads only. A damaged file is a warning (its own step reports it)."""
    findings, notes = [], []
    found, plan = _read(paths.p("01_analysis/motion-plan.json"))
    wj = _read(paths.p("02_transcription/words.json"))[1]
    words = wj.get("words") if isinstance(wj, dict) and isinstance(wj.get("words"), list) else None
    if found and not isinstance(plan, dict):
        findings.append(_f("unreadable", "خطة الموشن (motion-plan.json) بايظة ومش مقروءة",
                           "the motion plan (motion-plan.json) is damaged and cannot be read", level="warning"))
    elif found:
        _, script = _read(paths.p("01_analysis/motion-script.json"))
        findings += check_motion_plan(plan, script if isinstance(script, dict) else None)
        cues = (plan.get("captions") or {}).get("cues") if isinstance(plan.get("captions"), dict) else None
        if isinstance(cues, list) and words:
            findings += check_cues([c for c in cues if isinstance(c, dict)], words)
    if words:
        from .. import srt
        for name in ("subtitles.srt", "captions-short.srt"):
            f = paths.p(f"02_transcription/{name}")
            if f.is_file():
                try:
                    findings += check_cues(srt.read_srt(f), words)
                except Exception:  # noqa: BLE001  (a damaged SRT is the captions step's to report)
                    pass
    try:
        from ..motion_build import RESULT
    except Exception:  # noqa: BLE001  (a stripped runtime: the file name motion_build uses)
        RESULT = "04_after_effects/motion-build-result.json"
    _, build = _read(paths.p(RESULT))
    if isinstance(build, dict) and isinstance(build.get("readback"), dict):
        findings += check_readback(build["readback"])
    if not found and not findings:
        notes.append("مفيش خطة موشن للفيديو ده، فمفيش نص متحرك يتراجع / no motion plan for this item: no animated "
                     "text to check")
    return {"ok": not any(f["level"] == "error" for f in findings), "findings": findings, "notes": notes}
