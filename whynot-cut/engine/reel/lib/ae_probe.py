"""Arabic capability probe for After Effects (`reel ae-probe`).

Builds a small probe project through the bridge (Arabic text with the Universal composer and RTL direction, a
word-synced reveal, a per-word emphasis, a mixed Arabic/Latin/digits line, the brand font, an icon from path data),
reads back what AE kept, renders all probe comps with aerender and pulls frames. Claude views the frames and records the
verdict (`--record ok|fail --word-order logical|visual`); `motion-build` refuses until this AE version has an ok verdict.
The measured capabilities choose the motion library's fallbacks (spec §4.6).
"""
from __future__ import annotations

from pathlib import Path

from .common import ENV_DIR, now_iso, read_json, write_json
from . import plat

PROBE_DIR = ENV_DIR / "ae-probe"
CAPS = ENV_DIR / "ae-capabilities.json"
DEFAULT_FONTS = {"headline": "ArialMT"} if plat.IS_WIN else {"headline": "GeezaPro"}
W, H, FPS, FRAMES = 1080, 1920, 30, 90
CHECK_MARK = [{"vertices": [[-40, 0], [-12, 28], [44, -30]], "inTangents": [[0, 0], [0, 0], [0, 0]],
               "outTangents": [[0, 0], [0, 0], [0, 0]], "closed": False}]
# frames to look at, per comp (comp-local); every comp lies end to end in PROBE_ALL, 90 frames each
LOOK = {"arabic_rtl": [75], "word_reveal": [20, 65], "emphasis": [75], "mixed": [75], "brand_font": [75], "icon": [75]}


def probe_job(fonts: dict[str, str]) -> dict:
    head = (fonts or {}).get("headline") or DEFAULT_FONTS["headline"]
    base = {"font": head, "size": 96}
    comps = [
        dict(base, name="arabic_rtl", text="مرحبا بكم في البودكاست"),
        dict(base, name="word_reveal", text="واحد اتنين تلاتة اربعة", cues=[15, 30, 45, 60]),
        dict(base, name="emphasis", text="دي اهم نقطة في الكلام", emphasis=[3]),
        dict(base, name="mixed", text="الـ Isotretinoin ٣ مرات 25%"),
        dict(base, name="brand_font", text="خط البراند"),
        {"name": "icon", "shapes": CHECK_MARK, "stroke": 10},
    ]
    return {"aep_path": str(PROBE_DIR / "probe.aep"), "w": W, "h": H, "fps": FPS, "frames": FRAMES,
            "fonts": {"headline": head}, "comps": comps}


def capabilities_from(readback: dict, om_pref: str) -> dict:
    comps = {c.get("name"): c for c in readback.get("comps", [])}
    ar = comps.get("arabic_rtl", {})
    if ar.get("direction_textdocument") == "RTL":
        rtl = "textdocument"
    elif ar.get("direction_paragraph_range") == "RTL":
        rtl = "paragraph_range"
    else:
        rtl = False
    bf = comps.get("brand_font", {})
    templates = list(readback.get("om_templates") or [])
    om = om_pref if om_pref in templates else next(
        (t for key in ("ProRes", "Lossless") for t in templates if key in t), templates[0] if templates else om_pref)
    return {"composer_universal": ar.get("composer") == "UNIVERSAL", "rtl_direction": rtl,
            "fontobject": bool(bf.get("ok", True)) and not bf.get("substitute")
            and bf.get("font_ps") == bf.get("requested_ps", bf.get("font_ps")),
            "emphasis_animator": bool(comps.get("emphasis", {}).get("ok")), "om_template": om, "templates": templates}


def look_points() -> list[tuple[str, int]]:
    """(name, frame in PROBE_ALL) for every frame Claude must view."""
    order = ["arabic_rtl", "word_reveal", "emphasis", "mixed", "brand_font", "icon"]
    return [(f"{n}_{f:02d}", k * FRAMES + f) for k, n in enumerate(order) for f in LOOK[n]]


def run_probe(fonts: dict | None = None, timeout: int = 600) -> dict:
    from . import ae_bridge, ae_render
    PROBE_DIR.mkdir(parents=True, exist_ok=True)            # ExtendScript never creates folders itself
    job = probe_job(fonts or DEFAULT_FONTS)
    r = ae_bridge.submit("probe_text", {"job": job}, timeout=timeout)
    if not r.get("ok"):
        return {"ok": False, "step": "probe_text", "bridge": r}
    rb = (r.get("response") or {}).get("result") or {}
    caps = capabilities_from(rb, "High Quality")
    mov = PROBE_DIR / "probe_all.mov"
    rend = ae_render.render(Path(job["aep_path"]), "PROBE_ALL", mov, "Best Settings", caps["om_template"],
                            timeout=timeout, log=PROBE_DIR / "aerender.log")
    frames = []
    if rend["status"] == "RENDERED":
        pts = look_points()
        frames = [str(p) for p in ae_render.extract_frames(mov, [f for _, f in pts], FPS, PROBE_DIR / "frames",
                                                          [f"{n}.png" for n, _ in pts])]
    rec = {"ae_version": rb.get("ae_version"), "measured": caps, "readback": rb, "render": rend, "frames": frames,
           "word_index_logical": None, "verdict": None, "probed_at": now_iso(),
           "look_for": "joined Arabic letters; words right-to-left; word_reveal_20 shows only the first word واحد "
                       "(on the right); emphasis on the 3rd word; mixed line keeps 'الـ Isotretinoin' together; "
                       "brand font; icon drawn"}
    write_json(CAPS, rec)
    return dict(rec, ok=rend["status"] == "RENDERED" and bool(frames),
                next="VIEW every frame, then `reel ae-probe --record ok|fail --word-order logical|visual --notes …`")


def record(verdict: str, notes: str, word_order: str) -> dict:
    if verdict not in ("ok", "fail"):
        raise ValueError("verdict must be ok or fail")
    if word_order not in ("logical", "visual"):
        raise ValueError("word order must be logical or visual")
    rec = read_json(CAPS)
    if not rec or not rec.get("ae_version"):
        raise SystemExit("no probe to record: run `reel ae-probe` first")
    rec.update(verdict=verdict, notes=notes, word_index_logical=word_order == "logical", recorded_at=now_iso())
    write_json(CAPS, rec)
    return rec


def capabilities() -> dict:
    return read_json(CAPS, {}) or {}


def verdict_ok(ae_version: str) -> bool:
    rec = capabilities()
    return rec.get("verdict") == "ok" and bool(ae_version) and rec.get("ae_version") == ae_version
