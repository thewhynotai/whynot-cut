"""Smooth zoom and fades (3.0 T4.1): eased keyframes for the story editor's camera moves, and reel fades.

Pure: no file reads or writes. `reel plan` records what this module computes in the timeline spec: `camera_ease`
{ease_ms, curve, runs} always (a plan written before T4.1 has none and keeps building with hard punches; an empty run
list leaves the Gate 1 fingerprint as it was), `fades` only when one is on. `ppro-build` sends the runs and fades to the
Premiere bridge (wnc_ppro_lib.jsx: bezier keys on Motion Scale/Position, one black matte for the picture fade, Volume
keys on the dialogue / music); the preview renderer evaluates the same keys with `value_at` / `fade_gain`.

What is eased (rulings 2026-10-17/18): a story editor's punch_in (ease in and out over ease_ms) and slow_push (a push
across its whole first piece, whatever ease_ms says: a static slow_push would be a punch-in). punch_out and reframe
stay hard. Never the automatic pieces (jump-cut zoom masks, whose hard step hides the cut; source cutaways; the 4:5
window; shot framing), never a move inside 4:5 window framing (V1 there is the blurred cover copy), and never across a
shot boundary: an automatic neighbour (AUTO_*) eases only when it is the shot the move was composed over, and two
story pieces on different shots (a speaker change) meet hard; the shot identity comes from the plan's camera layer at
ease time (`with_shots`), never from the spec. A punch_in eases out only into a piece with no decision or a same-shot
automatic one, never into another story decision. An ease sits on a boundary only when the two pieces are contiguous in
the source (no pause or word cut between); at a cut the punch stays hard. A run of pieces of one decision (a punch-in
split by a cut) is one move: ease in on its first piece, ease out on its last. The ease of a boundary between two story
moves belongs to the later one. A piece too short for both eases shares its frames (the ease in half, the ease out the
rest minus one frame, so the keys never meet); a piece shorter than 2 frames gets no ease.

Keys carry segment values (scale_factor, offset_x, offset_y, the units of main_segments); the build turns them into
Premiere values relative to each clip's own Motion values, so nothing here depends on Premiere.
"""
from __future__ import annotations

import math

DEFAULT_EASE_MS = 250
MAX_EASE_MS = 2000
CURVE = "bezier"
STORY_MOVES = {"punch_in", "slow_push"}          # ruling 2026-10-18 (review 2 M-c): punch_out and reframe stay hard
PUSH_MOVES = {"slow_push"}                       # eased across the piece, not over ease_ms (round 3 item 1)
FADE_KEYS = ("video_in_ms", "video_out_ms", "audio_in_ms", "audio_out_ms")
BASE_VALUES = {"scale_factor": 1.0, "offset_x": 0.0, "offset_y": 0.0}   # the unzoomed picture (a push after a cut)
# The PREVIEW's assumption for Premiere's bezier keys (mode 5, influence 33 %) as a CSS-style cubic-bezier. NOT verified
# against Premiere: Gate 4 compares an exported mid-ease frame with the preview frame at the same time (T41-CASES.md).
BEZIER = (0.33, 0.0, 0.67, 1.0)
# the Gate 1 wording when a re-plan changed ONLY because the ease keys were added (executor ruling 2026-10-17)
EASE_REAPPROVE = {"en": "smooth zoom added to the punch-ins: have one more look and approve it again.",
                  "ar": "اتضاف زوم ناعم على الـ punch-ins. بص على الخطة بصّة كمان ووافق عليها تاني."}
SPEC_KEYS = ("camera_ease",)            # what the ease-only fingerprint leaves out


def _number(v):
    """(value, how): a finite number >= 0, else None. how: "ok" | "string" (a number written as text) | "bad"."""
    how = "ok"
    if isinstance(v, bool) or v is None:
        return None, "bad"
    if isinstance(v, str):
        try:
            v = float(v.strip())
        except ValueError:
            return None, "bad"
        how = "string"
    if not isinstance(v, (int, float)):
        return None, "bad"
    v = float(v)
    if not math.isfinite(v) or v < 0:
        return None, "bad"
    return v, how


def _half_up(v: float) -> int:
    return int(math.floor(v + 0.5))


