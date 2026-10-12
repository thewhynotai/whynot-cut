"""After Effects: generate a self-contained build JSX from timeline-spec.json, optionally run it
in the installed After Effects (macOS AppleScript / Windows AfterFX.exe -r), then render the queue with aerender.

Honesty rules: a JSX that was not executed is reported as SCRIPT_ONLY; an .aep is reported only
if the file exists after execution; renders only if the .mov files exist and probe correctly.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .common import (seq_fps, caption_hide_default, TEMPLATES_DIR, Paths, brand_fallback, font_role_fallback, project_prefix, load_config, log, now_iso, read_json, run, write_json, write_text)
from . import srt as srtlib
from .plan import norm, to_ms

RENDER_TEMPLATE = "High Quality with Alpha"  # AE default output module: QuickTime ProRes 4444 + alpha


def comp_fps() -> float:
    """The frame rate of the extras' comps: the profile's sequence rate (29.97 and 23.976 as After Effects names them,
    not 30000/1001 to six decimals), so the clip graphics line up with the Premiere sequence."""
    return round(seq_fps(), 3)


def wrap_lines(text: str, max_chars: int) -> str:
    """Balanced wrap for AE point text ('\\r' = AE line break). Uses the minimum number of lines
    that fit max_chars, then distributes words so lines are as even as possible (no orphans).
    Respects explicit newlines. Never splits a word (keeps Latin terms intact)."""
    out = []
    for para in text.replace("\\n", "\n").split("\n"):
        words = para.split()
        if not words:
            continue
        # greedy line count
        n, cur = 1, ""
        for w in words:
            cand = (cur + " " + w).strip()
            if len(cand) <= max_chars or not cur:
                cur = cand
            else:
                n, cur = n + 1, w
        out += _balance(words, n)
    return "\r".join(out)


def _balance(words: list, n: int) -> list:
    """Split words into n lines minimising the longest line (small DP; n, len(words) are tiny)."""
    if n <= 1:
        return [" ".join(words)]
    from functools import lru_cache
    L = len(words)

    def width(i, j):
        return len(" ".join(words[i:j]))

    @lru_cache(None)
    def best(i, k):
        if k == 1:
            return (width(i, L), (L,))
        res = None
        for j in range(i + 1, L - k + 2):
            sub = best(j, k - 1)
            cand = (max(width(i, j), sub[0]), (j,) + sub[1])
            if res is None or cand[0] < res[0]:
                res = cand
        return res
    cuts = best(0, min(n, L))[1]
    lines, i = [], 0
    for j in cuts:
        lines.append(" ".join(words[i:j]))
        i = j
    return lines


def brand_controls(db: Path) -> dict:
    tokens = read_json(db / "branding/brand-tokens.json", {})
    roles = tokens.get("roles", {})
    derived = tokens.get("derived", {})

    def rgbf(h):
        h = h.lstrip("#")
        return [round(int(h[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]
    teal = roles.get("primary", {}).get("hex", brand_fallback("primary"))
    white = roles.get("neutral_light", {}).get("hex", brand_fallback("neutral_light"))
    ctrls = [{"name": "Brand Teal", "rgb": rgbf(teal)}, {"name": "Brand White", "rgb": rgbf(white)},
             {"name": "Brand Paper", "rgb": rgbf(derived.get("paper_tint", {}).get("hex", brand_fallback("paper_tint")))},
             {"name": "Brand Ink", "rgb": rgbf(derived.get("ink", {}).get("hex", brand_fallback("ink")))}]
    official = ", ".join(c["hex"] for c in tokens.get("official_colors", []))
    return {"controls": ctrls, "official": official}


def fonts_map(db: Path) -> dict:
    typ = read_json(db / "branding/typography.json", {})
    roles = typ.get("roles", {})
    d = {"caption": "", "headline": "", "body": "", "term": "", "small": ""}
    d.update(font_role_fallback().get("postscript", {}))
    from .font_roles import resolve
    for k in d:
        spec = roles.get(k)
        face = resolve(typ, k, font_role_fallback().get("weights"))
        if isinstance(spec, dict) and spec.get("postscript_name"):
            d[k] = spec["postscript_name"]
        elif not d[k] or face["source"] == "typography.json roles":
            d[k] = face["ps"] or d[k]     # a role given only as a style, or not named at all: the shared resolver's face
    return d


def caption_data(paths: Paths, spec: dict, ed: dict) -> dict | None:
    srt_p = paths.p(spec.get("caption_source", "02_transcription/captions-short.srt"))
    if not srt_p.exists():
        return None
    style = ed.get("global", {}).get("caption_style", "keywords")
    hl = [norm(h["text"]) for h in spec.get("caption_highlights", [])]
    tpl = load_config("graphics-templates.json")["templates"]["highlight_caption"]
    from .common import ms_to_frame
    cues = []
    # captions are suppressed while a primary graphic carries the words (reference behaviour) or
    # a full-screen visual covers the speaker; plus explicit ranges from edit-decisions.global
    g = ed.get("global", {})
    hide_t = set(g.get("captions_hidden_during") or caption_hide_default())
    blocked = [(e["start_frame"], e["end_frame"]) for e in spec["events"] if e["template"] in hide_t]
    tm = spec.get("time_map")   # hidden ranges are authored in SOURCE time; events/captions are on the sequence clock
    if tm:
        from .timemap import TimeMap
        rm = TimeMap(tm["keep_ms"])
        blocked += [(rm.frame(to_ms(a)), rm.frame(to_ms(b))) for a, b in g.get("captions_hidden_ranges", [])]
    else:
        blocked += [(ms_to_frame(to_ms(a)), ms_to_frame(to_ms(b))) for a, b in g.get("captions_hidden_ranges", [])]
    for c in srtlib.read_srt(srt_p):
        sf, ef = ms_to_frame(c["start_ms"]), ms_to_frame(c["end_ms"])
        for a, b in blocked:
            if a <= sf < b:
                sf = b            # starts under a graphic -> push start to graphic end
            elif sf < a < ef:
                ef = a            # runs into a graphic -> cut at graphic start
        if ef - sf < 6:           # less than 0.25 s left -> drop
            continue
        is_hl = style == "highlight_all" or any(h and h in norm(c["text"]) for h in hl)
        cues.append({"text": c["text"].replace("\n", "\r"), "start_frame": sf, "end_frame": ef, "highlight": is_hl})
    return {"duration_frames": spec["duration_frames"], "cues": cues, "size": tpl["size"], "y": tpl["y"]}


def generate(paths: Paths) -> dict:
    spec = read_json(paths.p("01_analysis/timeline-spec.json"))
    ed = read_json(paths.p("01_analysis/edit-decisions.json"), {})
    if not spec:
        raise FileNotFoundError("timeline-spec.json missing — run plan first")
    tpls = load_config("graphics-templates.json")["templates"]
    manifest = read_json(paths.client_db / "asset-manifest.json", {"assets": []})
    by_rel = {a["rel"]: a for a in manifest["assets"]}
    logo = next((a for a in manifest["assets"] if a["category"] == "logo"), None)
    events = []
    for e in spec["events"]:
        e = json.loads(json.dumps(e))
        p = e["params"]
        if p.get("image"):
            a = by_rel.get(p["image"])
            p["image_path"] = (a.get("display_derivative") if a else str(paths.root / p["image"]))
        for key, mx in (("text", 26 if e["template"] in ("glass_card",) else 22), ("headline", 24)):
            if p.get(key) and e["template"] != "highlight_caption":
                p[key] = wrap_lines(p[key], p.get("max_chars", mx))
        events.append(e)
    render_dir = paths.p("04_after_effects/compositions")
    aep = paths.p(f"04_after_effects/project/{paths.video_id}_{project_prefix()}_GFX.aep")
    fps = comp_fps()
    warnings = []
    if spec.get("fps") and abs(float(spec["fps"]) - fps) > 0.01:
        warnings.append(f"the plan was compiled at {float(spec['fps']):.5g} fps but the profile is {fps:.5g} fps: the "
                        "comps use the profile rate, so run plan again before building")
    data = {"fps": fps, "brand": brand_controls(paths.client_db), "fonts": fonts_map(paths.client_db),
            "templates": tpls, "events": events, "captions": caption_data(paths, spec, ed),
            "logo": logo.get("display_derivative") if logo else None,
            "render_dir": str(render_dir), "aep_path": str(aep), "render_template": RENDER_TEMPLATE,
            "new_project": True, "generated": now_iso()}
    lib = (TEMPLATES_DIR / "after_effects/nh_ae_lib.jsx").read_text(encoding="utf-8")
    # ensure_ascii -> Arabic as \\uXXXX escapes: immune to ExtendScript file-encoding guessing
    js = ("// AUTO-GENERATED by whynot-cut — " + now_iso() + "\n"
          "// Run: File > Scripts > Run Script File… in After Effects, or `reel ae-build`.\n"
          "var NH_DATA = " + json.dumps(data, ensure_ascii=True, indent=1) + ";\n" + lib + "\nNH.build();\n")
    out = paths.p(f"04_after_effects/scripts/build_{paths.video_id}_graphics.jsx")
    write_text(out, js)
    return {"jsx": str(out), "aep": str(aep), "events": len(events), "fps": fps, "warnings": warnings,
            "captions": len(data["captions"]["cues"]) if data["captions"] else 0}


def ae_app_name() -> str | None:
    from .adobe_run import app_name
    return app_name("after_effects")


def execute(paths: Paths, jsx: Path, timeout: int = 900) -> dict:
    from .adobe_run import run_after_effects
    aep = paths.p(f"04_after_effects/project/{paths.video_id}_{project_prefix()}_GFX.aep")
    t0 = time.time()
    res = run_after_effects(jsx, timeout, done=lambda: aep.exists() and aep.stat().st_mtime >= t0 - 1)
    if res.get("status") == "UNSUPPORTED":
        return res
    res["aep_exists"] = aep.exists()
    # existence is not evidence: a copied/older .aep must not count. Require a save during THIS run.
    fresh = aep.exists() and aep.stat().st_mtime >= t0 - 1
    res["aep_saved_this_run"] = fresh
    res["status"] = "AEP_CREATED" if fresh else ("STALE_AEP_NOT_REBUILT" if aep.exists() else "FAILED")
    write_json(paths.p("04_after_effects/ae-build-result.json"), dict(res, at=now_iso()))
    return res


def _movs(d: Path) -> dict[str, tuple[int, int]]:
    """{path: (mtime_ns, size)} of the .mov files in d (AppleDouble ._ files left out)."""
    out = {}
    for x in d.glob("*.mov"):
        if not x.name.startswith("._"):
            try:
                st = x.stat()
            except OSError:
                continue
            out[str(x)] = (st.st_mtime_ns, st.st_size)
    return out


def render(paths: Paths, timeout: int = 3600) -> dict:
    """Render the saved project's queue with aerender. RENDERED only for files THIS run wrote (changed since the
    start, newer than it, not empty): a .mov left by an earlier run proves nothing (3.0 T2.18, MI-13)."""
    from . import ae_render
    env = read_json(paths.output / "discovery/environment.json", {})
    aer = env.get("aerender")
    if not aer or not Path(aer).exists():
        from .adobe_run import aerender
        aer = aerender()
    aep = paths.p(f"04_after_effects/project/{paths.video_id}_{project_prefix()}_GFX.aep")
    if not aer or not Path(aer).exists() or not aep.exists():
        return {"status": "SKIPPED", "msg": f"aerender={aer} aep_exists={aep.exists()}"}
    refused = ae_render.sandbox_refused(aer)
    if refused:
        return {"status": "REFUSED", "outputs": [], "msg": refused["error"], "how": refused["how"]}
    comps = paths.p("04_after_effects/compositions")
    comps.mkdir(parents=True, exist_ok=True)
    before = _movs(comps)
    t0 = time.time()
    logp = paths.p("logs/aerender.log")
    res_p = paths.p("04_after_effects/ae-render-result.json")
    try:
        # the queue's output paths live inside the project; only the command line needs ASCII (ae_render.stage_ascii)
        stage, r_aep, _ = ae_render.stage_ascii(aep)
    except ae_render.StageError as e:
        res = {"status": "FAILED", "returncode": None, "outputs": [], "elapsed_s": 0, "log": None, "msg": str(e)}
        write_json(res_p, dict(res, at=now_iso()))
        return res
    import subprocess
    try:
        p = run([aer, "-project", str(r_aep), "-sound", "OFF", "-continueOnMissingFootage"], check=False, timeout=timeout)
    except subprocess.TimeoutExpired as e:      # 3.0 T2.2: a FAILED result that says what to do, not a traceback
        write_text(logp, ae_render._text(e.stdout) + "\n" + ae_render._text(e.stderr))
        res = {"status": "FAILED", "returncode": None, "outputs": [], "elapsed_s": round(time.time() - t0, 1),
               "log": str(logp), "msg": ae_render.timeout_message(timeout), "how": ae_render.TIMEOUT_HOW}
        write_json(res_p, dict(res, at=now_iso()))
        return res
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
    write_text(logp, p.stdout + "\n" + p.stderr)
    after = _movs(comps)
    fresh = sorted(f for f, (mt, size) in after.items()
                   if size > 0 and before.get(f) != (mt, size) and mt / 1e9 >= t0 - 1)
    stale = sorted(f for f in after if f not in fresh and after[f][1] > 0)
    res = {"status": "RENDERED" if fresh else ("STALE_OUTPUT_NOT_RENDERED" if stale else "FAILED"),
           "returncode": p.returncode, "outputs": fresh, "stale_outputs": stale,
           "elapsed_s": round(time.time() - t0, 1), "log": str(logp)}
    if not fresh:
        res["msg"] = ("aerender wrote no new .mov this run; " + (
            "these are from an earlier run, not this render: " + ", ".join(Path(f).name for f in stale)
            if stale else "check the log") + f" ({logp})")
        res["how"] = ("Open the project in After Effects, check the Render Queue has items and no dialog is waiting, "
                      "then render again")
    write_json(res_p, dict(res, at=now_iso()))
    return res
