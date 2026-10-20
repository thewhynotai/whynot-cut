# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The reel's ending (3.0 Task 29, R-4.7): up to three parts, only those switched on, always in this order: the
comment call-to-action card, the follow card (the full handle), then the recorded sign-off.

Profile (config/defaults/profile.json <- client reel-profile): `endings: {cta: {on, keyword_ar, keyword_en}, follow: {on,
handle, logo}, sign_off: {on, phrase}}`; this video's edit-decisions `global.endings` may switch a part off (or on).
A card is an ending part when its graphic says `"ending": "cta" | "follow"`, or when it uses the `cta` template.

`sign_off_span` is the ONE sign-off detector (the cut proposals use the same rule: until their call to it lands, a parity
test pins both to the same answer): the editor's `global.sign_off_at` wins; else the normalised profile phrase, the
last time it is said inside the last 20 s; else, when a sign-off is expected, the last 8 s, with one line to the
editor. The span runs to the end of the media and is protected: nothing is placed over it, no caption-hide window
starts inside it, no music ducking change inside it (a warning), and the cut proposals never cut it.

This module checks and never moves anything: a refusal names the exact fix (the free slot and the length needed).
Pure: no file reads or writes (`plan_check` takes what the plan already read).
"""
from __future__ import annotations

ROLES = ("cta", "follow")
# starting values of ours (R-4.7 / questions Q12): measured on our reels later, the basis says so
DEFAULTS = {"search_s": 20, "fallback_s": 8, "cta_min_ms": 1200, "follow_min_ms": 1500, "label_floor_px": 32,
            "card_start_px": 60, "card_box_px": 900}
BASIS = "R-4.7 starting value (Task 29 Q12), not measured"
OFF_PART = ("الجزء ده مقفول في البروفايل", "this part is switched off in the profile")
HANDLE_LONG = ("الهاندل أطول من المساحة: اختصر الاسم أو شيل كارت المتابعة",
               "the handle does not fit even at the smallest label size: shorten it or switch the follow card off")


def _on(v) -> bool:
    return v is True


def _text(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def config(profile_endings, global_endings=None) -> dict:
    """The merged ending parts: the profile's `endings`, then this video's `global.endings` (any key it sets wins)."""
    prof = profile_endings if isinstance(profile_endings, dict) else {}
    over = global_endings if isinstance(global_endings, dict) else {}

    def part(name):
        p = dict(prof.get(name)) if isinstance(prof.get(name), dict) else {}
        if isinstance(over.get(name), dict):
            p.update(over[name])
        return p
    c, f, s = part("cta"), part("follow"), part("sign_off")
    return {"cta": {"on": _on(c.get("on")), "keyword_ar": _text(c.get("keyword_ar")), "keyword_en": _text(c.get("keyword_en"))},
            "follow": {"on": _on(f.get("on")), "handle": _text(f.get("handle")), "logo": _text(f.get("logo"))},
            "sign_off": {"on": _on(s.get("on")), "phrase": s.get("phrase") if isinstance(s.get("phrase"), str) else None}}


def cta_keyword(cfg: dict, lang: str) -> tuple:
    """(keyword in the reel's language, None) | (None, None) when the CTA is off | (None, note) when it is on but has no
    keyword in that language (the part is then treated as off)."""
    cta = (cfg or {}).get("cta") or {}
    if not cta.get("on"):
        return None, None
    en = str(lang or "").lower().startswith("en")
    kw = cta.get("keyword_en" if en else "keyword_ar")
    if kw:
        return kw, None
    which = "English" if en else "Arabic"
    return None, {"ar": f"كلمة الـ CTA مش مكتوبة {'بالإنجليزي' if en else 'بالعربي'} في البروفايل، فجزء الـ CTA مقفول في "
                        "الفيديو ده",
                  "en": f"the CTA keyword has no {which} wording in the profile: the CTA part is treated as off"}


def _tokens(words: list) -> tuple:
    from .cut_proposals import clean_words, norm_word
    ws = clean_words(words)
    return ws, [norm_word(w["word"]) for w in ws]


def sign_off_span(words: list, cfg: dict, marker_ms, media_end_ms, values: dict | None = None) -> dict | None:
    """{start_ms, end_ms, source: marker|phrase|fallback, note: {ar, en} | None} on the source clock, or None when
    nothing is protected (no marker and the sign-off is off)."""
    from .cut_proposals import norm_word
    v = dict(DEFAULTS, **(values or {}))
    ws, toks = _tokens(words)
    num = isinstance(media_end_ms, (int, float)) and not isinstance(media_end_ms, bool)
    end = media_end_ms if num else (ws[-1]["end_ms"] if ws else 0)
    if isinstance(marker_ms, (int, float)) and not isinstance(marker_ms, bool):
        return {"start_ms": marker_ms, "end_ms": end, "source": "marker", "note": None}
    so = (cfg or {}).get("sign_off") or {}
    if not so.get("on"):
        return None
    phrase = str(so.get("phrase") or "").strip()
    q = [norm_word(x) for x in phrase.split() if norm_word(x)]
    hit = None
    for i in range(len(toks) - len(q) + 1):
        if q and toks[i:i + len(q)] == q and ws[i]["start_ms"] >= end - v["search_s"] * 1000:
            hit = ws[i]["start_ms"]
    if hit is not None:
        return {"start_ms": hit, "end_ms": end, "source": "phrase", "note": None}
    said = f"«{phrase}»" if phrase else "(من غير نص في الملف / no phrase in the profile)"
    return {"start_ms": max(0, end - v["fallback_s"] * 1000), "end_ms": end, "source": "fallback",
            "note": {"ar": f"جملة الختام {said} ماتلقتش في آخر {v['search_s']:g} ثانية، فآخر {v['fallback_s']:g} ثواني "
                           "محمية من القص.",
                     "en": f"The sign-off {said} was not found in the last {v['search_s']:g} s, so the last "
                           f"{v['fallback_s']:g} s are protected from cuts."}}


def card_role(event: dict) -> str | None:
    """"cta" | "follow" | None: the ending part a graphic is."""
    p = event.get("params") if isinstance(event.get("params"), dict) else {}
    r = p.get("ending")
    if r in ROLES:
        return r
    return "cta" if event.get("template") == "cta" else None


def ending_start(span: dict | None, events: list) -> float | None:
    """Where the ending begins: the earliest of the first ending card's start and the protected span's start."""
    pts = [e["start_ms"] for e in events or [] if card_role(e)]
    if span:
        pts.append(span["start_ms"])
    return min(pts) if pts else None


def fmt(ms) -> str:
    """Sequence ms -> "MM:SS.cc" (the editor's timeline reading)."""
    cs = int(round(float(ms) / 10))
    m, cs = divmod(cs, 6000)
    return f"{m:02d}:{cs // 100:02d}.{cs % 100:02d}"


def _sec(ms) -> str:
    return f"{ms / 1000:.1f}".rstrip("0").rstrip(".")


def fit_handle(handle: str, measure, box_w: float, start_px: float, floor_px: float) -> dict:
    """Fit-or-fail for the follow card's handle: the full text, shrunk 1 px at a time from `start_px` down to
    `floor_px` until `measure(text, px)` <= box_w; never truncated or ellipsised. {ok, size_px, width_px, floor_px,
    text}; ok False when it does not fit even at the floor."""
    px = float(start_px)
    w = measure(handle, px)
    while w > box_w and px - 1 >= floor_px - 1e-9:
        px -= 1
        w = measure(handle, px)
    return {"ok": w <= box_w, "size_px": int(px) if px == int(px) else px, "width_px": round(float(w), 1),
            "floor_px": floor_px, "text": handle}


def looks_type_measure(typography: dict | None, role: str = "headline"):
    """measure(text, px) with the client's font chain for `role` (looks_type), the measurement R-6.1 refines later."""
    from .looks_type import Typesetter, font_chain
    chain = font_chain(typography or {}, role)
    if not chain["arabic"] and not chain["latin"]:
        raise LookupError("no font for the label on this computer")

    def measure(text, px):
        line = Typesetter(chain, px).line([text])
        if line["missing"]:                       # a glyph no font has: its width is unknown, never "it fits"
            raise LookupError(f"no font draws {', '.join(line['missing'][:4])}")
        return line["w"]
    return measure


def _both(ar: str, en: str) -> str:
    return f"{ar} — {en}"


def check(events: list, span: dict | None, cfg: dict, *, hidden=(), music_cues=(), values: dict | None = None,
          handle_fit: dict | None = None, lang: str = "ar") -> tuple:
    """(errors, warnings) of the ending on the SEQUENCE clock. `events`: the plan's graphic events (start_ms/end_ms on
    the sequence clock); `span`: the protected sign-off span on the same clock (or None); `hidden`: the caption-hide
    windows; `music_cues`: music cue points {label, at_ms}; `handle_fit`: fit_handle's answer for the follow card."""
    v = dict(DEFAULTS, **(values or {}))
    errors, warnings = [], []
    cfg = cfg or config({}, {})
    cta_kw, _ = cta_keyword(cfg, lang)
    on = {"cta": bool(cfg["cta"]["on"] and cta_kw), "follow": bool(cfg["follow"]["on"])}
    s0 = span["start_ms"] if span else None
    # nothing over the sign-off
    if span:
        for e in sorted(events or [], key=lambda x: (x["start_ms"], x["event_id"])):
            if e["start_ms"] < span["end_ms"] and span["start_ms"] < e["end_ms"]:
                errors.append(_both(f"{e['event_id']} ({e['template']}) فوق جملة الختام المحمية: حرّك {e['event_id']} قبل "
                                    f"{fmt(s0)} أو قصّره",
                                    f"{e['event_id']} ({e['template']}) covers the protected sign-off: move "
                                    f"{e['event_id']} before {fmt(s0)} or shorten it"))
        for a, b in hidden or ():
            if span["start_ms"] <= a < span["end_ms"]:
                errors.append(_both(f"الكابشن بيختفي من {fmt(a)} جوه جملة الختام المحمية: خلّي الاختفاء يبدأ قبل {fmt(s0)}",
                                    f"a caption-hide window starts at {fmt(a)} inside the protected sign-off: start it "
                                    f"before {fmt(s0)}"))
        for c in music_cues or ():
            t = c.get("at_ms")
            if isinstance(t, (int, float)) and span["start_ms"] <= t < span["end_ms"]:
                warnings.append(_both(f"علامة الموسيقى «{c.get('label', '')}» عند {fmt(t)} جوه جملة الختام: سيبناها زي ما هي، "
                                      "بس متغيّرش مستوى الموسيقى تحت الكلام ده",
                                      f"music cue '{c.get('label', '')}' at {fmt(t)} is inside the protected sign-off: "
                                      "kept as authored, but do not change the music level (ducking) there"))
    cards = sorted(((card_role(e), e) for e in events or [] if card_role(e)), key=lambda x: (x[1]["start_ms"], x[1]["event_id"]))
    for role, e in cards:
        if not on[role]:
            warnings.append(_both(f"{e['event_id']}: {OFF_PART[0]} ({'CTA' if role == 'cta' else 'المتابعة'})",
                                  f"{e['event_id']}: {OFF_PART[1]} ({role})"))
    live = [(r, e) for r, e in cards if on[r]]
    # order: every CTA card ends before every follow card starts; every card ends before the sign-off span starts
    for r1, a in live:
        for r2, b in live:
            if r1 == "cta" and r2 == "follow" and a["end_ms"] > b["start_ms"]:
                errors.append(_both(f"الترتيب غلط: {a['event_id']} (CTA) لازم يخلص قبل ما {b['event_id']} (المتابعة) يبدأ "
                                    f"عند {fmt(b['start_ms'])}",
                                    f"wrong order: {a['event_id']} (CTA) must end before {b['event_id']} (follow) starts "
                                    f"at {fmt(b['start_ms'])}"))
    if span:
        for r, e in live:
            if e["start_ms"] >= s0:
                errors.append(_both(f"{e['event_id']} بعد جملة الختام: الكروت قبل الختام دايمًا، حرّكه قبل {fmt(s0)}",
                                    f"{e['event_id']} is after the sign-off: ending cards always come before it, move "
                                    f"it before {fmt(s0)}"))
    # each card long enough; the free slot it may use and the length it needs
    for k, (r, e) in enumerate(live):
        need = v["cta_min_ms"] if r == "cta" else v["follow_min_ms"]
        have = e["end_ms"] - e["start_ms"]
        if have >= need:
            continue
        prev_end = max([x["end_ms"] for _r, x in live[:k]] or [e["start_ms"]])
        nxt = [x["start_ms"] for _r, x in live[k + 1:]] + ([s0] if span else [])
        lo, hi = min(prev_end, e["start_ms"]), (min(nxt) if nxt else e["end_ms"])
        slot = max(0, hi - lo)
        what_ar = "كارت الـ CTA" if r == "cta" else "كارت المتابعة"
        if slot >= need:
            fix_ar = f"طوّله لـ {_sec(need)} ث على الأقل جوه المساحة الفاضية من {fmt(lo)} لـ {fmt(hi)}"
            fix_en = f"make it at least {_sec(need)} s inside the free slot {fmt(lo)}-{fmt(hi)}"
        else:
            other = [x for _r, x in live if x is not e]
            short = f", أو قصّر {other[0]['event_id']} لـ {_sec(max(0, (other[0]['end_ms'] - other[0]['start_ms']) - (need - slot)))} ث" \
                if other else ""
            short_en = f", or shorten {other[0]['event_id']} to " \
                       f"{_sec(max(0, (other[0]['end_ms'] - other[0]['start_ms']) - (need - slot)))} s" if other else ""
            fix_ar = (f"المساحة الفاضية من {fmt(lo)} لـ {fmt(hi)} ({_sec(slot)} ث) أقل من {_sec(need)} ث: اقفل الجزء ده في "
                      f"الفيديو ده (global: endings.{r}.on: false){short}، أو خلّي الريل يخلص متأخر")
            fix_en = (f"the free slot {fmt(lo)}-{fmt(hi)} ({_sec(slot)} s) is shorter than {_sec(need)} s: switch this part "
                      f"off for this video (global: endings.{r}.on: false){short_en}, or end the reel later")
        errors.append(_both(f"{e['event_id']}: {what_ar} {_sec(have)} ث بس، ومحتاج {_sec(need)} ث: {fix_ar}",
                            f"{e['event_id']}: the {r} card is only {_sec(have)} s and needs {_sec(need)} s: {fix_en}"))
    # parts switched on but not placed: the free slot before the sign-off, for the story-editor
    for r in ROLES:
        if on[r] and not any(x == r for x, _e in live):
            where = f" (فيه مكان قبل {fmt(s0)})" if span else ""
            where_en = f" (there is room before {fmt(s0)})" if span else ""
            warnings.append(_both(f"جزء {'الـ CTA' if r == 'cta' else 'المتابعة'} مفعّل في البروفايل ومفيش كارت ليه{where}",
                                  f"the {r} part is on in the profile but no card is placed{where_en}"))
    if on["follow"] and any(x == "follow" for x, _e in live):
        if not cfg["follow"].get("handle"):
            errors.append(_both("كارت المتابعة محتاج الهاندل: اكتبه في البروفايل (endings.follow.handle)",
                                "the follow card needs the handle: set endings.follow.handle in the profile"))
        elif handle_fit is not None and not handle_fit.get("ok"):
            errors.append(_both(HANDLE_LONG[0], HANDLE_LONG[1]))
    return errors, warnings


def plan_check(inp, tm: dict, music: dict | None) -> tuple:
    """The plan step (after the time map): (errors, warnings, info). `inp`: PlanInputs (words, profile, base, dur_ms,
    lang); `tm`: apply_timemap's data (tmap, events on the sequence clock); `music`: build_audio's music block.
    info = {"span": the protected span on the sequence clock | None, "parts": the parts switched on, "source"}."""
    from .common import caption_hide_default
    base = getattr(inp, "base", None) or {}
    profile = getattr(inp, "profile", None) or {}
    cfg = config(profile.get("endings"), base.get("endings"))
    errors, warnings = [], []
    lang = getattr(inp, "lang", None) or "ar"
    _kw, note = cta_keyword(cfg, lang)
    if note:
        warnings.append(_both(note["ar"], note["en"]))
    marker = base.get("sign_off_at")
    marker_ms = None
    if marker not in (None, ""):
        from .plan import _try_ms
        marker_ms = _try_ms(marker)
        if marker_ms is None:
            errors.append(f"global.sign_off_at {marker!r} is not a time (seconds such as 27.4, or a clock such as "
                          "00:00:27.400)")
    span = sign_off_span(getattr(inp, "words", None) or [], cfg, marker_ms, getattr(inp, "dur_ms", None))
    tmap = tm.get("tmap")
    seq = (lambda t: round(tmap.ms(t))) if tmap else (lambda t: int(t))
    sspan = None
    if span:
        if span.get("note"):
            warnings.append(_both(span["note"]["ar"], span["note"]["en"]))
        sspan = dict(span, start_ms=seq(span["start_ms"]), end_ms=seq(span["end_ms"]))
    events = tm.get("events") or []
    hide_t = set(base.get("captions_hidden_during") or caption_hide_default(None))
    hidden = []
    for r in base.get("captions_hidden_ranges") or []:
        if isinstance(r, (list, tuple)) and len(r) == 2:
            from .plan import _try_ms
            a, b = _try_ms(r[0]), _try_ms(r[1])
            if a is not None and b is not None:
                hidden.append((seq(a), seq(b)))
    hidden += [(e["start_ms"], e["end_ms"]) for e in events if e.get("template") in hide_t and not (
        sspan and sspan["start_ms"] <= e["start_ms"] < sspan["end_ms"])]      # a card inside is refused on its own
    fps = getattr(inp, "fps", None) or 24
    cues = []
    for c in (music or {}).get("cue_points") or []:
        if isinstance(c.get("frame"), (int, float)):
            cues.append({"label": c.get("label", ""), "at_ms": c["frame"] * 1000 / fps})
    fit = None
    if cfg["follow"]["on"] and cfg["follow"].get("handle") and any(card_role(e) == "follow" for e in events):
        measure = getattr(inp, "measure_label", None)
        why = "no font chain"
        try:
            if measure is None and getattr(inp, "typography", None) is not None:
                measure = looks_type_measure(inp.typography)
            if measure is not None:
                W = float(getattr(inp, "frame_w", None) or 1080)
                fit = fit_handle(cfg["follow"]["handle"], measure, DEFAULTS["card_box_px"] * W / 1080,
                                 DEFAULTS["card_start_px"] * W / 1080, DEFAULTS["label_floor_px"] * W / 1080)
        except Exception as e:  # noqa: BLE001  no font or no text engine on this computer: say so, never pass silently
            fit, why = None, type(e).__name__
        if fit is None:
            warnings.append(_both("الهاندل ماتقاسش (مفيش خط أو محرك نص على الجهاز ده): اتأكد بعينك إنه ظاهر كله في الكارت",
                                  f"the handle was not measured ({why}): check by eye that it shows in full on the "
                                  "follow card"))
    e2, w2 = check(events, sspan, cfg, hidden=hidden, music_cues=cues, handle_fit=fit, lang=lang)
    parts = [p for p in ("cta", "follow", "sign_off") if cfg[p]["on"]]
    return errors + e2, warnings + w2, {"span": sspan, "parts": parts, "handle_fit": fit}
