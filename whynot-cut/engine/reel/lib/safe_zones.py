# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Platform safe-zone profiles (Phase 4 Task 27, R-4.5): where each platform's own UI covers a reel, scaled to any frame
size, plus the platform's delivery-encode rules and the check of an exported file against them.

Data: config/defaults/safe-zones.json. Every number carries a basis (official | template | screenshot | community), a
source URL and the date it was read; the strict loader refuses a number without them. A value a platform does not
publish stays absent from the file (no check), never a guess. Community numbers are flagged in the profile and in the
finding text. Rectangles are [x0, y0, x1, y1] in pixels with x1/y1 exclusive: a box that only touches a zone's edge
does not overlap it.

Nothing here raises for a real user (G10): an unreadable or damaged file falls back to today's built-in numbers
(legacy_safe_area), a damaged profile is dropped with a reason, a bad box is skipped, an unmeasured value is not a
finding. `read_profiles(strict=True)` is the one place that raises (SafeZoneError), for the loader's tests.
Standard library only.
"""
from __future__ import annotations

import datetime
import json
import math
import re
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parents[3] / "config" / "defaults" / "safe-zones.json"
BASES = ("official", "template", "screenshot", "community")
ENCODE_KEYS = {"codec", "profile", "level_max", "gop_s", "closed_gop", "pix_fmt", "audio", "audio_sample_rate_max",
               "audio_channels_max", "audio_bitrate_kbps_min", "container", "fps_min", "fps_max", "bitrate_kbps_min",
               "loudness_lufs", "true_peak_dbtp"}
ENCODE_META = {"basis", "source", "retrieved", "note"}
SHAPE_KINDS = {"shape", "decorative"}
LOUDNESS_TOLERANCE_LU = 1.0
SHAPE_P2_BELOW = 0.20            # a decorative shape overlapping less than this share of its area is P2, else P1

# Today's numbers, kept as the fallback when the file is unreadable (G10) and for "no profile chosen" (byte-identical).
_LEGACY_AREA = {"left": 90, "right": 90, "top": 250, "bottom": 420}      # config/defaults/subtitle-style.json safe_area
_LEGACY_TOP_PX = 220                                                      # previews.SAFE_TOP_PX at 1920 px height


class SafeZoneError(ValueError):
    """A profile or file the strict loader refuses (names the profile and the number)."""


@dataclass(frozen=True)
class Zone:
    name: str
    kind: str
    rect: tuple
    basis: str
    source: str
    retrieved: str
    note: str = ""
    platform: str = ""
    platform_ar: str = ""
    mirror_rtl: bool = False


@dataclass(frozen=True)
class Profile:
    name: str
    frame: tuple
    zones: tuple
    safe_text: tuple
    caption_band: tuple
    encode: dict | None = None
    flags: tuple = ()
    platform_ar: str = ""
    gaps: tuple = ()          # what the platform shows but publishes no number for (stated in the QC line, never silent)
    fallback: bool = False
    fallback_reason: str = ""
    aspect_mismatch: bool = False
    rtl: bool = False

    def scaled(self, frame) -> "Profile":
        fr = _frame(frame)
        if fr is None or fr == tuple(self.frame):
            return self
        fw, fh = self.frame
        W, H = fr

        def lo(v, n, d):                       # floor(v * n / d), exact
            return (v * n) // d

        def hi(v, n, d):                       # ceil(v * n / d), exact
            return -((-v * n) // d)

        zones = tuple(replace(z, rect=(lo(z.rect[0], W, fw), lo(z.rect[1], H, fh), hi(z.rect[2], W, fw), hi(z.rect[3], H, fh)))
                      for z in self.zones)
        safe = (hi(self.safe_text[0], W, fw), hi(self.safe_text[1], H, fh), lo(self.safe_text[2], W, fw), lo(self.safe_text[3], H, fh))
        cb = _clip(self.caption_band_raw(W, H, fw, fh), safe)
        return replace(self, frame=fr, zones=zones, safe_text=safe, caption_band=cb,
                       aspect_mismatch=self.aspect_mismatch or abs(W * fh - H * fw) * 100 > W * fh)

    def caption_band_raw(self, W, H, fw, fh):
        c = self.caption_band
        return ((c[0] * W) // fw, (c[1] * H) // fh, -((-c[2] * W) // fw), -((-c[3] * H) // fh))

    def mirrored(self) -> "Profile":
        W = self.frame[0]

        def m(r):
            return (W - r[2], r[1], W - r[0], r[3])
        return replace(self, zones=tuple(replace(z, rect=m(z.rect)) for z in self.zones), safe_text=m(self.safe_text),
                       caption_band=m(self.caption_band), rtl=not self.rtl)


def _clip(r, bound):
    x0, y0, x1, y1 = max(r[0], bound[0]), max(r[1], bound[1]), min(r[2], bound[2]), min(r[3], bound[3])
    return (x0, y0, max(x0, x1), max(y0, y1))


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _frame(f):
    if isinstance(f, (list, tuple)) and len(f) == 2 and all(_int(v) and v > 0 for v in f):
        return (int(f[0]), int(f[1]))
    if isinstance(f, (list, tuple)) and len(f) == 2 and all(_num(v) and v > 0 and float(v).is_integer() for v in f):
        return (int(f[0]), int(f[1]))
    return None


# --------------------------------------------------------------------------- legacy numbers
def legacy_safe_area() -> dict:
    """Today's subtitle-style.json safe_area (1080x1920): what the engine uses when no profile is chosen."""
    return dict(_LEGACY_AREA)


