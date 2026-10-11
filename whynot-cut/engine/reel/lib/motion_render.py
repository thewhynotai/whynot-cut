"""Render a built motion project (`reel motion-render`, spec §4.9) and pull QC frames from it (`reel motion-frames`,
spec §4.10).

aerender renders MAIN_<id> from the SAVED .aep in its own AE instance (the editor's After Effects is untouched); the
master is probed against the plan, then ffmpeg makes the posting MP4 and the cover. Frames come from the newest render
(scene pieces win for their ranges) at every scene's hero frame, reveal midpoints, transition midpoints and caption
samples, each with what it should show.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .common import ffmpeg_exe, now_iso, read_json, run, write_json

RESULT = "04_after_effects/motion-render-result.json"


def _templates() -> tuple[str, str]:
    from .ae_probe import capabilities
    from .motion_config import motion_cfg
    r = motion_cfg().get("render") or {}
    caps = (capabilities() or {}).get("measured") or {}
    return r.get("rs_template", "Best Settings"), caps.get("om_template") or r.get("om_template", "High Quality")


def _probe(f: Path) -> dict:
    from .media import probe
    pr = probe(f)
    v = pr.get("video") or {}
    return {"w": v.get("display_width"), "h": v.get("display_height"), "fps": v.get("fps"),
            "duration_s": pr.get("duration_s"), "audio": bool(pr.get("audio"))}


def render(paths, scenes: list[str] | None = None, timeout: int = 3600) -> dict:
    from . import ae_render
    from .audio_clean import _lufs
    from .common import load_status, set_status
    from .motion_audio import mix
    from .motion_build import aep_path, render_path
    plan = read_json(paths.p("01_analysis/motion-plan.json"))
    aep = aep_path(paths)
    if not plan or not aep.exists():
        raise SystemExit("build the After Effects project first (`reel motion-build`)")
    rs, om = _templates()
    comp = "MAIN_" + plan["reel_id"]
    fps = float(plan["fps"])
    log = paths.p("logs/aerender.log")
    res = {"status": "FAILED", "reasons": [], "warnings": [], "main": None, "pieces": [], "mp4": None, "cover": None,
           "probe": None, "templates": [rs, om], "at": now_iso()}
    if scenes:
        prior = read_json(paths.p(RESULT), {}) or {}
        pieces = [p for p in prior.get("pieces", []) if p["scene"] not in scenes]
        by_id = {s["id"]: s for s in plan["scenes"]}
        for sid in scenes:
            sc = by_id.get(sid)
            if not sc:
                raise SystemExit(f"unknown scene {sid}")
            out = paths.p(f"04_after_effects/render/pieces/{paths.video_id}_{sid}.mov")
            out.unlink(missing_ok=True)
            end = min(plan["duration_frames"], sc["end_frame"]) - 1
            r = ae_render.render(aep, comp, out, rs, om, sc["start_frame"], end, timeout=timeout, log=log)
            if r["status"] != "RENDERED":
                res["reasons"].append(f"{sid}: aerender {r['status']} (see {log})")
                continue
            pieces.append({"scene": sid, "file": str(out), "start_frame": sc["start_frame"], "end_frame": end,
                           "rendered_at": time.time()})
        res.update(status="RENDERED" if not res["reasons"] else "FAILED", pieces=pieces,
                   main=(read_json(paths.p(RESULT), {}) or {}).get("main"))
        write_json(paths.p(RESULT), res)
        return res
    main = render_path(paths)
    main.unlink(missing_ok=True)
    r = ae_render.render(aep, comp, main, rs, om, timeout=timeout, log=log)
    if r["status"] != "RENDERED":
        res["reasons"].append(f"aerender {r['status']}: {r.get('msg') or 'see ' + str(log)}")
        write_json(paths.p(RESULT), res)
        return res
    pr = _probe(main)
    res.update(main=str(main), probe=pr)
    want = plan["duration_frames"] / fps
    if (pr["w"], pr["h"]) != (plan["w"], plan["h"]):
        res["reasons"].append(f"size {pr['w']}x{pr['h']}, plan {plan['w']}x{plan['h']}")
    if pr["fps"] and abs(float(pr["fps"]) - fps) > 0.01:
        res["reasons"].append(f"fps {pr['fps']}, plan {fps:.3f}")
    if pr["duration_s"] is None or abs(pr["duration_s"] - want) > 1.5 / fps:
        res["reasons"].append(f"duration {pr['duration_s']} s, plan {want:.3f} s (±1 frame)")
    mp4 = paths.p(f"04_after_effects/render/{paths.video_id}_motion.mp4")
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(main)]
    if not pr["audio"]:
        wav = mix(plan, paths.root, paths.p("04_after_effects/render/_mix.wav"))
        cmd += ["-i", str(wav), "-map", "0:v:0", "-map", "1:a:0"]
        res["warnings"].append("the After Effects render has no audio stream: the MP4 carries the engine's mix")
    cmd += ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", "-t", f"{want:.3f}", str(mp4)]
    p = run(cmd, check=False)
    if p.returncode or not mp4.exists():
        res["reasons"].append(f"MP4 encode failed: {(p.stderr or '')[-200:]}")
    else:
        res["mp4"] = str(mp4)
        lufs = _lufs(mp4)
        res["lufs"] = lufs
        if lufs is not None and abs(lufs + 14) > 1:
            res["warnings"].append(f"loudness {lufs:.1f} LUFS (target -14 ±1)")
    hero = plan["scenes"][0]["hero_frame"]
    cov = ae_render.extract_frames(main, [hero], fps, mp4.parent, [f"{paths.video_id}_cover.png"])
    if cov:
        from PIL import Image
        jpg = mp4.parent / f"{paths.video_id}_cover.jpg"
        Image.open(cov[0]).convert("RGB").save(jpg, quality=92)
        cov[0].unlink(missing_ok=True)
        res["cover"] = str(jpg)
    res["status"] = "RENDERED" if not res["reasons"] else "FAILED"
    res["pieces"] = []
    write_json(paths.p(RESULT), res)
    if res["status"] == "RENDERED":
        set_status(paths, load_status(paths).get("status") or "PROJECT_ASSEMBLED", "rendered with aerender",
                   "motion_render", [str(main), str(mp4)])
    return res


def frame_points(plan: dict) -> list[dict]:
    pts = []
    cap_cues = ((plan.get("persistent") or {}).get("captions") or {}).get("cues") or []
    for sc in plan["scenes"]:
        texts = [e for e in sc["elements"] if e.get("kind") in ("text", "counter")]
        toks = [t for e in texts for t in (e.get("tokens") or [])]
        items = [e for e in sc["elements"] if e.get("reveal") == "item"]

        def expect(f):
            return {"lines": [ln for e in texts for ln in (e.get("lines") or [e.get("text", "")])
                              if (e.get("appear_frame") is None or e["appear_frame"] <= f)],
                    "emphasis": [e["tokens"][k - 1]["text"] for e in texts for k in (e.get("emphasis") or [])
                                 if e.get("tokens") and k - 1 < len(e["tokens"])],
                    "icon": [e.get("icon") for e in sc["elements"] if e.get("kind") == "icon"],
                    "revealed_tokens": len([t for t in toks if t["cue_frame"] <= f]),
                    "revealed_items": len([e for e in items if e.get("appear_frame", 0) <= f])}
        pts.append({"frame": sc["hero_frame"], "scene": sc["id"], "type": sc["type"], "kind": "hero",
                    "expect": expect(sc["hero_frame"])})
        cues = sorted({t["cue_frame"] for t in toks if t.get("text")} if sc["type"] in ("kinetic_quote", "quote_card")
                      else {e["appear_frame"] for e in items})
        if len(cues) >= 2 and cues[-1] > cues[0]:
            mid = (cues[0] + cues[-1]) // 2
            if mid in cues and mid < cues[-1]:
                mid += 1
            pts.append({"frame": mid, "scene": sc["id"], "type": sc["type"], "kind": "reveal_mid", "expect": expect(mid)})
        n = sc["transition_in"]["frames"]
        if n > 0:
            f = sc["start_frame"] + n // 2
            pts.append({"frame": f, "scene": sc["id"], "type": sc["type"], "kind": "transition_mid",
                        "expect": {"transition": sc["transition_in"]["type"]}})
    if cap_cues:
        picks = sorted({0, len(cap_cues) // 2, len(cap_cues) - 1})
        for k in picks:
            c = cap_cues[k]
            f = (c["start_frame"] + c["end_frame"]) // 2
            sc = next((s for s in plan["scenes"] if s["start_frame"] <= f < s["end_frame"]), plan["scenes"][-1])
            pts.append({"frame": f, "scene": sc["id"], "type": sc["type"], "kind": "caption", "expect": {"caption": c["text"]}})
    seen, out = set(), []
    for p in sorted(pts, key=lambda p: (p["frame"], p["kind"])):
        key = (p["frame"], p["kind"], p["scene"])
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def frames(paths) -> dict:
    from PIL import Image, ImageDraw
    from . import ae_render
    plan = read_json(paths.p("01_analysis/motion-plan.json"))
    res = read_json(paths.p(RESULT), {}) or {}
    main = res.get("main")
    if not plan or not main or not Path(main).exists():
        raise SystemExit("render first (`reel motion-render`)")
    fps = float(plan["fps"])
    pts = frame_points(plan)
    od = paths.p(f"08_quality_control/ae_frames/run-{time.strftime('%Y%m%d-%H%M%S')}")
    od.mkdir(parents=True, exist_ok=True)
    main_t = Path(main).stat().st_mtime
    pieces = [p for p in res.get("pieces", []) if Path(p["file"]).exists() and Path(p["file"]).stat().st_mtime >= main_t]
    recs, missing = [], []
    for k, p in enumerate(pts, 1):
        name = f"F{k:03d}_{p['scene']}_{p['kind']}.png"
        src, f = Path(main), p["frame"]
        piece = next((q for q in pieces if q["start_frame"] <= f <= q["end_frame"]), None)
        if piece:
            src, f = Path(piece["file"]), f - piece["start_frame"]
        got = ae_render.extract_frames(src, [f], fps, od, [name])
        if got:
            recs.append(dict(p, file=name, source=src.name))
        else:
            missing.append(name)
    write_json(od / "frames.json", {"plan_fingerprint": plan.get("fingerprint"), "render": main, "frames": recs,
                                    "missing": missing, "generated": now_iso()})
    sheet = None
    if recs:
        tw = 270
        im0 = Image.open(od / recs[0]["file"])
        th = int(round(im0.height * tw / im0.width))
        cols = 4
        rows = math.ceil(len(recs) / cols)
        sh = Image.new("RGB", (cols * tw, rows * (th + 30)), "black")
        dr = ImageDraw.Draw(sh)
        for i, rc in enumerate(recs):
            x, y = (i % cols) * tw, (i // cols) * (th + 30)
            sh.paste(Image.open(od / rc["file"]).convert("RGB").resize((tw, th)), (x, y + 30))
            dr.text((x + 4, y + 4), f"{rc['file'][:4]} {rc['scene']} {rc['kind']} f{rc['frame']}", fill="yellow")
            if rc["kind"] == "reveal_mid":
                dr.text((x + 4, y + 16), f"{rc['expect']['revealed_tokens'] or rc['expect']['revealed_items']} shown",
                        fill="white")
        sheet = od / "_sheet.jpg"
        sh.save(sheet, quality=88)
    return {"dir": str(od), "frames": len(recs), "expected": len(pts), "missing": missing,
            "sheet": str(sheet) if sheet else None}
