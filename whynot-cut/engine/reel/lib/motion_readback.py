"""Compare what After Effects built (the bridge's `readback`) with the compiled motion plan (spec §4.8)."""
from __future__ import annotations

from .plan import norm

TOL = 4          # px of tolerance for safe-area edges


def _overlap(a: list, b: list) -> float:
    """Intersection area / smaller box area."""
    x = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    y = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    small = min(a[2] * a[3], b[2] * b[3]) or 1
    return x * y / small


def compare(plan: dict, rb: dict, fmt: dict, caps: dict) -> dict:
    fails, warns = [], []
    w, h, s = fmt["w"], fmt["h"], fmt["safe"]
    by_id = {x.get("id"): x for x in rb.get("scenes") or []}
    cap = (plan.get("persistent") or {}).get("captions") or {}
    band = (cap["y"] - cap["size"] * 1.4, cap["y"] + cap["size"] * 1.4) if cap.get("cues") else None
    for sc in plan["scenes"]:
        got = by_id.get(sc["id"])
        if not got:
            fails.append(f"{sc['id']}: scene comp {sc['id']}_{sc['type']} missing in After Effects")
            continue
        if got.get("in_frame") != sc["start_frame"]:
            fails.append(f"{sc['id']}: starts at frame {got.get('in_frame')} in MAIN, plan says {sc['start_frame']}")
        want_out = sc.get("layer_out_frame", sc["end_frame"])
        if got.get("out_frame") != want_out:
            fails.append(f"{sc['id']}: ends at frame {got.get('out_frame')} in MAIN, plan says {want_out}")
        layers = {L.get("name"): L for L in got.get("layers") or []}
        boxes = []
        for el in sc["elements"]:
            if el.get("kind") not in ("text", "counter"):
                continue
            L = layers.get(el["name"])
            if not L:
                fails.append(f"{sc['id']}: text layer {el['name']} missing")
                continue
            if el["kind"] == "text" and norm(str(L.get("text", "")).replace("\r", " ")) != norm(el["text"].replace("\r", " ")):
                fails.append(f"{el['name']}: AE shows «{str(L.get('text', ''))[:40]}», plan says «{el['text'][:40]}»")
            if L.get("font_ps") != el.get("font_ps"):
                fails.append(f"{el['name']}: font {L.get('font_ps')!r} instead of {el.get('font_ps')!r} (install the brand font)")
            if L.get("substitute"):
                fails.append(f"{el['name']}: AE substituted the font {el.get('font_ps')!r} (not installed)")
            if el.get("rtl"):
                if L.get("composer") != "UNIVERSAL":
                    fails.append(f"{el['name']}: composer {L.get('composer')!r}, Arabic needs the Universal (Middle Eastern) composer")
                if caps.get("rtl_direction") is not False and "RTL" not in (L.get("direction"), L.get("direction_pr")):
                    fails.append(f"{el['name']}: paragraph direction is not right-to-left")
            if el.get("cue_hash") and L.get("comment") != el["cue_hash"]:
                fails.append(f"{el['name']}: word cues differ from the plan (cue hash)")
            r = L.get("rect")
            if r:
                l, t, rw, rh = r
                if l < s["side"] - TOL or l + rw > w - s["side"] + TOL or t < s["top"] - TOL or t + rh > h - s["bottom"] + TOL:
                    fails.append(f"{el['name']}: box {[round(v) for v in r]} leaves the safe area")
                if band and sc["type"] not in ("kinetic_quote", "quote_card") and t < band[1] and t + rh > band[0]:
                    warns.append(f"{el['name']}: box overlaps the caption band")
                boxes.append((el["name"], r))
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if _overlap(boxes[i][1], boxes[j][1]) > 0.05:
                    fails.append(f"{sc['id']}: {boxes[i][0]} overlaps {boxes[j][0]}")
    for ps in rb.get("missing_or_substituted") or []:
        fails.append(f"After Effects reports a missing/substituted font: {ps}")
    return {"ok": not fails, "failures": fails, "warnings": warns}