def legacy_safe_top_px(frame_h=1920):
    """Today's previews.SAFE_TOP_PX (220 at 1920 px height), scaled to the frame height."""
    return _LEGACY_TOP_PX if frame_h in (None, 1920) else _LEGACY_TOP_PX * frame_h / 1920


def _legacy_profile(reason: str) -> Profile:
    a = _LEGACY_AREA
    W, H = 1080, 1920
    src = "built-in (the numbers the engine used before safe-zone profiles)"
    z = lambda n, k, r: Zone(n, k, r, "community", src, "2026-10-17", "built-in fallback", "legacy", "إنستجرام")  # noqa: E731
    return Profile("legacy", (W, H),
                   (z("top_ui", "top", (0, 0, W, a["top"])), z("bottom_ui", "bottom", (0, H - a["bottom"], W, H)),
                    z("left_margin", "side", (0, 0, a["left"], H)), z("right_margin", "side", (W - a["right"], 0, W, H))),
                   (a["left"], a["top"], W - a["right"], H - a["bottom"]),
                   (a["left"], H - a["bottom"] - 248, W - a["right"], H - a["bottom"]), None,
                   ("built-in numbers: no platform profile was readable",), "إنستجرام", fallback=True, fallback_reason=reason)


# --------------------------------------------------------------------------- loading and validation
def _check_source(where, d):
    if d.get("basis") not in BASES:
        raise SafeZoneError(f"{where}: basis must be one of {', '.join(BASES)} (got {d.get('basis')!r})")
    s = d.get("source")
    if not isinstance(s, str) or not re.match(r"https?://\S{4,}$", s.strip()):
        raise SafeZoneError(f"{where}: a number needs the platform page it came from as its source URL (got {s!r})")
    r = d.get("retrieved")
    if not isinstance(r, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r):
        raise SafeZoneError(f"{where}: retrieved must be a YYYY-MM-DD date (got {r!r})")
    try:
        day = datetime.date.fromisoformat(r)
    except ValueError:
        raise SafeZoneError(f"{where}: retrieved is not a real date ({r})") from None
    if day > datetime.date.today() + datetime.timedelta(days=1):
        raise SafeZoneError(f"{where}: retrieved is in the future ({r})")


def _rect(where, v, W, H, strict_area=False):
    if not (isinstance(v, (list, tuple)) and len(v) == 4 and all(_int(x) for x in v)):
        raise SafeZoneError(f"{where}: rect must be four whole numbers (got {v!r})")
    x0, y0, x1, y1 = v
    ok = 0 <= x0 <= x1 <= W and 0 <= y0 <= y1 <= H and (not strict_area or (x0 < x1 and y0 < y1))
    if not ok:
        raise SafeZoneError(f"{where}: rect {list(v)} is not inside the {W}x{H} frame")
    return (x0, y0, x1, y1)