def ease_settings(style: dict | None) -> tuple[int, list[str]]:
    """style.json camera.ease_ms -> (ms, warnings). Missing -> 250 (DEFAULT_EASE_MS); 0 = off; a bad value warns and
    uses the default; above MAX_EASE_MS it is clamped."""
    cam = (style or {}).get("camera")
    if cam is None:
        return DEFAULT_EASE_MS, []
    if not isinstance(cam, dict):
        return DEFAULT_EASE_MS, [f"style.json camera must be an object like {{\"ease_ms\": 250}} (got {cam!r}): "
                                 f"camera.ease_ms {DEFAULT_EASE_MS} used"]
    raw = cam.get("ease_ms")
    if raw is None:
        return DEFAULT_EASE_MS, []
    v, how = _number(raw)
    if v is None:
        return DEFAULT_EASE_MS, [f"style.json camera.ease_ms {raw!r} is not a number of milliseconds >= 0: "
                                 f"{DEFAULT_EASE_MS} used"]
    warns = []
    if how == "string":
        warns.append(f"style.json camera.ease_ms {raw!r} is text: taken as {_half_up(v)} (write it as a number)")
    if v > MAX_EASE_MS:
        warns.append(f"style.json camera.ease_ms {raw!r} is longer than {MAX_EASE_MS} ms: {MAX_EASE_MS} used")
        v = MAX_EASE_MS
    return _half_up(v), warns


def ease_frames(ms: int, fps) -> int:
    """Milliseconds -> whole frames at the sequence rate, half up (250 ms: 6 at 24/25 fps, 7 at 29.97, 8 at 30)."""
    from .common import ms_to_frame
    return ms_to_frame(int(ms), fps) if ms else 0


