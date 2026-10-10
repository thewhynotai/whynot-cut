"""Stage 8: automatic quality control. A mandatory failure blocks QC_PASSED."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .common import still_category, Paths, fmt_ts, load_config, now_iso, read_json, write_json, write_text, frame_to_tc
from . import srt as srtlib


class Report:
    def __init__(self):
        self.items = []

    def add(self, group, name, ok, detail="", mandatory=True, level=None):
        lvl = level or ("PASS" if ok else ("FAIL" if mandatory else "WARN"))
        self.items.append({"group": group, "check": name, "result": lvl, "mandatory": mandatory, "detail": detail})

    @property
    def failed(self):
        return [i for i in self.items if i["result"] == "FAIL"]


FULL_SCREEN = {"broll_card", "broll_video", "logo_outro", "flash_transition", "photo_card"}


def run_qc(paths: Paths) -> dict:
    r = Report()
    seq = load_config("sequence-settings.json")
    W, H, FPS = seq["general"]["frame_width"], seq["general"]["frame_height"], seq["general"]["timebase"]
    spec = read_json(paths.p("01_analysis/timeline-spec.json"))
    tm = read_json(paths.p("07_premiere/timeline-manifest.json"))
    missing_assets = []

    # ---------------- technical: XML
    if tm and Path(tm["xml"]).exists():
        try:
            root = ET.parse(tm["xml"]).getroot()
            sc = root.find("./sequence/media/video/format/samplecharacteristics")
            r.add("technical", "XML parses (well-formed xmeml v4)", root.tag == "xmeml" and root.get("version") == "4")
            r.add("technical", f"Sequence resolution {W}x{H}",
                  sc.findtext("width") == str(W) and sc.findtext("height") == str(H),
                  f"{sc.findtext('width')}x{sc.findtext('height')}")
            r.add("technical", f"Sequence timebase {FPS} fps (non-NTSC)",
                  root.findtext("./sequence/rate/timebase") == str(FPS) and root.findtext("./sequence/rate/ntsc") == "FALSE")
            r.add("technical", "Pixel aspect square / progressive",
                  sc.findtext("pixelaspectratio") == "square" and sc.findtext("fielddominance") == "none")
            r.add("technical", "Audio 48 kHz stereo",
                  root.findtext("./sequence/media/audio/format/samplecharacteristics/samplerate") == "48000"
                  and root.findtext("./sequence/media/audio/numOutputChannels") == "2")
            bad = []
            for pu in root.iter("pathurl"):
                from .premiere_xml import path_from_url
                pth = str(path_from_url(pu.text))
                if not Path(pth).exists():
                    bad.append(pth)
            r.add("technical", "All XML media references resolve", not bad, "; ".join(bad[:5]))
            missing_assets += [f"XML media missing: {b}" for b in bad]
            dur = int(root.findtext("./sequence/duration"))
            over = [c.findtext("name") for c in root.iter("clipitem") if int(c.findtext("end")) > dur]
            r.add("technical", "No clip ends beyond sequence duration", not over, ", ".join(over[:5]))
            # V1 continuity: main footage covers the whole sequence without gaps
            v1 = root.find("./sequence/media/video/track")
            spans = sorted((int(c.findtext("start")), int(c.findtext("end"))) for c in v1.iter("clipitem"))
            gaps = [(a[1], b[0]) for a, b in zip(spans, spans[1:]) if b[0] != a[1]]
            r.add("technical", "V1 main footage continuous (no gaps/overlaps)", not gaps and spans and spans[0][0] == 0,
                  f"gaps={gaps[:3]}")
            # A/V sync: each V1 clip's in == start (timeline time == source time)
            # sync: every A1 dialogue clip mirrors its V1 picture clip (same timeline span AND same source ticks)
            atr = root.find("./sequence/media/audio/track")
            vk = [(c.findtext("start"), c.findtext("end"), c.findtext("pproTicksIn")) for c in v1.iter("clipitem")]
            ak = [(c.findtext("start"), c.findtext("end"), c.findtext("pproTicksIn")) for c in atr.iter("clipitem")] if atr is not None else []
            r.add("technical", "Dialogue sync preserved (A1 clips mirror V1 clips: span + source ticks)",
                  vk == ak and bool(vk), f"{len(vk)} video vs {len(ak)} audio clips")
        except Exception as e:
            r.add("technical", "XML parses", False, str(e))
    else:
        r.add("technical", "Premiere interchange XML exists", False, "run `reel premiere`")

    # ---------------- technical: subtitles
    srt_p = paths.p("02_transcription/subtitles.srt")
    tj = read_json(paths.p("02_transcription/transcript.json"))
    if srt_p.exists() and tj:
        errs = srtlib.validate_cues(srtlib.read_srt(srt_p), tj["meta"]["duration_ms"])
        r.add("technical", "subtitles.srt timing valid", not errs, "; ".join(errs[:5]))
        rv = paths.p("02_transcription/subtitle-review.md").read_text(encoding="utf-8") if paths.p("02_transcription/subtitle-review.md").exists() else ""
        from .transcribe import transcript_flags, transcript_verified
        verified = transcript_verified(paths)
        r.add("creative", "Transcript verified by a human", verified,
              "Machine transcript (or changed since it was verified) — verify with subtitle-review.md, then "
              "`reel transcript-verify`", mandatory=False)
        fl = transcript_flags(paths)
        r.add("creative", "No uncertain words left unconfirmed", not fl,
              ", ".join(f"#{f['id']} {f['word']} ({fmt_ts(f['start_ms'], '.')})" for f in fl[:8]), mandatory=False)
    else:
        r.add("technical", "subtitles.srt exists", False)

    # ---------------- technical: frames + assets
    if spec:
        bad = [e["event_id"] for e in spec["events"] if not (0 <= e["start_frame"] < e["end_frame"] <= spec["duration_frames"])]
        r.add("technical", "All event frame positions inside sequence", not bad, ", ".join(bad))
        bm = read_json(paths.p("03_broll/broll-manifest.json"), {"assets": []})
        miss = []
        for a in bm["assets"]:
            ae, png = paths.p(a["output_paths"]["ae_render"]), paths.p(a["output_paths"]["preview_png"])
            a["validation_status"] = "AE_RENDERED" if ae.exists() else ("PREVIEW_PNG_ONLY" if png.exists() else "MISSING")
            if not ae.exists() and not png.exists():
                miss.append(a["asset_id"])
        write_json(paths.p("03_broll/broll-manifest.json"), bm)
        r.add("technical", "Every planned graphic has media (AE render or preview)", not miss, ", ".join(miss))
        missing_assets += [f"Graphic not generated: {m}" for m in miss]
        n_ae = sum(1 for a in bm["assets"] if a["validation_status"] == "AE_RENDERED")
        extras = n_ae > 0 or paths.p("04_after_effects/ae-build-result.json").exists()
        if extras:   # Premiere-first by default: AE renders are only judged when the AE extra was used
            r.add("technical", "Graphics rendered from After Effects (animated/editable)", n_ae == len(bm["assets"]),
                  f"{n_ae}/{len(bm['assets'])} AE renders; others are static previews", mandatory=False)
        # jump cuts: every cut after a removed pause must show a visible zoom change
        same = []
        segs = spec.get("main_segments", [])
        for a_, b_ in zip(segs, segs[1:]):
            if "keep_index" in b_ and b_.get("keep_index") != a_.get("keep_index") \
                    and abs(b_["scale_factor"] - a_["scale_factor"]) < 1e-6 \
                    and "AUTO_CUTAWAY" not in (a_.get("decision_id"), b_.get("decision_id")):   # cards stay whole
                same.append(f"frame {b_['start_frame']} ({a_['scale_factor']}→{b_['scale_factor']})")
        if spec.get("time_map"):
            r.add("technical", "Every jump cut changes the zoom (cut masked)", not same, ", ".join(same[:6]))
        # graphics stay inside the platform-safe area (full-screen templates excluded)
        sa = load_config("subtitle-style.json").get("safe_area", {})
        out_sa = []
        if sa:
            from PIL import Image
            for e in spec["events"]:
                if e["template"] in FULL_SCREEN:
                    continue
                cat = still_category(e["template"])
                png = paths.p(f"03_broll/{cat}/{e['event_id']}.png")
                if not png.exists():
                    continue
                bb = Image.open(png).getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
                if bb and (bb[1] < sa.get("top", 0) or bb[3] > H - sa.get("bottom", 0)
                           or bb[0] < sa.get("left", 0) - 40 or bb[2] > W - sa.get("right", 0) + 40):
                    out_sa.append(f"{e['event_id']} {e['template']} y {bb[1]}–{bb[3]} x {bb[0]}–{bb[2]}")
            r.add("creative", f"Graphics inside the safe area (top {sa.get('top')}, bottom {sa.get('bottom')} px)",
                  not out_sa, "; ".join(out_sa[:5]))
        # probe AE renders
        try:
            from .media import probe
            badr = []
            for mov in sorted(m for m in paths.p("04_after_effects/compositions").glob("*.mov") if not m.name.startswith("._")):
                pr = probe(mov)
                v = pr.get("video") or {}
                if (v.get("display_width"), v.get("display_height")) != (W, H) or round(v.get("fps") or 0) != FPS:
                    badr.append(f"{mov.name}: {v.get('display_width')}x{v.get('display_height')}@{v.get('fps')}")
                elif v.get("pix_fmt") and not any(k in v["pix_fmt"] for k in ("a", "rgba", "argb", "yuva")):
                    badr.append(f"{mov.name}: no alpha ({v.get('pix_fmt')})")
            r.add("technical", "AE renders are 1080x1920 @24 fps with alpha", not badr, "; ".join(badr[:5]))
        except Exception as e:
            r.add("technical", "AE render probe", False, str(e), mandatory=False)
        cues = read_json(paths.p("06_audio/audio-cue-sheet.json"), {"cues": []})["cues"]
        ms = [c["cue_id"] for c in cues if not paths.p(c["source_file"]).exists()]
        r.add("technical", "All SFX cue files exist", not ms, ", ".join(ms[:5]))
        missing_assets += [f"SFX missing: {m}" for m in ms]

        # ---------------- creative heuristics
        dur = spec["duration_frames"] or 1
        full = sum(e["end_frame"] - e["start_frame"] for e in spec["events"]
                   if e["template"] in ("broll_card", "broll_video", "logo_outro"))
        r.add("creative", "Speaker visible ≥ 75% of runtime", full / dur <= 0.25, f"full-screen cover {full / dur:.0%}", mandatory=False)
        ov = sum(e["end_frame"] - e["start_frame"] for e in spec["events"] if e["template"] not in ("flash_transition",))
        r.add("creative", "Overlay density reasonable (≤ 70% of runtime)", ov / dur <= 0.7, f"{ov / dur:.0%}", mandatory=False)
        cpm = len(cues) / (dur / 24 / 60)
        r.add("creative", "SFX density restrained (≤ 18 cues/min)", cpm <= 18, f"{cpm:.1f}/min", mandatory=False)
        pend = [e["event_id"] for e in spec["events"] if e.get("approval_required")]
        r.add("creative", "No graphics awaiting approval", not pend, f"pending: {', '.join(pend)}", mandatory=False)
        r.add("creative", "Music placed", spec.get("music", {}).get("status") == "PLACED",
              "No licensed/approved music supplied — A06 holds markers only", mandatory=False)

    # ---------------- analysis artefacts
    for rel in ("01_analysis/main-topic.md", "01_analysis/narrative-segments.json",
                "01_analysis/transcript-semantic-analysis.json", "01_analysis/medical-content-review.md",
                "01_analysis/editing-style.json", "01_analysis/edit-decisions.json", "01_analysis/plan-validation.json"):
        r.add("project", f"{rel} present", paths.p(rel).exists())
    pv = read_json(paths.p("01_analysis/plan-validation.json"), {})
    r.add("project", "Edit decisions traceable to transcript (plan validation)", pv.get("ok", False), "; ".join(pv.get("errors", [])[:3]))

    # ---------------- fonts
    typ = read_json(paths.client_db / "branding/typography.json", {})
    # graphics reach Premiere as rendered stills (shaped from the font FILES), so installed fonts are only required for
    # live text: the AE/PS extras or a native caption track. Otherwise a missing install is advisory.
    needs_fonts = bool(read_json(paths.p("04_after_effects/ae-build-result.json")) or
                       read_json(paths.p("05_photoshop/ps-build-result.json")) or
                       read_json(paths.p("01_analysis/edit-decisions.json"), {}).get("global", {}).get("native_caption_track"))
    r.add("technical", "Brand fonts installed" + ("" if needs_fonts else " (needed only for live text in Premiere/AE/PS)"),
          not typ.get("missing_or_uninstalled"), str(typ.get("missing_or_uninstalled")), mandatory=needs_fonts)
    ae_res = read_json(paths.p("04_after_effects/ae-build-result.json"), {})
    if ae_res:   # only when the optional After Effects extra was used
        r.add("technical", "After Effects project (.aep) created in application", ae_res.get("status") == "AEP_CREATED",
              ae_res.get("status"), mandatory=False)
    ps_res = read_json(paths.p("05_photoshop/ps-build-result.json"), {})
    if ps_res:   # only when the optional Photoshop extra was used
        r.add("technical", "Photoshop PSDs created in application", ps_res.get("status") == "PSD_CREATED",
              ps_res.get("status"), mandatory=False)
    pb = read_json(paths.p("07_premiere/ppro-build-result.json"), {})
    prj = Path(pb.get("project", "")) if pb.get("project") else None
    built = pb.get("status") == "PRPROJ_BUILT" and prj is not None and prj.exists()
    r.add("project", "Native Premiere .prproj built and saved by Premiere (WhyNot Cut Bridge)", built,
          f"{pb.get('status')} · {pb.get('project')}" if pb else "not built — run `reel ppro-build` (or import the XML manually)",
          mandatory=False, level=None if built else "MANUAL")
    if built:
        r.add("project", "Premiere build read-back checks", all((pb.get("checks") or {}).values()),
              ", ".join(k for k, v in (pb.get("checks") or {}).items() if not v) or "all pass")
        from .verify import editor_modified
        em = editor_modified(paths)
        r.add("project", "Premiere project unchanged since the pipeline build", not em,
              f"edited in Premiere at {em['edited_at']} (built {em['built_at']}) — the editor's own work; a rebuild would "
              f"not carry it over" if em else "unchanged", mandatory=False)
    dc = read_json(paths.p("06_audio/dialogue/dialogue-clean-report.json"))
    if dc:
        m = dc["metrics"]
        # judge the DELIVERED file (metrics["after"]), not an intermediate stage
        before, after = m["before_selected_mic"]["speech_to_noise_db"], m["after"]["speech_to_noise_db"]
        if (dc.get("source_assessment") or {}).get("already_clean"):
            r.add("technical", "Clean source kept clean (delivered file)", after >= before - 1,
                  f"{before} -> {after} dB; {m['lufs_before']} -> {m['lufs_after']} LUFS", mandatory=False)
        else:
            r.add("technical", "Dialogue cleanup improved speech-to-noise (delivered file)", after >= before + 3,
                  f"{before} -> {after} dB; {m['lufs_before']} -> {m['lufs_after']} LUFS", mandatory=False)
    cv = read_json(paths.p("06_audio/dialogue/cut-verification.json"))
    if read_json(paths.p("01_analysis/edit-decisions.json"), {}).get("global", {}).get("remove_pauses"):
        r.add("technical", "Pause removal cut no speech (re-transcription diff)",
              bool(cv) and not cv.get("missing") and cv.get("ok", True),
              (f"missing words: {cv.get('missing')}" + (f"; {cv['verdict']}" if cv.get("verdict") else "")
               + (f"; coverage {cv['coverage']}" if "coverage" in cv else "")) if cv else "not verified — run audio-clean")
        near = [c for c in (cv or {}).get("changed", []) if c.get("cuts_nearby")]
        r.add("creative", "Cut points where wording changed next to a cut (listen to these)", not near,
              "; ".join(f"{c['src_ms'][0] / 1000:.1f}s '{c['orig']}'→'{c['tight']}'" for c in near[:6]) or "none", mandatory=False)

    # ---------------- evidence gates (verification-before-completion)
    from .verify import status as vstatus
    from .plan import plan_fingerprint
    vs = vstatus(paths)
    r.add("evidence", "Visual verification PASS recorded after the latest renders", vs["ok"], vs["detail"])
    appr = read_json(paths.p("01_analysis/plan-approval.json"))
    appr_ok = bool(appr) and not appr.get("stale") and spec is not None and appr.get("plan_fingerprint") == plan_fingerprint(paths)
    r.add("evidence", "Current edit plan approved (editor or explicitly delegated)", appr_ok,
          f"by {appr.get('by')} at {appr.get('at')}" if appr else "no approval recorded")

    ok = not r.failed
    out = {"generated": now_iso(), "ok": ok, "checks": r.items, "failed": r.failed}
    write_json(paths.p("08_quality_control/qc-results.json"), out)
    L = ["# Validation Report", "", f"Video: **{paths.video_id}** — generated {out['generated']}", "",
         f"**Overall: {'PASSED (no mandatory failures)' if ok else 'FAILED — see FAIL rows'}**", "",
         "| Group | Check | Result | Detail |", "|---|---|---|---|"]
    for i in r.items:
        L.append(f"| {i['group']} | {i['check']} | {i['result']}{'' if i['mandatory'] else ' (advisory)'} | {str(i['detail']).replace('|', '/')[:220]} |")
    write_text(paths.p("08_quality_control/validation-report.md"), "\n".join(L) + "\n")
    M = ["# Missing Assets", ""] + ([f"- {m}" for m in missing_assets] or ["- No missing generated assets."])
    M += ["", "## Not supplied by client (cannot be invented)", "",
          "- Background music: no approved/licensed track in `data/`. Add one (e.g. `data/Music/…`) and re-run `reel premiere`.",
          "- Stock/illustrative B-roll: no library or approved generation provider configured; B-roll uses client assets and branded graphics only."]
    write_text(paths.p("08_quality_control/missing-assets.md"), "\n".join(M) + "\n")
    return out