def _parse_profile(name, d) -> Profile:
    if not isinstance(d, dict):
        raise SafeZoneError(f"{name}: not an object")
    fr = _frame(d.get("frame"))
    if fr is None:
        raise SafeZoneError(f"{name}: frame must be [width, height] of positive whole numbers")
    W, H = fr
    ar = d.get("platform_ar") if isinstance(d.get("platform_ar"), str) else name
    zs = d.get("zones")
    if not isinstance(zs, list) or not zs:
        raise SafeZoneError(f"{name}: no zones")
    zones, flags = [], []
    for i, z in enumerate(zs):
        if not isinstance(z, dict) or not isinstance(z.get("name"), str) or not z["name"]:
            raise SafeZoneError(f"{name}: zone {i} has no name")
        where = f"{name}/{z['name']}"
        rect = _rect(where, z.get("rect"), W, H)
        _check_source(where, z)
        kind = z.get("kind") if isinstance(z.get("kind"), str) else "ui"
        zones.append(Zone(z["name"], kind, rect, z["basis"], z["source"].strip(), z["retrieved"], str(z.get("note", "")),
                          name, ar, z.get("mirror_rtl") is True))
        if z["basis"] == "community" and "community" not in flags:
            flags.append("community")
    safe = _rect(f"{name}/safe_text", d.get("safe_text"), W, H, True)
    cb = _rect(f"{name}/caption_band", d.get("caption_band"), W, H, True)
    if not (safe[0] <= cb[0] and cb[2] <= safe[2] and safe[1] <= cb[1] and cb[3] <= safe[3]):
        raise SafeZoneError(f"{name}: caption_band must sit inside safe_text")
    enc = d.get("encode")
    if enc is not None:
        if not isinstance(enc, dict):
            raise SafeZoneError(f"{name}/encode: not an object")
        extra = set(enc) - ENCODE_KEYS - ENCODE_META
        if extra:
            raise SafeZoneError(f"{name}/encode: unknown keys {sorted(extra)}")
        _check_source(f"{name}/encode", enc)
        _check_encode_types(name, enc)
        if enc["basis"] == "community" and "community" not in flags:
            flags.append("community")
    if "community" in flags:
        flags[flags.index("community")] = "community numbers (last resort, re-verify): " + ", ".join(
            sorted({z.name for z in zones if z.basis == "community"}) or ["encode"])
    gaps = d.get("gaps", [])
    if not isinstance(gaps, list) or not all(isinstance(g, str) and g.strip() for g in gaps):
        raise SafeZoneError(f"{name}: gaps must be a list of plain-words strings")
    return Profile(name, fr, tuple(zones), safe, cb, dict(enc) if enc else None, tuple(flags), ar, tuple(gaps))


_ENC_STR = {"profile", "pix_fmt", "audio"}
_ENC_NUM = {"level_max", "gop_s", "audio_sample_rate_max", "audio_channels_max", "audio_bitrate_kbps_min", "fps_min",
            "fps_max", "bitrate_kbps_min", "loudness_lufs", "true_peak_dbtp"}


def _check_encode_types(name, enc):
    for k, v in enc.items():
        if k in ENCODE_META:
            continue
        where = f"{name}/encode/{k}"
        if k in ("codec", "container"):
            ok = (isinstance(v, str) and v.strip()) or (isinstance(v, list) and v and all(isinstance(x, str) and x.strip() for x in v))
        elif k == "closed_gop":
            ok = isinstance(v, bool)
        elif k in _ENC_STR:
            ok = isinstance(v, str) and v.strip()
        else:
            ok = _num(v)
        if not ok:
            raise SafeZoneError(f"{where}: unusable value {v!r}")


def _read_file(path):
    try:
        raw = Path(path).read_bytes()
    except (OSError, ValueError, TypeError) as e:
        raise SafeZoneError(f"cannot read {path}: {e.__class__.__name__}") from None
    try:
        d = json.loads(raw.decode("utf-8-sig"))
    except Exception as e:  # noqa: BLE001  ValueError, UnicodeDecodeError, RecursionError on a hostile file: all "not usable"
        raise SafeZoneError(f"{path} is not valid JSON ({e.__class__.__name__})") from None
    if not isinstance(d, dict) or not isinstance(d.get("profiles"), dict) or not d["profiles"]:
        raise SafeZoneError(f"{path} has no profiles")
    return d


def read_profiles(path=None, strict=False):
    """(profiles by name, default name, reasons). strict=True raises SafeZoneError on the first problem; otherwise a
    bad profile is dropped (its reason recorded) and an unreadable file gives ({}, None, [reason])."""
    reasons = []
    try:
        d = _read_file(path or DEFAULT_FILE)
    except SafeZoneError as e:
        if strict:
            raise
        return {}, None, [str(e)]
    profs = {}
    for name, body in d["profiles"].items():
        try:
            profs[name] = _parse_profile(name, body)
        except SafeZoneError as e:
            if strict:
                raise
            reasons.append(str(e))
    want = d.get("default")
    default = want if isinstance(want, str) and want in profs else None
    if want is not None and default is None:
        reasons.append(f"default profile {str(want)[:40]!r} is not usable")
    if profs and default is None:
        default = next(iter(profs))
    return profs, default, reasons


def _key(name):
    return name.strip().lower() if isinstance(name, str) and len(name) < 100 else None


def load(profile=None, *, client_default=None, frame=None, rtl=False, path=None) -> Profile:
    """The profile to use: the reel's choice > the client's default > the file's default. Never raises: an unknown
    name or a damaged file falls back with `fallback_reason` set (`fallback` is True only for the built-in numbers).
    frame=(w, h) scales to that size; rtl=True mirrors the platform's right-to-left (Arabic) layout when it has one."""
    profs, default, reasons = read_profiles(path)
    if not profs:
        return _scale_rtl(_legacy_profile("; ".join(reasons) or "no profiles"), frame, rtl)
    note = list(reasons)
    chosen = None
    for label, want in (("reel", profile), ("client", client_default)):
        if want is None or want == "":
            continue
        k = _key(want)
        if k in profs:
            chosen = profs[k]
            break
        note.append(f"unknown {label} profile {str(want)[:40]!r}")
    if chosen is None:
        chosen = profs[default]
    out = replace(chosen, fallback_reason="; ".join(note))
    return _scale_rtl(out, frame, rtl)