def fade_settings(style: dict | None, duration_ms, fps=None) -> tuple[dict | None, list[str]]:
    """style.json fades -> ({video_in_ms, video_out_ms, audio_in_ms, audio_out_ms} | None when all off, warnings).
    A bad value warns and is 0; a fade shorter than one frame at `fps` is 0 (off) with a warning; a fade longer than
    the reel is clamped, and in + out never exceeds the reel."""
    fd = (style or {}).get("fades")
    if fd is None:
        return None, []
    if not isinstance(fd, dict):
        return None, [f"style.json fades must be an object like {{\"video_in_ms\": 300}} (got {fd!r}): no fades"]
    dur = max(0, int(math.floor(float(duration_ms or 0))))
    out, warns = {}, []
    for k in FADE_KEYS:
        raw = fd.get(k)
        if raw is None:
            out[k] = 0
            continue
        v, how = _number(raw)
        if v is None:
            warns.append(f"style.json fades.{k} {raw!r} is not a number of milliseconds >= 0: no fade there")
            out[k] = 0
            continue
        if how == "string":
            warns.append(f"style.json fades.{k} {raw!r} is text: taken as {_half_up(v)} (write it as a number)")
        v = _half_up(v)
        if fps and 0 < v < 1000.0 / float(fps):
            warns.append(f"style.json fades.{k} {v} ms is shorter than one frame at {float(fps):.5g} fps: no fade there")
            v = 0
        if v > dur:
            warns.append(f"style.json fades.{k} {v} ms is longer than the reel ({dur} ms): {dur} used")
            v = dur
        out[k] = v
    for kind in ("video", "audio"):
        a, b = out[f"{kind}_in_ms"], out[f"{kind}_out_ms"]
        if a + b > dur:
            na = int(a * dur // (a + b))
            out[f"{kind}_in_ms"], out[f"{kind}_out_ms"] = na, dur - na
            warns.append(f"style.json fades: {kind} in {a} ms + out {b} ms is longer than the reel ({dur} ms): "
                         f"shortened to {na} + {dur - na} ms")
    if not any(out.values()):
        return None, warns
    return out, warns


def _values(seg: dict) -> dict:
    sf = seg.get("scale_factor")
    return {"scale_factor": float(1.0 if sf is None else sf), "offset_x": float(seg.get("offset_x") or 0.0),
            "offset_y": float(seg.get("offset_y") or 0.0)}


def _is_story(seg: dict) -> bool:
    """A story editor's move on V1. Not a windowed piece (4:5 framing stays hard, ruling 2026-10-17): its speaker is
    its own clip on the cutaway track and V1 under it is the blurred cover copy, so V1 keys would zoom the blur."""
    did = seg.get("decision_id")
    return (seg.get("camera") in STORY_MOVES and bool(did) and not str(did).startswith("AUTO_")
            and not seg.get("window"))


def _is_cutaway(seg: dict) -> bool:
    return seg.get("decision_id") == "AUTO_CUTAWAY"


def _contiguous(a: dict, b: dict, fps) -> bool:
    """No cut between piece a and the next piece b: same keep range, and b starts in the source where a ends."""
    if a.get("end_frame") != b.get("start_frame"):
        return False
    if a.get("keep_index") is not None and b.get("keep_index") is not None and a["keep_index"] != b["keep_index"]:
        return False
    if a.get("src_out_ms") is None or b.get("src_in_ms") is None:
        return True
    return abs(float(a["src_out_ms"]) - float(b["src_in_ms"])) <= 500.0 / float(fps) + 1e-6


def _same(a: dict, b: dict) -> bool:
    return all(abs(a[k] - b[k]) < 1e-9 for k in a)


def _same_shot(story: dict, nb: dict) -> bool:
    """May the story piece ease towards its neighbour? (review 2 IMP-1, round 4 I-1) A plain neighbour (no decision)
    yes. Another story piece: not when both sit on a known shot and the shots differ (a speaker change). An automatic
    one (AUTO_SHOT ...): only when it is the shot the move was composed over. The shot identity (`shot_offset_x`) is
    put on the pieces at ease time by `with_shots` from the camera layer; it is never stored in the spec."""
    did = nb.get("decision_id")
    if not did:
        return True
    if not str(did).startswith("AUTO_"):
        a, b = story.get("shot_offset_x"), nb.get("shot_offset_x")
        if a is None or b is None:
            # round 5: in a plan with shots (podcast / multicam) a story piece whose shot is unknown is ANOTHER shot;
            # a single-camera plan (no shot ids at all) keeps easing between story moves
            return not (story.get("_shots") or nb.get("_shots"))
        return abs(float(a) - float(b)) <= 0.5
    if story.get("shot_offset_x") is None:
        return False                                  # no record of the shot under the move: never ease across one
    return abs(float(nb.get("offset_x") or 0.0) - float(story["shot_offset_x"])) <= 0.5


def with_shots(segments: list, camera: list | None, fps=None) -> list:
    """Copies of the V01 pieces with the shot identity (`shot_offset_x`) of each story piece, taken from the plan's
    camera layer (shots.compose_camera: a story move composed over a shot carries the shot's offset): the entry of the
    same decision whose span holds the piece's source in-point, matched in FRAMES with common.ms_to_frame exactly as
    plan.apply_framing cuts the pieces (round 5: a move at 3010 ms starts its piece at frame 75 = 3000 ms at 25 fps).
    When the layer carries any shot id, every copy is marked `_shots` (a story piece left without one is then another
    shot, never the same). Round 4 I-3 (option B): only for easing; the spec's pieces never change for it."""
    from .common import ms_to_frame
    cams = [c for c in camera or [] if c.get("shot_offset_x") is not None and c.get("decision_id")]

    def frame(ms):
        return ms_to_frame(int(round(float(ms))), fps)
    out = []
    for sg in segments or []:
        sg = dict(sg)
        if cams:
            sg["_shots"] = True
        did, t = sg.get("decision_id"), sg.get("src_in_ms")
        if did and t is not None and sg.get("shot_offset_x") is None:
            f = frame(t)
            hit = next((c for c in cams if c["decision_id"] == did
                        and frame(c.get("at_ms", 0)) <= f < frame(c.get("until_ms", 0))), None)
            if hit is not None:
                sg["shot_offset_x"] = float(hit["shot_offset_x"])
        out.append(sg)
    return out


def _neighbour_ok(story: dict, nb: dict, a: dict, b: dict, fps) -> bool:
    """An ease may cross the boundary a|b (story piece and neighbour nb, in timeline order)."""
    return not _is_cutaway(nb) and _contiguous(a, b, fps) and _same_shot(story, nb)


def ease_keys(segments: list, fps, ease_ms: int) -> list[dict]:
    """The eased runs of the compiled V01 pieces: [{decision_id, camera, pieces: [first, last], ease_in, ease_out,
    interpolation}], ease_in = {piece, frames, from, value}, ease_out = {piece, frames, value, to} (or None). Pieces
    are main_segments indexes (= the V1 clip indexes of the build). A run with neither ease is left out. A slow_push's
    ease in spans its first piece (start to end minus one frame) from the picture before it (the unzoomed picture
    after a cut, at frame 0 or next to another shot) and has no ease out."""
    E = ease_frames(ease_ms, fps) if ease_ms and ease_ms > 0 else 0
    segs = list(segments or [])
    runs, i = [], 0
    while i < len(segs):
        if not _is_story(segs[i]):
            i += 1
            continue
        j = i
        while (j + 1 < len(segs) and _is_story(segs[j + 1]) and segs[j + 1].get("decision_id") == segs[i].get("decision_id")
               and segs[j + 1].get("camera") == segs[i].get("camera")):
            j += 1
        first, last = segs[i], segs[j]
        ein = eout = None
        if first.get("camera") in PUSH_MOVES:
            prev = segs[i - 1] if i > 0 else None
            src = (_values(prev) if prev is not None and _neighbour_ok(first, prev, prev, first, fps)
                   else dict(BASE_VALUES, offset_x=float(first.get("shot_offset_x") or 0.0)))
            n = int(first["end_frame"]) - int(first["start_frame"])
            if n >= 2 and not _same(src, _values(first)):
                runs.append({"decision_id": first.get("decision_id"), "camera": first.get("camera"), "pieces": [i, j],
                             "ease_in": {"piece": i, "frames": n - 1, "from": src, "value": _values(first)},
                             "ease_out": None, "interpolation": CURVE})
            i = j + 1
            continue
        if E <= 0:
            i = j + 1
            continue
        if i > 0:
            prev = segs[i - 1]
            if _neighbour_ok(first, prev, prev, first, fps) and not _same(_values(prev), _values(first)):
                ein = {"piece": i, "frames": E, "from": _values(prev), "value": _values(first)}
        if j + 1 < len(segs):
            nxt = segs[j + 1]
            # round 4 I-2: ease out only into a piece with no decision or a same-shot automatic one; never into
            # another story decision (a reframe or punch_out starts hard)
            nd = nxt.get("decision_id")
            if ((not nd or str(nd).startswith("AUTO_")) and _neighbour_ok(last, nxt, last, nxt, fps)
                    and not _same(_values(last), _values(nxt))):
                eout = {"piece": j, "frames": E, "value": _values(last), "to": _values(nxt)}
        for side, seg in ((ein, first), (eout, last)):
            if side:
                n = int(seg["end_frame"]) - int(seg["start_frame"])
                side["frames"] = min(E, n) if n >= 2 else 0       # a 1-frame piece has no room for an ease
        if i == j and ein and eout and ein["frames"] + eout["frames"] >= int(first["end_frame"]) - int(first["start_frame"]):
            # both eases on one piece would meet (their middle keys merge into one): the ease in takes half, the ease out
            # what is left minus one frame, so the four keys stay apart (12 frames at 6 + 6 -> 6 + 5)
            n = int(first["end_frame"]) - int(first["start_frame"])
            ein["frames"] = min(E, n // 2)
            eout["frames"] = min(E, n - 1 - ein["frames"])
        if ein and ein["frames"] < 1:
            ein = None
        if eout and eout["frames"] < 1:
            eout = None
        if ein or eout:
            runs.append({"decision_id": first.get("decision_id"), "camera": first.get("camera"), "pieces": [i, j],
                         "ease_in": ein, "ease_out": eout, "interpolation": CURVE})
        i = j + 1
    return runs


def _frame(v):
    """An int frame from a manual_verse record value, or None (round 7 P3-3: a malformed entry is skipped)."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if math.isfinite(f) else None


def verse_spans(verse, held: bool = False) -> list:
    """[(start_frame, end_frame)) half-open sequence-frame spans of the records plan.apply_ease passes: the spec's
    manual_verse, and the caption runs held after one (verse_hold, marked `held: True`; round 9). `held` False: the
    unmarked records (a recited verse), True: the marked ones (the verse may go on). An entry that is not a dict or
    has no usable frames is skipped, never a crash (P3-3)."""
    out = []
    for v in verse if isinstance(verse, list) else []:
        if not isinstance(v, dict) or (v.get("held") is True) != held:
            continue
        a, b = _frame(v.get("start_frame")), _frame(v.get("end_frame"))
        if a is not None and b is not None and b > a:
            out.append((a, b))
    return out


def _mmss(ms: float) -> str:
    t = max(0, int(round(ms / 1000.0)))
    return f"{t // 60:02d}:{t % 60:02d}"


def outside_verse(runs: list, segments: list, verse: list | None, fps=None) -> tuple[list, list, list, list[str]]:
    """No camera motion during a recited verse (round 7 P3-2 ruling, religious content: the conservative choice), nor
    during a caption run held after one (a `verse` record marked `held: True`: the verse may go on; round 9, the
    round-7 P3-4 ruling: audio that might be a recitation is treated as one). An ease whose window OVERLAPS a span is
    dropped and that side stays hard; a slow_push whose piece overlaps a span is not pushed. The ease-in window is
    [start, start + frames] (its last key sits AT start + frames, round 8 P3-1), the ease-out window [end - frames, end); spans are half-open sequence frames. The ease-out's last key sits ON the
    out point, the next piece's first frame, so a verse starting exactly there meets a cut, not motion: that ease is
    kept, since dropping it would make the same cut a full hard step (round 8 review P3-1). The runs stay as the build contract
    knows them (round 8 P2-1): a dropped side of a run that keeps its other ease goes to `verse_dropped` (decision,
    camera, side, start_ms), a move left with no ease to `verse_hard` (decision, camera, sides, start_ms); start_ms is
    the time of the side that was dropped (round 8 P3-4). A side lost ONLY to a held run is marked `held: True` (its
    words say "the verse may go on", never that a verse is recited). One warning per move (round 9 P3-2: the runs of a
    move split by a cutaway share it), at the time of its first side lost to a verse, else to a held run, in plain
    English and Egyptian Arabic. Returns (runs, verse_dropped, verse_hard, warnings)."""
    spans, maybe = verse_spans(verse), verse_spans(verse, held=True)
    if not spans and not maybe:
        return runs, [], [], []
    rate = float(fps) if fps else 24.0

    def hits(a, b):
        """"verse" when frames [a, b) overlap a recited span, "held" when only a held run, else None."""
        return next((k for k, ss in (("verse", spans), ("held", maybe)) if any(a < z and r < b for r, z in ss)), None)
    out, dropped, hard, per = [], [], [], {}
    for r in runs:
        r = dict(r)
        ein, eout, sides, kinds = r.get("ease_in"), r.get("ease_out"), {}, {}
        if ein:
            sg = segments[ein["piece"]]
            a = int(sg["start_frame"])
            b = int(sg["end_frame"]) if r.get("camera") in PUSH_MOVES else a + int(ein["frames"]) + 1
            kinds["in"] = hits(a, b)
            if kinds["in"]:
                r["ease_in"] = None
                sides["in"] = a * 1000 / rate
        if eout:
            sg = segments[eout["piece"]]
            b = int(sg["end_frame"])
            kinds["out"] = hits(b - int(eout["frames"]), b)
            if kinds["out"]:
                r["ease_out"] = None
                sides["out"] = (b - int(eout["frames"])) * 1000 / rate
        if not sides:
            out.append(r)
            continue
        at = per.setdefault(r.get("decision_id"), {})
        for side, ms in sides.items():
            at[kinds[side]] = min(ms, at.get(kinds[side], ms))
        if r.get("ease_in") or r.get("ease_out"):
            out.append(r)
            dropped += [{"decision_id": r.get("decision_id"), "camera": r.get("camera"), "side": side,
                         "start_ms": int(round(ms)), **({"held": True} if kinds[side] == "held" else {})}
                        for side, ms in sides.items()]
        else:
            hard.append({"decision_id": r.get("decision_id"), "camera": r.get("camera"), "sides": list(sides),
                         "start_ms": int(round(min(sides.values()))),
                         **({} if "verse" in kinds.values() else {"held": True})})
    warns = []
    for did, at in per.items():
        t = _mmss(at.get("verse", at.get("held")))
        warns.append(f"{did} at {t}: no smooth zoom while a verse is recited, so the move stays hard there / مفيش زوم "
                     f"ناعم وقت الآية عند {t}، الحركة فضلت من غير نعومة هناك" if "verse" in at else
                     f"{did} at {t}: no smooth zoom where the verse may go on (held captions), so the move stays hard "
                     f"there / مفيش زوم ناعم في وقت ممكن الآية تكون مكمّلة عند {t}، الحركة فضلت من غير نعومة هناك")
    return out, dropped, hard, warns


def spec_fields(segments: list, style: dict | None, fps, duration_ms, camera: list | None = None,
                verse: list | None = None) -> tuple[dict, list[str]]:
    """What `reel plan` adds to the timeline spec, and its warnings: {"camera_ease": {ease_ms, curve, runs}} always
    (round 3 item 2: the plan records the value it was written with; an empty `runs` does not change the Gate 1
    fingerprint, plan.spec_fingerprint), plus {"fades": {...}} when a fade is on. `camera`: the plan's camera layer,
    for the shot each story move sits on (with_shots). `verse`: the plan's manual_verse spans and the caption runs
    held after one, marked `held: True` (no camera motion during either: outside_verse)."""
    out, warns = {}, []
    ms, w = ease_settings(style)
    warns += w
    runs, dropped, hard, w = outside_verse(ease_keys(with_shots(segments, camera, fps), fps, ms), segments, verse, fps)
    warns += w
    out["camera_ease"] = {"ease_ms": ms, "curve": CURVE, "runs": runs, **({"verse_dropped": dropped} if dropped else {}),
                          **({"verse_hard": hard} if hard else {})}
    fades, w = fade_settings(style, duration_ms, fps)
    warns += w
    if fades:
        out["fades"] = fades
    return out, warns


def ease_only_change(spec: dict, approved_fp: str | None, fingerprint_of) -> bool:
    """True when the approved fingerprint is the spec's WITHOUT its ease keys: the only change since the approval is
    the smooth zoom added to the punch-ins. `fingerprint_of(spec_dict)` is plan's hash of a spec body."""
    if not approved_fp or not isinstance(spec, dict) or not any(k in spec for k in SPEC_KEYS):
        return False
    return fingerprint_of({k: v for k, v in spec.items() if k not in SPEC_KEYS}) == approved_fp


def _bezier(u: float) -> float:
    """The eased progress at linear progress u (0..1) on the cubic-bezier BEZIER."""
    u = min(1.0, max(0.0, u))
    x1, y1, x2, y2 = BEZIER

    def bx(t):
        return 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3

    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if bx(mid) < u:
            lo = mid
        else:
            hi = mid
    t = (lo + hi) / 2
    return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3


def _mix(a: dict, b: dict, e: float) -> dict:
    return {k: a[k] + (b[k] - a[k]) * e for k in a}


def value_at(spec: dict, piece: int, frame_in_piece: float) -> dict:
    """{scale_factor, offset_x, offset_y} of V01 piece `piece` at `frame_in_piece` frames after its start, with the
    spec's ease keys applied (the preview renderer's per-frame value)."""
    seg = spec["main_segments"][piece]
    n = int(seg["end_frame"]) - int(seg["start_frame"])
    for r in (spec.get("camera_ease") or {}).get("runs") or []:
        ein, eout = r.get("ease_in"), r.get("ease_out")
        if ein and ein["piece"] == piece and frame_in_piece < ein["frames"]:
            return _mix(ein["from"], ein["value"], _bezier(frame_in_piece / ein["frames"]))
        if eout and eout["piece"] == piece and frame_in_piece > n - eout["frames"]:
            return _mix(eout["value"], eout["to"], _bezier((frame_in_piece - (n - eout["frames"])) / eout["frames"]))
    return _values(seg)


def fade_gain(spec: dict, frame: float, kind: str = "video") -> float:
    """0..1: the picture (kind "video") or sound ("audio") level at sequence `frame` from the spec's fades (linear)."""
    fd = spec.get("fades") or {}
    fin, fout = float(fd.get(f"{kind}_in_ms") or 0), float(fd.get(f"{kind}_out_ms") or 0)
    fps = float(spec.get("fps") or 24)
    t = frame * 1000.0 / fps
    dur = float(spec["duration_frames"]) * 1000.0 / fps
    g = 1.0
    if fin > 0 and t < fin:
        g = min(g, max(0.0, t / fin))
    if fout > 0 and t > dur - fout:
        g = min(g, max(0.0, (dur - t) / fout))
    return g
