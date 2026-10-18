# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""K-T4 (Phase 4 Task 64): the safe-zone check with an exit code.

Built on Task 27 (`lib/safe_zones.py`, the platform profiles and their check): nothing of its data or detection is
redefined here. `reel safezone-check` runs Task 27's check over this item's graphic stills
(03_broll/<category>/<event>.png and their part stills) and caption stills (03_broll/captions/CAP_###_fg.png and the
caption plate CAP_###_bar.png), each element's box being the visible part of its still (alpha above 24, as today's
QC), scaled to the reel's frame, prints the intruding element ids, and exits:

    0  checked, nothing in a platform's UI zone
    1  at least one element intrudes (its id is printed)
    2  could not check: no stills yet, the plan or a box list unreadable, an unknown or damaged platform, stills of
       another shape than the reel, an unreadable still, or the check itself failing — never a silent 0
    (an error of the command line itself, e.g. no --video-id, is the CLI's own exit 1, before the check runs)

The platform is the command's `--platform` (one or more), else the plan's (edit-decisions global.platforms /
platform), else the client's (style.json platforms), else Task 27's default; a 4:5 reel (a 4:5 frame) with none chosen
uses `feed_4x5`. A 4:5 window inside a 9:16 reel is delivered 9:16 and is checked as 9:16. An Arabic transcript also
checks the platform's right-to-left layout. Premiere QC frames carry no element boxes: when the frames step records
them (`08_quality_control/frames/boxes.json`: {"frame": [w, h], "boxes": [{"id", "rect"}]}, Adobe track) they are
checked too. Every element counts as text (P1). `reel qc` treats an intrusion as a hard failure only behind its K1
switch (off until the Gate 4 tag) and only when a platform was chosen, like Task 27's QC lines; with the switch on
and no platform chosen it warns that the safe zones are not enforced. Every result names what it checked (graphic and
caption stills, Premiere frames recorded or not). Reads only."""
from __future__ import annotations

import json

EXIT_OK, EXIT_FOUND, EXIT_ERROR = 0, 1, 2
ALPHA = 24
FULL_SCREEN = {"broll_card", "broll_video", "logo_outro", "flash_transition", "photo_card"}   # as today's qc
DEFAULT_4X5 = "feed_4x5"


class _CannotCheck(Exception):
    """A reason the check could not run (exit 2), in plain words."""


def _read(path):
    """The JSON at path; None when the file is absent; raises _CannotCheck when it exists but cannot be read."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        raise _CannotCheck(f"الملف {path.name} بايظ ومش مقروء / {path.name} cannot be read") from None


def _still_box(png):
    """(rect, size) of the visible part of a still; (None, size) when it is fully transparent; raises when it cannot
    be read."""
    from PIL import Image
    with Image.open(png) as im:
        size = im.size
        if im.mode not in ("RGBA", "LA"):
            im = im.convert("RGBA")
        bb = im.getchannel("A").point(lambda v: 255 if v > ALPHA else 0).getbbox()
    return (list(bb) if bb else None), size


def _reel_frame(paths):
    try:
        from ..common import frame_size
        return tuple(frame_size(paths))
    except Exception:  # noqa: BLE001
        return None


def _scale(rect, src, dst):
    if not dst or tuple(src) == tuple(dst):
        return list(rect)
    if abs(src[0] * dst[1] - src[1] * dst[0]) * 100 > src[0] * dst[1]:
        raise _CannotCheck(f"صورة مقاسها {src[0]}x{src[1]} مش بنفس شكل الفيديو {dst[0]}x{dst[1]} / a still of "
                           f"{src[0]}x{src[1]} is not the reel's shape {dst[0]}x{dst[1]}")
    fx, fy = dst[0] / src[0], dst[1] / src[1]
    import math       # outward: a scaled edge never moves away from a zone (errs toward reporting an intrusion)
    return [math.floor(rect[0] * fx), math.floor(rect[1] * fy), math.ceil(rect[2] * fx), math.ceil(rect[3] * fy)]


def boxes(paths) -> tuple:
    """([{"id", "kind", "rect", "label", "source"}] on the reel's frame, frame (w, h) or None). Raises _CannotCheck
    when the plan, a box list or a still cannot be read, or a still is not the reel's shape."""
    from ..common import still_category
    spec = _read(paths.p("01_analysis/timeline-spec.json"))
    files, missing = [], []
    for e in (spec.get("events") or []) if isinstance(spec, dict) else []:
        if not isinstance(e, dict) or e.get("template") in FULL_SCREEN or not e.get("event_id"):
            continue
        folder = paths.p(f"03_broll/{still_category(str(e.get('template') or ''))}")
        eid = str(e["event_id"])
        own = [f for f in (sorted(folder.glob(f"{eid}*.png")) if folder.is_dir() else [])
               if f.stem == eid or f.stem.startswith(eid + "_")]
        files += [(eid, f, "graphic") for f in own]
        if not own:
            missing.append(eid)
    if spec is None:                                     # no plan: our graphic stills cannot be named
        ours = {still_category(t) for t in ("hook_title", "glass_card", "checklist", "term_callout", "name_card")}
        graphics = [f for d in ours for f in paths.p(f"03_broll/{d}").glob("*.png")]             if paths.p("03_broll").is_dir() else []
        if graphics:
            raise _CannotCheck("فيه صور جرافيك بس مفيش خطة متجمعة تقول دي بتاعة أنهي حدث / graphic stills exist but "
                               "there is no compiled plan to name them: run `reel plan`")
    caps = paths.p("03_broll/captions")
    for f in sorted(caps.glob("CAP_*.png")) if caps.is_dir() else []:
        if f.stem.endswith(("_fg", "_bar")):
            files.append((f.stem.rsplit("_", 1)[0], f, "caption"))
    frame = _reel_frame(paths)
    out, sizes = [], []
    for bid, f, src in files:
        try:
            rect, size = _still_box(f)
        except Exception:  # noqa: BLE001
            raise _CannotCheck(f"مش قادر أقرا الصورة {f.name} / the still {f.name} cannot be read") from None
        sizes.append(size)
        if rect:
            out.append({"id": bid, "kind": "text", "rect": rect, "label": bid, "source": src, "_size": size})
    fb = _read(paths.p("08_quality_control/frames/boxes.json"))
    if fb is not None:
        if not isinstance(fb, dict) or not isinstance(fb.get("boxes"), list):
            raise _CannotCheck("قائمة صناديق فريمات بريمير مش مفهومة / the Premiere frame box list is not readable")
        fsize = tuple(fb.get("frame") or frame or ())
        if len(fsize) != 2:
            raise _CannotCheck("قائمة صناديق فريمات بريمير من غير مقاس / the Premiere frame box list has no frame size")
        for b in fb["boxes"]:
            if isinstance(b, dict) and b.get("id") and isinstance(b.get("rect"), list) and len(b["rect"]) == 4:
                out.append({"id": str(b["id"]), "kind": "text", "rect": b["rect"], "label": str(b["id"]),
                            "source": "premiere", "_size": fsize})
                sizes.append(fsize)
    frame = frame if frame else (sizes[0] if sizes else None)
    return out, frame, missing                           # each box keeps "_size": _boxes_scaled() scales it


def _platforms(paths, ctx, frame) -> list:
    from ..common import load_config
    ed = _read(paths.p("01_analysis/edit-decisions.json"))
    g = (ed.get("global") or {}) if isinstance(ed, dict) else {}
    for v in (g.get("platforms"), g.get("platform")):
        if v:
            if isinstance(v, str):
                return [v]
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                return v
            raise _CannotCheck("المنصات في قرارات المونتاج مكتوبة غلط / the plan's platforms are not a name or a list "
                               "of names")
    try:
        st = load_config("style.json", ctx).get("platforms")
    except Exception:  # noqa: BLE001
        st = None
    if st:
        if isinstance(st, str):
            return [st]
        if isinstance(st, list) and all(isinstance(x, str) for x in st):
            return st
        raise _CannotCheck("المنصات في style.json مكتوبة غلط / style.json platforms are not a name or a list of names")
    if frame and abs(frame[0] / frame[1] - 4 / 5) < 0.01:
        return [DEFAULT_4X5]
    return []


def _rtl(paths):
    """True/False from the transcript's script mix; None when the transcript exists but cannot be read."""
    try:
        wj = _read(paths.p("02_transcription/words.json"))
    except _CannotCheck:
        return None
    sc = ((wj.get("meta") or {}).get("scripts") or {}) if isinstance(wj, dict) else {}
    return bool(sc.get("rtl_primary")) and (sc.get("arabic_ratio") or 0) > 0


def check(paths, platforms=None, ctx=None, *, rtl=None) -> dict:
    """{"exit_code", "ids", "findings", "platforms", "message"}: Task 27's zones over this item's stills. Never
    raises: anything that stops the check is exit 2 with the reason."""
    res = {"exit_code": EXIT_ERROR, "ids": [], "findings": [], "platforms": list(platforms or []), "rtl": False}
    try:
        return _check(paths, platforms, ctx, rtl, res)
    except _CannotCheck as e:
        res["message"] = f"الفحص ماكملش: {e} / the check could not run"
        return res
    except Exception as e:  # noqa: BLE001  G10: exit 2 with the reason, never a crash
        res["message"] = f"فحص المناطق ما اشتغلش ({type(e).__name__}) / the safe-zone check did not run ({type(e).__name__})"
        return res


def _check(paths, platforms, ctx, rtl, res) -> dict:
    from .. import safe_zones as S
    bxs, frame, missing = _boxes_scaled(paths)
    plats = list(platforms) if platforms else _platforms(paths, ctx, frame)
    notes = []
    if rtl is None:
        rtl = _rtl(paths)
        if rtl is None:
            rtl = False
            notes.append("التفريغ مش مقروء، فالترتيب العربي للمنصة ماتفحصش / the transcript cannot be read: the "
                         "platform's Arabic layout was not checked")
    if missing:
        notes.append(f"{len(missing)} حدث من غير صورة لسه ({', '.join(missing[:5])}) / {len(missing)} event(s) have "
                     f"no still yet ({', '.join(missing[:5])})")
    res.update(platforms=plats or ["(default)"], rtl=bool(rtl), notes=notes)
    if not bxs or not frame:
        res["message"] = ("مفيش صور جرافيك أو كابشن لسه، فمفيش حاجة تتفحص / no graphic or caption stills yet: run "
                          "`reel previews` first — " + _what(paths, bxs)
                          + (" — " + "؛ ".join(notes) if notes else ""))
        res["nothing"] = True
        return res
    prof = S.union(plats, frame=frame, rtl=rtl) if plats else S.load(None, frame=frame, rtl=rtl)
    if prof.fallback or prof.aspect_mismatch:
        named = ", ".join(map(str, list(prof.unknown) + list(prof.damaged))) or "; ".join(map(str, prof.errors))[:200]
        raise _CannotCheck("بيانات المنصات مش صالحة أو شكلها مش زي الفيديو / the platform data is unusable or not the "
                           f"reel's shape ({named or prof.name})")
    found = S.violations(bxs, prof)
    ids = list(dict.fromkeys(f["box"] for f in found))
    res.update(findings=found, ids=ids, platforms=plats or [prof.name])
    partial = list(prof.unknown) + list(prof.damaged)
    if ids:
        res["exit_code"] = EXIT_FOUND
        res["message"] = (f"فيه عناصر داخلة في منطقة واجهة المنصة: {', '.join(ids)} — حرّكها لجوه / elements inside "
                          f"the platform's UI zone: {', '.join(ids)}; move them in")
    elif partial:
        raise _CannotCheck(f"منصة مش معروفة أو بياناتها بايظة: {', '.join(map(str, partial))} / an unknown or damaged "
                           f"platform: {', '.join(map(str, partial))}")
    else:
        res["exit_code"] = EXIT_OK
        res["message"] = (f"كل العناصر برّه مناطق واجهة المنصة ({len(bxs)} عنصر) / every element is clear of the "
                          f"platform's UI zones ({len(bxs)} checked)")
    if partial:
        res["message"] += (f"؛ ومنصة ماتفحصتش: {', '.join(map(str, partial))} / and a platform was not checked: "
                           f"{', '.join(map(str, partial))}")
    res["message"] += " — " + _what(paths, bxs)
    if notes:
        res["message"] += " — " + "؛ ".join(notes)
    return res


def _ar_n(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def _what(paths, bxs) -> str:
    """What the check looked at, Arabic first: our graphic and caption stills, and the Premiere frames' boxes only
    when the frames step recorded them (else the line says they were not)."""
    n = {k: sum(1 for b in bxs if b.get("source") == k) for k in ("graphic", "caption", "premiere")}
    fb = _read(paths.p("08_quality_control/frames/boxes.json"))
    listed = fb.get("boxes") if isinstance(fb, dict) and isinstance(fb.get("boxes"), list) else []
    skipped = sum(1 for b in listed if not (isinstance(b, dict) and b.get("id") and isinstance(b.get("rect"), list)
                                            and len(b["rect"]) == 4))
    if fb is None:
        pp_ar, pp_en = "مش متسجلة", "not recorded"
    elif not n["premiere"]:
        pp_ar, pp_en = "متسجلة بس فاضية", "recorded but empty"
    else:
        pp_ar, pp_en = f"{_ar_n(n['premiere'])} صندوق", f"{n['premiere']} box(es)"
    if skipped:
        pp_ar += f" ({_ar_n(skipped)} مش مقروء)"
        pp_en += f" ({skipped} unreadable, skipped)"
    return (f"اتفحص: {_ar_n(n['graphic'])} صورة جرافيك و{_ar_n(n['caption'])} صورة كابشن؛ فريمات بريمير: {pp_ar} / "
            f"checked: {n['graphic']} graphic still(s), {n['caption']} caption still(s); Premiere frames: {pp_en}")


def _boxes_scaled(paths) -> tuple:
    bxs, frame, missing = boxes(paths)
    out, seen = [], set()
    for b in bxs:
        size = b.pop("_size", None)
        rect = _scale(b["rect"], size, frame) if size else list(b["rect"])
        key = (b["id"], tuple(rect))
        if key not in seen:
            seen.add(key)
            out.append(dict(b, rect=rect))
    return out, frame, missing


def qc_item(paths, ctx=None) -> dict | None:
    """The `reel qc` line: None while the K-T4 switch is off (QC stays as it is). With the switch on: no platform
    chosen for the reel is a warning (not mandatory) that says the safe zones are not enforced and how to choose one;
    else a mandatory item that fails on an intrusion or when the check could not run, and passes with a plain note
    when there is nothing to check. The note names what was checked."""
    from . import switches
    if not switches.enabled(switches.QC_SAFEZONE_HARD_FAIL, ctx):
        return None
    try:
        chosen = _platforms(paths, ctx, _reel_frame(paths))         # a 4:5 reel gets feed_4x5 (the default)
    except _CannotCheck as e:
        return {"name": "safe_zone_gate", "ok": False, "mandatory": True, "detail": str(e), "ids": [],
                "exit_code": EXIT_ERROR}
    if not chosen:
        return {"name": "safe_zone_gate", "ok": False, "mandatory": False, "ids": [], "exit_code": EXIT_ERROR,
                "detail": "مناطق المنصة مااتفحصتش: مفيش منصة متحددة للفيديو ده / safe zones not enforced: no platform "
                          "set (choose one in edit-decisions.json global.platforms, or style.json platforms, then run "
                          "`reel qc` again)"}
    res = check(paths, chosen, ctx=ctx)
    ok = res["exit_code"] == EXIT_OK or bool(res.get("nothing"))
    return {"name": "safe_zone_gate", "ok": ok, "mandatory": True, "detail": res["message"], "ids": res["ids"],
            "exit_code": res["exit_code"]}