def _scale_rtl(p: Profile, frame, rtl) -> Profile:
    p = p.scaled(frame)
    if rtl and any(z.mirror_rtl for z in p.zones) and not p.rtl:
        p = p.mirrored()
    return p


def union(profiles, *, frame=None, rtl=False, path=None) -> Profile:
    """A multi-platform reel: every zone of every target profile, the safe text is where they all agree. A name that is
    not a known profile is left out and named in `fallback_reason` (the QC line shows it: a typo is never a silent pass)."""
    known = read_profiles(path)[0]
    ps, unknown = [], []
    for p in profiles or []:
        if isinstance(p, Profile):
            ps.append(p)
        elif _key(p) in known:
            ps.append(load(p, path=path))
        else:
            unknown.append(str(p)[:40])
    note = "; ".join(f"unknown profile {u!r}" for u in unknown)
    if not ps:
        base = load(None, frame=frame, rtl=rtl, path=path)
        return replace(base, fallback_reason="; ".join(x for x in (base.fallback_reason, note) if x))
    fr = _frame(frame) or ps[0].frame
    ps = [_scale_rtl(p, fr, rtl) for p in ps]
    zones = tuple(z for p in ps for z in p.zones)
    safe = (max(p.safe_text[0] for p in ps), max(p.safe_text[1] for p in ps), min(p.safe_text[2] for p in ps), min(p.safe_text[3] for p in ps))
    if safe[0] >= safe[2] or safe[1] >= safe[3]:
        safe = ps[0].safe_text
    cb = _clip(ps[0].caption_band, safe)
    reasons = [p.fallback_reason for p in ps if p.fallback_reason] + ([note] if note else [])
    return Profile("+".join(p.name for p in ps), fr, zones, safe, cb, None,
                   tuple(dict.fromkeys(f for p in ps for f in p.flags)), " + ".join(dict.fromkeys(p.platform_ar for p in ps)),
                   tuple(dict.fromkeys(g for p in ps for g in p.gaps)),
                   any(p.fallback for p in ps), "; ".join(reasons), any(p.aspect_mismatch for p in ps), rtl)


def safe_width(profile, side_margin_px=0) -> int:
    """Width a caption line may use: the safe text width minus a margin on each side (caption fit-or-fail, R-4.1)."""
    if not isinstance(profile, Profile):
        return 0
    m = side_margin_px if _num(side_margin_px) and side_margin_px > 0 else 0
    return max(0, int(profile.safe_text[2] - profile.safe_text[0] - 2 * m))


# --------------------------------------------------------------------------- violations
_AR_DIGITS = str.maketrans("0123456789.-", "٠١٢٣٤٥٦٧٨٩٫-")
_ZONE_AR = {"top": "الشريط العلوي", "bottom": "المنطقة السفلية (الوصف والأزرار)", "side": "الهامش الجانبي", "rail": "منطقة أزرار"}


def _ar(n) -> str:
    n = round(float(n), 1)
    return (str(int(n)) if n == int(n) else str(n)).translate(_AR_DIGITS)


def _box_rect(b):
    r = b.get("rect") if isinstance(b, dict) else None
    if not (isinstance(r, (list, tuple)) and len(r) == 4 and all(_num(v) for v in r)):
        return None
    return tuple(r) if r[2] > r[0] and r[3] > r[1] else None


def _overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return (w, h) if w > 0 and h > 0 else None


def _severity(kind, ow, oh, area):
    if kind not in SHAPE_KINDS:
        return "P1"
    return "P2" if ow * oh * round(1 / SHAPE_P2_BELOW) < area else "P1"      # integer maths: exactly 20 % is P1


def violations(boxes, profile, *, face=None) -> list:
    """Every graphic/text box tested against each UI zone of the profile and, when `face` is given, the head envelope
    (R-6.4). A box is {"id", "kind": "text"|"shape", "rect": [x0, y0, x1, y1], "label": plain-words name}. Findings come
    in box order, then zone order: {box, kind, zone, platform, severity P1|P2, overlap_w, overlap_h, overlap_px,
    community, text}. A box that cannot be read is skipped, never an error."""
    if not isinstance(profile, Profile) or not isinstance(boxes, (list, tuple)):
        return []
    fr = _box_rect({"rect": face}) if face is not None else None
    W = profile.frame[0]
    out = []
    for i, b in enumerate(boxes):
        r = _box_rect(b)
        if r is None:
            continue
        bid = b.get("id") if b.get("id") not in (None, "") else f"box-{i}"
        kind = b.get("kind") if isinstance(b.get("kind"), str) else "text"
        label = b.get("label") if isinstance(b.get("label"), str) and b.get("label") else "العنصر"
        area = (r[2] - r[0]) * (r[3] - r[1])
        hits = [(z, o) for z in profile.zones for o in [_overlap(r, z.rect)] if o]
        total = min(area, sum(o[0] * o[1] for _, o in hits))        # a shape straddling two zones is judged on both together
        for z, (ow, oh) in hits:
            zk = z.kind if z.kind in _ZONE_AR else "side"
            depth = oh if zk in ("top", "bottom") else ow if zk in ("side", "rail") else min(ow, oh)
            plat = z.platform_ar or z.platform
            side = "على اليمين" if (z.rect[0] + z.rect[2]) / 2 > W / 2 else "على اليسار"
            if zk == "rail":
                where = f"{_ZONE_AR['rail']} {plat} {side}"
            elif zk == "side":
                where = f"{_ZONE_AR['side']} {side} في {plat}"
            else:
                where = f"{_ZONE_AR[zk]} في {plat}"
            community = z.basis == "community"
            text = f"{label} داخل {where} ({_ar(depth)} بكسل)" + (" — تقدير غير رسمي" if community else "")
            out.append({"box": bid, "kind": "zone", "zone": z.name, "platform": z.platform, "severity": _severity(kind, total, 1, area),
                        "overlap_w": math.ceil(ow), "overlap_h": math.ceil(oh), "overlap_px": math.ceil(ow * oh),
                        "community": community, "text": text})
        if fr:
            o = _overlap(r, fr)
            if o:
                ow, oh = o
                out.append({"box": bid, "kind": "face", "zone": "face", "platform": profile.name,
                            "severity": _severity(kind, min(area, ow * oh + total), 1, area), "overlap_w": math.ceil(ow),
                            "overlap_h": math.ceil(oh), "overlap_px": math.ceil(ow * oh), "community": False,
                            "text": f"{label} يغطي الوجه ({_ar(min(ow, oh))} بكسل)"})
    return out


def safe_area_for(profile=None, frame=None, *, path=None) -> dict:
    """The {left, right, top, bottom} margins (px) captions and previews keep clear of: today's subtitle-style.json
    numbers when no profile is chosen or the file is unreadable, else the chosen profile's safe text scaled to `frame`."""
    if profile in (None, "") or profile == []:
        return legacy_safe_area()
    names = list(profile) if isinstance(profile, (list, tuple)) else [profile]
    known = read_profiles(path)[0]
    if not any(_key(n) in known for n in names):         # a typo must not move the margins: today's numbers stay
        return legacy_safe_area()
    p = union(names, frame=frame, path=path)
    if p.fallback:
        return legacy_safe_area()
    W, H = p.frame
    s = p.safe_text
    return {"left": s[0], "right": W - s[2], "top": s[1], "bottom": H - s[3]}


def safe_top_px_for(profile=None, frame=None, *, path=None):
    """What previews.SAFE_TOP_PX is today (220, not scaled) when no profile is chosen or the file is unreadable, else
    the top of the chosen profile's safe text at `frame`."""
    if profile in (None, ""):
        return legacy_safe_top_px()
    if _key(profile) not in read_profiles(path)[0]:
        return legacy_safe_top_px()
    p = load(profile, frame=frame, path=path)
    return legacy_safe_top_px() if p.fallback else p.safe_text[1]


# --------------------------------------------------------------------------- QC helper (qc.py calls this)
QC_OK = "Graphics clear of platform app areas"
QC_P1 = "Text clear of platform app areas (P1)"
QC_P2 = "Graphics clear of platform app areas (P2: decorative)"
QC_UNKNOWN = "Platform app areas: a platform name is not known"


def qc_items(boxes, platforms, frame=None, *, rtl=False, face=None, path=None) -> list:
    """The QC lines for a reel's target platform(s): [] when none is chosen (QC output stays as it is today). A
    multi-platform reel is checked against the union of its profiles. One line per severity: {name, ok, detail}; a
    clean reel gets one passing line. P1 = text (or a shape under the shared-area rule), P2 = decorative < 20 %."""
    if isinstance(platforms, str):
        platforms = [platforms] if platforms.strip() else []
    if not platforms:
        return []
    try:
        prof = union(list(platforms), frame=frame, rtl=rtl, path=path)
        found = violations(boxes, prof, face=face)
    except Exception:  # noqa: BLE001  G10: a check that cannot run is no finding
        return []
    out = []
    for sev, name in (("P1", QC_P1), ("P2", QC_P2)):
        hit = [f for f in found if f["severity"] == sev]
        if hit:
            texts = list(dict.fromkeys(f["text"] for f in hit))
            out.append({"name": name, "ok": False, "detail": "؛ ".join([*texts[:5], *prof.gaps]) + (f" (+{len(texts) - 5})" if len(texts) > 5 else "")})
    if prof.fallback_reason and "unknown profile" in prof.fallback_reason:
        out.append({"name": QC_UNKNOWN, "ok": False,
                    "detail": "اسم منصة غير معروف في قائمة المنصات: " + prof.fallback_reason.replace("unknown profile", "").strip()})
    if not out:
        out.append({"name": QC_OK, "ok": True, "detail": "؛ ".join([prof.platform_ar or prof.name, *prof.gaps])})
    return out


# --------------------------------------------------------------------------- delivery-encode check
_PROFILE_RANK = {"baseline": 0, "constrained baseline": 0, "main": 1, "extended": 2, "high": 3, "high 10": 4,
                 "high 4:2:2": 5, "high 4:4:4 predictive": 6}
_CODEC_ALIAS = {"avc": "h264", "avc1": "h264", "h.264": "h264", "h265": "hevc", "h.265": "hevc", "hvc1": "hevc"}


def _codec(v):
    s = str(v).strip().lower()
    return _CODEC_ALIAS.get(s, s)


def _level(v):
    """H.264 level as a number: ffprobe's 41 -> 4.1, "5.1" -> 5.1."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or x <= 0:
        return None
    return x / 10 if x >= 10 else x


def encode_findings(media_info, profile) -> list:
    """Compare an exported file's measured values (see probe_media) with the profile's encode block. Only values the
    platform publishes (present in the block) and the file measured (not None) are checked. Each finding is
    {check, text (plain Arabic), severity "advisory"}; loudness findings add delta_db."""
    enc = profile.encode if isinstance(profile, Profile) else None
    if not enc or not isinstance(media_info, dict):
        return []
    plat = profile.platform_ar or profile.name
    m = media_info
    f = []

    def add(check, text, **extra):
        f.append({"check": check, "text": text, "severity": "advisory", **extra})

    if "codec" in enc and m.get("codec"):
        allowed = [enc["codec"]] if isinstance(enc["codec"], str) else list(enc["codec"])
        if _codec(m["codec"]) not in {_codec(a) for a in allowed}:
            add("codec", f"ترميز الفيديو ({m['codec']}) غير مناسب لـ{plat}: المطلوب {' أو '.join(allowed)}")
    if "profile" in enc and isinstance(m.get("profile"), str):
        got, lim = _PROFILE_RANK.get(m["profile"].strip().lower()), _PROFILE_RANK.get(str(enc["profile"]).strip().lower())
        if got is not None and lim is not None and got > lim:
            add("profile", f"بروفايل الترميز ({m['profile']}) أعلى من المسموح لـ{plat} ({enc['profile']})")
    if "level_max" in enc and _codec(m.get("codec") or "h264") == "h264":      # HEVC levels use another scale
        got, lim = _level(m.get("level")), _level(enc["level_max"])
        if got is not None and lim is not None and got > lim + 1e-9:
            add("level_max", f"مستوى الترميز ({_ar(got)}) أعلى من المسموح لـ{plat} ({_ar(lim)})")
    if "gop_s" in enc and _num(m.get("gop_s")) and _num(enc["gop_s"]) and m["gop_s"] > enc["gop_s"] + 1e-6:
        add("gop_s", f"المسافة بين الإطارات المفتاحية (GOP) {_ar(m['gop_s'])} ثانية، والمسموح لـ{plat} {_ar(enc['gop_s'])}")
    if enc.get("closed_gop") is True and m.get("closed_gop") is False:
        add("closed_gop", f"الملف بـ GOP مفتوح، و{plat} يطلب GOP مغلقًا (كل مجموعة تبدأ بإطار IDR)")
    if "pix_fmt" in enc and isinstance(m.get("pix_fmt"), str) and m["pix_fmt"] != enc["pix_fmt"]:
        add("pix_fmt", f"تنسيق البكسل ({m['pix_fmt']}) غير المطلوب لـ{plat} ({enc['pix_fmt']})")
    if "audio" in enc and isinstance(m.get("audio_codec"), str) and m["audio_codec"].lower() != str(enc["audio"]).lower():
        add("audio", f"ترميز الصوت ({m['audio_codec']}) غير المطلوب لـ{plat} ({enc['audio']})")
    for key, mkey, bad, word in (("audio_sample_rate_max", "sample_rate", lambda g, l: g > l, "معدل عينات الصوت أعلى من حد"),
                                 ("audio_channels_max", "channels", lambda g, l: g > l, "عدد قنوات الصوت أكبر من حد"),
                                 ("audio_bitrate_kbps_min", "audio_bitrate_kbps", lambda g, l: g < l, "معدل بيانات الصوت أقل من حد"),
                                 ("bitrate_kbps_min", "bitrate_kbps", lambda g, l: g < l, "معدل بيانات الفيديو أقل من حد"),
                                 ("fps_min", "fps", lambda g, l: g < l - 0.1, "عدد الإطارات في الثانية أقل من حد"),
                                 ("fps_max", "fps", lambda g, l: g > l + 0.1, "عدد الإطارات في الثانية أكبر من حد")):
        if key in enc and _num(enc[key]) and _num(m.get(mkey)) and bad(m[mkey], enc[key]):
            add(key, f"{word} {plat} ({_ar(enc[key])})")
    if "container" in enc and isinstance(m.get("container"), str):
        allowed = [enc["container"]] if isinstance(enc["container"], str) else list(enc["container"])
        names = {c.strip().lower() for c in m["container"].split(",")}
        if not names & {a.lower() for a in allowed}:
            add("container", f"حاوية الملف ({m['container']}) غير مناسبة لـ{plat}: المطلوب {' أو '.join(allowed)}")
    if _num(enc.get("loudness_lufs")) and _num(m.get("loudness_lufs")):
        d = m["loudness_lufs"] - enc["loudness_lufs"]
        if d > LOUDNESS_TOLERANCE_LU:
            add("loudness_lufs", f"الصوت أعلى من المطلوب لـ{plat} بـ {_ar(d)} ديسيبل", delta_db=round(d, 1))
    if _num(enc.get("true_peak_dbtp")) and _num(m.get("true_peak_dbtp")):
        d = m["true_peak_dbtp"] - enc["true_peak_dbtp"]
        if d > 0:
            add("true_peak_dbtp", f"ذروة الصوت أعلى من الحد المسموح لـ{plat} بـ {_ar(d)} ديسيبل", delta_db=round(d, 1))
    return f


# --------------------------------------------------------------------------- probes (parsers are pure; probe_media runs the tools)
def parse_ffprobe_streams(d) -> dict:
    """codec, profile, level, pix_fmt, size, fps and the audio format from `ffprobe -show_streams -of json`."""
    if not isinstance(d, dict) or not isinstance(d.get("streams"), list):
        return {}
    out = {}
    for s in d["streams"]:
        if not isinstance(s, dict):
            continue
        if s.get("codec_type") == "video" and "codec" not in out:
            out.update(codec=s.get("codec_name"), profile=s.get("profile"), level=s.get("level"), pix_fmt=s.get("pix_fmt"),
                       width=s.get("width"), height=s.get("height"))
            for key in ("avg_frame_rate", "r_frame_rate"):      # avg first: r_frame_rate of a variable-rate clip is 1000/1 or more
                m = re.fullmatch(r"(\d+)/(\d+)", str(s.get(key, "")))
                if m and int(m.group(2)) and 0 < int(m.group(1)) / int(m.group(2)) <= 480:
                    out["fps"] = int(m.group(1)) / int(m.group(2))
                    break
            if _kbps(s.get("bit_rate")) is not None:
                out["bitrate_kbps"] = _kbps(s.get("bit_rate"))
        elif s.get("codec_type") == "audio" and "audio_codec" not in out:
            out["audio_codec"] = s.get("codec_name")
            if _kbps(s.get("bit_rate")) is not None:
                out["audio_bitrate_kbps"] = _kbps(s.get("bit_rate"))
            try:
                out["sample_rate"] = int(s.get("sample_rate"))
            except (TypeError, ValueError):
                pass
            if _int(s.get("channels")):
                out["channels"] = s["channels"]
    fmt = d.get("format")
    if isinstance(fmt, dict):
        if isinstance(fmt.get("format_name"), str):
            out["container"] = fmt["format_name"]
        if "bitrate_kbps" not in out and _kbps(fmt.get("bit_rate")) is not None:
            out["bitrate_kbps"] = _kbps(fmt.get("bit_rate"))      # whole-file rate when the video stream states none
    return {k: v for k, v in out.items() if v is not None}


def _kbps(v):
    try:
        x = float(v) / 1000
    except (TypeError, ValueError):
        return None
    return round(x, 1) if math.isfinite(x) and x > 0 else None


def gop_seconds_from_packets(packets):
    """The longest gap between keyframes (K flag) from `ffprobe -show_packets`; None when fewer than two are readable."""
    ts = []
    for p in packets if isinstance(packets, list) else []:
        if not isinstance(p, dict) or "K" not in str(p.get("flags", "")):
            continue
        try:
            t = float(p.get("pts_time"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(t):
            ts.append(t)
    ts.sort()
    return round(max(b - a for a, b in zip(ts, ts[1:])), 3) if len(ts) >= 2 else None


_IDR_TYPES = {5, 19, 20}          # H.264 IDR slice; HEVC IDR_W_RADL / IDR_N_LP
_NAL = re.compile(r"nal_unit_type\s+[01]+\s*=\s*(\d+)")


def closed_gop_from_trace(text):
    """True when every keyframe packet carries an IDR NAL unit, False when one does not (an open GOP), None when the
    trace_headers log has nothing to judge. `text` is the log of `-bsf:v trace_headers` on a stream copy. Only packets
    the muxer flags as key frames are judged: an open-GOP I-frame that is not flagged would not be seen."""
    if not isinstance(text, str):
        return None
    seen = False
    for chunk in re.split(r"Packet:", text)[1:]:
        head = chunk.split("\n", 1)[0]
        if "key frame" not in head:
            continue
        nals = {int(n) for n in _NAL.findall(chunk)}
        if not nals:
            continue
        seen = True
        if not nals & _IDR_TYPES:
            return False
    return True if seen else None


def parse_ebur128(text) -> dict:
    """Integrated loudness and true peak from the summary of FFmpeg's ebur128 filter (peak=true)."""
    if not isinstance(text, str):
        return {}
    if "Summary:" not in text:             # a cut-off log would give a momentary value, not the integrated one
        return {}
    tail = text.rsplit("Summary:", 1)[-1]
    out = {}
    m = re.search(r"\bI:\s+(-?\d+(?:\.\d+)?)\s+LUFS", tail)
    if m:
        out["loudness_lufs"] = float(m.group(1))
    m = re.search(r"True peak:\s*Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS", tail)
    if m and "loudness_lufs" in out:
        out["true_peak_dbtp"] = float(m.group(1))
    return out if "loudness_lufs" in out else {}


def _default_runner(argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=kw.get("timeout", 300), check=False)


def probe_media(path, runner=None, ffmpeg=None, ffprobe=None, timeout=300) -> dict:
    """Measure an exported file for encode_findings: streams, keyframe gap, closed GOP (trace_headers on a stream copy,
    the first 120 s), loudness and true peak (ebur128). Fails open: a missing tool or a step that fails adds a note and
    the other values are still returned."""
    run = runner or _default_runner
    info, notes = {}, []
    ff, fp = ffmpeg, ffprobe
    if ff is None and runner is None:
        try:
            from .common import ffmpeg_exe
            ff = ffmpeg_exe()
        except Exception:  # noqa: BLE001
            ff = None
    ff = ff or "ffmpeg"
    if fp is None:
        import shutil
        sibling = Path(ff).with_name("ffprobe.exe" if str(ff).lower().endswith(".exe") else "ffprobe") if Path(ff).parent != Path(".") else None
        fp = str(sibling) if sibling is not None and sibling.is_file() else (shutil.which("ffprobe") or "ffprobe")   # never the current folder
    src = str(path)

    def go(label, argv):
        try:
            p = run(argv, timeout=timeout)
        except Exception as e:  # noqa: BLE001  FileNotFoundError, TimeoutExpired, OSError: the tool is advisory
            notes.append(f"{label}: {e.__class__.__name__}")
            return None
        if getattr(p, "returncode", 1) != 0:
            notes.append(f"{label}: the tool reported an error")
            return None
        return p

    p = go("streams", [fp, "-v", "error", "-show_streams", "-show_format", "-of", "json", src])
    if p is not None:
        try:
            info.update(parse_ffprobe_streams(json.loads(p.stdout)))
        except (ValueError, TypeError):
            notes.append("streams: unreadable output")
    p = go("keyframes", [fp, "-v", "error", "-select_streams", "v:0", "-show_packets", "-show_entries", "packet=pts_time,flags",
                         "-of", "json", src])
    if p is not None:
        try:
            g = gop_seconds_from_packets(json.loads(p.stdout).get("packets"))
        except (ValueError, TypeError, AttributeError):
            g = None
            notes.append("keyframes: unreadable output")
        if g is not None:
            info["gop_s"] = g
    p = go("closed GOP", [ff, "-v", "trace", "-t", "120", "-i", src, "-map", "0:v:0", "-c", "copy", "-bsf:v", "trace_headers",
                          "-f", "null", "-"])
    if p is not None:
        c = closed_gop_from_trace((p.stderr or "") + (p.stdout or ""))
        if c is not None:
            info["closed_gop"] = c
    p = go("loudness", [ff, "-nostats", "-i", src, "-map", "0:a:0", "-filter:a", "ebur128=peak=true", "-f", "null", "-"])
    if p is not None:
        info.update(parse_ebur128((p.stderr or "") + (p.stdout or "")))
    if notes:
        info["notes"] = notes
    return info
