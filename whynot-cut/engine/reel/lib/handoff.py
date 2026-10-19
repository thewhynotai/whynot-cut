"""Stage 12 (record + hand off): human-editor handoff package (README + checklist) generated from real state."""
from __future__ import annotations

from pathlib import Path

from .common import Paths, project_prefix, frame_size, frame_to_tc, load_config, now_iso, read_json, seq_fps, write_text


def aspect_label(w: int, h: int) -> str:
    """The aspect of a w x h frame as a file-name tag: 9x16, 4x5, 16x9, 1x1 ... (else the size, e.g. 1000x1500)."""
    from math import gcd
    g = gcd(w, h)
    a, b = w // g, h // g
    return f"{a}x{b}" if max(a, b) <= 21 else f"{w}x{h}"


def export_spec(paths: Paths) -> dict:
    """The client's delivery spec (style.json `export`: name pattern, video/audio settings, folder) for this video.
    Pattern fields: {episode} (the raw file's stem), {video_id}, {name} (the range label without the id), {prefix},
    {version}, {aspect} (9x16, 4x5, 16x9 ... from the frame size). Example: "{episode}_{video_id}_{name}_9x16_AR_v{version:02d}.mp4" -> EP02_R02_Tennis_Racket_Tasleem_..."""
    from .common import source_range
    ex = load_config("style.json").get("export") or {}
    rng = source_range(paths)
    label = (rng.get("label") or "").strip()
    name = label[len(paths.video_id):].strip(" _-") if label.startswith(paths.video_id) else label
    fields = {"episode": Path(rng["footage"]).stem if rng else paths.video_id, "video_id": paths.video_id,
              "name": (name or paths.video_id).replace(" ", "_"), "prefix": project_prefix(),
              "version": int(ex.get("version", 1)), "aspect": aspect_label(*frame_size(paths))}
    try:
        file_name = (ex.get("name") or "{video_id}_{prefix}_{aspect}_v{version:02d}.mp4").format(**fields)
    except (KeyError, ValueError, IndexError) as e:
        file_name = f"{paths.video_id}_{project_prefix()}_{fields['aspect']}_v01.mp4 (export.name pattern error: {e})"
    fps = seq_fps()
    fw, fh = frame_size(paths)
    return {"file_name": file_name,
            "video": ex.get("video") or f"H.264 High Profile, {fw}x{fh} at {fps:.2f} fps, high bitrate (or ProRes)",
            "audio": ex.get("audio") or "AAC 320 kbps, 48 kHz stereo, -14 LUFS integrated, true peak <= -1 dB",
            "folder": ex.get("folder")}


NATIVE_STATUSES = ("PRPROJ_BUILT", "PRPROJ_BUILT_WITH_ISSUES")
MAGNIFIC_MANIFEST = "05_assets/magnific-manifest.json"
LICENCE_NOTE = "agency-licensed, not transferable"


def _rel(paths: Paths, p) -> str | None:
    """A project-relative path with forward slashes on every OS (the README is read on Windows and macOS)."""
    if not p:
        return None
    try:
        return Path(p).relative_to(paths.project).as_posix()
    except ValueError:
        return str(p)


def premiere_build_state(paths: Paths) -> dict:
    """What `ppro-build` really produced: {"native": bool, "status", "rec", "project", "failed_checks", "why"}.
    Native = the bridge saved a .prproj (PRPROJ_BUILT | PRPROJ_BUILT_WITH_ISSUES); anything else (no result, FAILED)
    means the editor works from the XML interchange."""
    rec = read_json(paths.p("07_premiere/ppro-build-result.json"), {}) or {}
    status = rec.get("status")
    native = status in NATIVE_STATUSES
    if native:
        why = None
    elif status:
        err = rec.get("premiere_error")
        why = f"the native build ended **{status}**" + (f" ({err})" if err else "") + " — the XML interchange is the fallback"
    else:
        why = "not built natively yet (no `07_premiere/ppro-build-result.json`)"
    default = paths.p(f"07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj")
    project = rec.get("project") or str(default)
    if not Path(project).exists() and default.exists():      # the client folder moved since the build: use the local copy
        project = str(default)
    return {"native": native, "status": status, "rec": rec, "why": why, "project": project,
            "failed_checks": [k for k, v in (rec.get("checks") or {}).items() if not v] if native else []}


def native_track_rows(rec: dict, tm: dict) -> list[tuple[str, object]]:
    """(track name, clip count) for the native sequence. The names are the ones the bridge was told to give the tracks
    (`job_data.track_names`); the counts are what Premiere reported back. A result without job_data (written before 3.0)
    falls back to Premiere's own read-back, then to the XML manifest's track map."""
    live = (rec.get("result") or {}).get("tracks") or {}
    counts = {k: {t.get("i"): t.get("clips") for t in live.get(k) or []} for k in ("video", "audio")}
    names = (rec.get("job_data") or {}).get("track_names") or rec.get("track_names") or \
        {k: [t.get("name") for t in live.get(k) or []] for k in ("video", "audio")}
    rows = [(n, counts[k].get(i)) for k in ("video", "audio") for i, n in enumerate(names.get(k) or [], 1)]
    if not rows:
        rows = [(f"{'V' if k == 'video' else 'A'}{t['xml_index']} {t['name']}", t.get("clips"))
                for k in ("video", "audio") for t in (tm.get("tracks") or {}).get(k, [])]
    return rows


def _asset_kind(e: dict) -> str:
    """image | video | audio | 3d from the Magnific tool name, else from the file extension."""
    tool = str(e.get("tool") or "").lower()
    for key, kind in (("video", "video"), ("audio", "audio"), ("music", "audio"), ("sfx", "audio"), ("tts", "audio"),
                      ("voice", "audio"), ("3d", "3d"), ("image", "image"), ("upscale", "image"), ("svg", "image")):
        if key in tool:
            return kind
    ext = Path(str(e.get("local_path") or e.get("file") or "")).suffix.lower()
    return ({".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".svg": "image", ".psd": "image",
             ".mp4": "video", ".mov": "video", ".webm": "video", ".wav": "audio", ".mp3": "audio", ".m4a": "audio",
             ".glb": "3d", ".obj": "3d"}).get(ext, "—")


def licensed_material_lines(paths: Paths) -> list[str]:
    """The "Licensed material" section: nothing unless `05_assets/magnific-manifest.json` exists; then one row per
    asset record (master plan Appendix F: asset_id, need_id, local_path, source mcp-creation | stock-rest, tool, model,
    license_type, attribution_*, transferable_to_client). Every asset whose record does not say
    `transferable_to_client: true` is marked agency-licensed, not transferable."""
    mp = paths.p(MAGNIFIC_MANIFEST)
    if not mp.exists():
        return []
    head = ["", "## Licensed material", "", "Assets the agency generated or licensed through Magnific for this clip."]
    try:
        data = read_json(mp, {})
    except (OSError, ValueError) as e:      # read_json raises on a corrupt file: say so instead of failing the handoff
        return head + ["", f"- `{MAGNIFIC_MANIFEST}` could not be read ({type(e).__name__}): ask the agency"]
    entries = data if isinstance(data, list) else next((data[k] for k in ("entries", "assets", "items")
                                                         if isinstance(data, dict) and isinstance(data.get(k), list)), [])
    entries = [e for e in entries if isinstance(e, dict)]
    if not entries:
        return head + ["", "- none listed yet"]
    cell = lambda v: str(v if v not in (None, "") else "—").replace("|", "/").replace("\n", " ")

    def source(e: dict) -> str:
        if e.get("source") == "stock-rest" or (e.get("stock_id") and not e.get("tool")):
            return f"stock {e.get('stock_id') or '—'}"
        return " / ".join(str(x) for x in (e.get("tool"), e.get("model")) if x) or e.get("source") or "—"

    def licence(e: dict) -> str:
        bits = [e.get("license_type") or "licence not recorded"]
        if e.get("attribution_required"):
            bits.append(f"attribution: {e.get('attribution_text') or 'required (text not recorded)'}")
        if e.get("transferable_to_client") is not True:
            bits.append(LICENCE_NOTE)
        return "; ".join(str(b) for b in bits)

    rows = [f"| {cell(e.get('asset_id'))} | {cell(e.get('need_id'))} | {cell(e.get('local_path') or e.get('file'))} | "
            f"{_asset_kind(e)} | {cell(source(e))} | {cell(licence(e))} |" for e in entries]
    return head + ["", "| Asset | Need | File | Kind | Source | Licence |", "|---|---|---|---|---|---|"] + rows


def build(paths: Paths) -> dict:
    from .premiere_xml import timeline_manifest
    tm = timeline_manifest(paths)
    _fps = seq_fps()
    _fps_num = f"{_fps:.2f}"
    _fw, _fh = frame_size(paths)
    _fps_label = f"{_fps:.2f} fps Non-Drop-Frame" if abs(_fps - round(_fps)) > 0.001 else f"{round(_fps)} fps"
    qc = read_json(paths.p("08_quality_control/qc-results.json"), {})
    exp = export_spec(paths)
    style = load_config("style.json")
    no_music = isinstance(style.get("music"), str) and style["music"].lower().startswith("none")
    from .stamps import read_compiled
    spec = read_compiled(paths.p("01_analysis/timeline-spec.json"), {}) or {}
    # manual verse: with a recited verse the CC track comes from the SRT the plan wrote without it (never the
    # transcript's subtitles.srt, which holds Whisper's words of the verse)
    srt = "subtitles-seq.srt" if spec.get("manual_verse") else "subtitles.srt"
    ae = read_json(paths.p("04_after_effects/ae-build-result.json"), {})
    aer = read_json(paths.p("04_after_effects/ae-render-result.json"), {})
    ps = read_json(paths.p("05_photoshop/ps-build-result.json"), {})
    # After Effects / Photoshop are opt-in extras: they appear only when a result or a generated script exists
    ae_used = bool(ae or aer or paths.p(f"04_after_effects/scripts/build_{paths.video_id}_graphics.jsx").exists())
    ps_used = bool(ps or paths.p(f"05_photoshop/scripts/build_{paths.video_id}_psd.jsx").exists())
    ae_captions = paths.p("04_after_effects/compositions/CAPTIONS.mov").exists()
    pb = premiere_build_state(paths)
    native, rec = pb["native"], pb["rec"]
    jd = rec.get("job_data") or {}
    seq_name = tm.get("sequence_name") or jd.get("sequence_name") or f"{paths.video_id}_{project_prefix()}_EDIT"
    prproj_rel = _rel(paths, pb["project"])
    pend = [e for e in spec.get("events", []) if e.get("approval_required")]
    from .verify import status as vstatus
    vs = vstatus(paths)
    from .plan import approval_state
    appr = approval_state(paths)        # a stale approval never reads "approved by X" (3.0 T11)
    rows = native_track_rows(rec, tm) if native else []
    cap_lanes = [n for n, _ in rows if "caption" in n.lower() and n.startswith("V")]
    native_caps = bool(jd.get("native_caption_track",
                              read_json(paths.p("01_analysis/edit-decisions.json"), {}).get("global", {}).get("native_caption_track")))

    music_note = (f"- Music: {style['music']}." if no_music else
                  "- Music: add your licensed track on a new audio track under the SFX pair, using the MUSIC markers; duck −18 to −22 dB under dialogue."
                  if native else
                  "- Music: add your licensed track to A06 using the MUSIC markers; duck −18 to −22 dB under dialogue.")
    music_check = "- [ ] No music (client style)" if no_music else (
        "- [ ] Add licensed music on a new track under the SFX, duck under dialogue" if native else
        "- [ ] Add licensed music on A06, duck under dialogue")

    # ---- the status table
    music_cell = "None, by the client's style" if no_music else "**Not supplied** — markers only"
    if native:
        prem_row = (f"Built natively by the WhyNot Cut Bridge (**{pb['status']}**, {rec.get('at', '—')}) → "
                    "**open the .prproj, nothing to import**")
        cap_row = ("Animated captions are brand stills on the Caption lanes of the sequence" +
                   (f" ({', '.join(cap_lanes)})" if cap_lanes else "") + ", placed by the bridge" +
                   ("; an editable caption track (C01) is also on the sequence" if native_caps else
                    f"; SRT (`02_transcription/{srt}`) for an optional CC track"))
    else:
        prem_row = "FCP7 XML interchange (automated) → **you import + save as .prproj**"
        cap_row = ("Animated captions rendered from AE on C02 (automated); SRT for optional CC track" if ae_captions else
                   f"SRT only (`02_transcription/{srt}`): the XML carries no animated captions — build natively "
                   "(`reel ppro-build`) for those")
    table = ["| Component | Status |", "|---|---|",
             "| Transcription (Whisper large-v3, word timing) | Automated — **needs your verification** (`02_transcription/subtitle-review.md`) |",
             "| Topic / narrative / statement analysis | Automated by Claude (`01_analysis/`) |",
             "| Edit plan → frame-accurate timeline spec | Automated (`01_analysis/timeline-spec.json`, readable: `edit-plan.md`) |",
             f"| Edit plan approval | {appr['message'] if appr['state'] != 'stale' else '**' + appr['message'] + '**'} |",
             f"| Visual verification of renders/PSDs | {'PASS' if vs['ok'] else 'NOT PASSED'}: {vs['detail']} |"]
    if ae_used:
        table += [f"| After Effects comps (.aep, editable) | {ae.get('status', 'SCRIPT ONLY — run the JSX')} |",
                  f"| AE renders (ProRes 4444 + alpha) | {aer.get('status', 'not rendered')}"
                  f"{' (partial)' if aer.get('partial') else ''} |"]                 # T2.16: never reads as all done
    if ps_used:
        table += [f"| Photoshop layered PSDs | {ps.get('status', 'SCRIPT ONLY — run the JSX')} |"]
    table += [f"| Premiere sequence | {prem_row} |", f"| Captions | {cap_row} |",
              "| SFX | Original procedural SFX placed on A-tracks |",
              f"| Music | {music_cell} |",
              "| Final mix, polish, render | You |"]

    # ---- section 1: Premiere
    main_line = (f"Main footage: source is {float(tm.get('source_fps') or 0):.5g} fps in a {_fps_num} fps sequence, kept at native "
                 f"speed (no interpretation change), so dialogue sync is exact; base scale {tm.get('base_scale_percent')}%. "
                 "Punch-ins are separate V1 clips with Scale/Position in Motion.") if tm.get("source_fps") else ""
    markers_line = "Every graphic and decision also appears as a **sequence marker** (ID + transcript evidence)."
    mvs = spec.get("manual_verse") or []
    if mvs:              # manual verse: the verses the editor adds by hand (never their words)
        markers_line += (f" **{len(mvs)} recited verse(s)** have a marker «آية: يضيفها المونتير يدويًا» and empty captions: "
                         "add each verse by hand from a trusted Mushaf and check the diacritics (أضف الآية يدويًا من مصحف "
                         "موثوق ودقّق التشكيل): " + ", ".join(f"{s.get('id')} at {s.get('start_tc')}" for s in mvs) + ".")
    if native:
        all_checks = rec.get("checks") or {}
        ok_checks = [k for k, v in all_checks.items() if v]
        if not all_checks:
            read_back = "; no read-back checks were recorded: confirm them in Sequence › Sequence Settings."
        elif pb["failed_checks"]:
            read_back = f"; read-back: {len(ok_checks)} of {len(all_checks)} passed — see the failures below."
        else:
            read_back = f"; read-back: all {len(all_checks)} checks passed — nothing to set by hand."
        issues = ([f"   - **Not confirmed by the read-back:** {', '.join('`' + c + '`' for c in pb['failed_checks'])}. "
                   "Look at these first; fix and rebuild (`reel ppro-build --force`) or correct them by hand."]
                  if pb["failed_checks"] else [])
        gone = ([f"   - **`{prproj_rel}` is not on disk** — run `reel ppro-build --force` to build it again."]
                if not Path(pb["project"]).exists() else [])
        trk = "\n".join(f"| {n} | {c if c is not None else '—'} |" for n, c in rows) or "| (no track map recorded) | — |"
        cap_step = ("4. Captions: the Caption lanes " + (", ".join(f"**{n}**" for n in cap_lanes) or "(see the track map)") +
                    " hold the animated caption stills (bar + text)" +
                    (" and the sequence also has an editable caption track (C01); keep one of the two visible so captions don't appear twice."
                     if native_caps else ".") +
                    " Caption wording lives in those stills: to correct it, fix the transcript (`02_transcription/transcript-corrections.json`, "
                    "then `reel transcript-correct`) and re-run the pipeline (`reel plan`, `reel previews`, then `reel ppro-build --force`), "
                    "don't retype it in Premiere. Edits made only in `captions-short.srt` are lost whenever the captions are rebuilt "
                    "from the transcript words (a chosen caption size or cut words).")
        sec1 = ["## 1. Open in Premiere Pro (≈1 min)", "",
                f"1. Premiere Pro → **File › Open Project…** → `{prproj_rel}`. The sequence **{seq_name}** is already built with its "
                "media, graphics, captions, markers and audio tracks. **Do not import the XML interchange**: it would add a second sequence."]
        sec1 += gone
        sec1 += [f"2. Sequence settings (frame size, frame rate, preview codec, colour options) are set through Premiere's API by the "
                 f"bridge{read_back}"]
        sec1 += issues
        sec1 += ["3. Track map (as built):", "", "| Track | Clips |", "|---|---|", trk, "", cap_step,
                 f"5. The project stays at `{prproj_rel}`: **File › Save** after your changes. A rebuild (`reel ppro-build --force`) refuses to "
                 "overwrite changes you saved unless `--replace-edited` is added, and it would not carry your edits over.", ""]
    else:
        xml_rel = _rel(paths, tm.get("xml")) or f"07_premiere/interchange/{seq_name}.xml"
        vtr = "\n".join(f"| V{t['xml_index']} | {t['id']} — {t['name']} | {t['clips']} |" for t in tm.get("tracks", {}).get("video", []))
        atr = "\n".join(f"| A{t['xml_index']} | {t['id']} — {t['name']} | {t['clips']} |" for t in tm.get("tracks", {}).get("audio", []))
        cap_step = ("3. Burned-in animated captions are **already on the C02 track** (AE render). Optionally **File › Import…** "
                    f"`02_transcription/{srt}` → drag onto the sequence to get an editable caption track (C01) for closed "
                    "captions/sidecar export — **turn its visibility off** so captions don't appear twice. If you correct caption text, "
                    "fix it in AE (CAPTIONS comp) or re-run the pipeline after editing the SRT." if ae_captions else
                    f"3. The XML carries no animated captions. **File › Import…** `02_transcription/{srt}` → drag onto the sequence "
                    "to get an editable caption track (C01), or ask for the native build (`reel ppro-build`, Premiere open with the WhyNot "
                    "Cut Bridge) which places the animated captions.")
        sec1 = ["## 1. Open in Premiere Pro (≈3 min)", "", f"This clip was {pb['why']}. The preferred path is `reel ppro-build` "
                "(Premiere open with the WhyNot Cut Bridge); import the XML only if that cannot run.", "",
                f"1. Premiere Pro → open/create your project → **File › Import…** → `{xml_rel}`.",
                f"   Premiere creates a bin with the sequence **{seq_name}** and all linked media.",
                "2. Open the sequence → **Sequence › Sequence Settings…** and confirm/set the values the XML cannot carry:",
                f"   - Editing Mode **Custom**, Display Format **{_fps_label} Timecode**, Audio Display Format **Audio Samples**",
                f"   - Preview File Format **QuickTime**, Codec **Apple ProRes 422 LT**, Preview **{_fw} × {_fh}**",
                "   - Maximum Bit Depth **off**, Maximum Render Quality **off**, **Composite in Linear Color on**",
                f"   - (Verify XML-set values: {_fw}×{_fh}, {_fps_num} fps, Square Pixels, No Fields, 48000 Hz stereo.)",
                cap_step,
                "4. Rename tracks (Premiere does not read track names from XML):", "",
                "| XML track | Role | Clips |", "|---|---|---|", vtr, atr, "",
                f"5. **File › Save As…** `07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj`.", ""]
    sec1 += [x for x in (main_line, markers_line) if x]

    # ---- optional extras sections, then approvals and finishing notes (numbered in order)
    n = 1
    extras = []
    if ae_used:
        n += 1
        extras += ["", f"## {n}. After Effects",
                   f"- Project: `{_rel(paths, ae.get('aep') or str(paths.p(f'04_after_effects/project/{paths.video_id}_{project_prefix()}_GFX.aep')))}`. "
                   "Folders: NH_BRAND (edit colours once in **BRAND_CONTROLS › BRAND**), NH_COMPS (one comp per event, named by event ID), NH_CAPTIONS.",
                   "- Re-render after edits: Render Queue already set (High Quality with Alpha → `04_after_effects/compositions/<ID>.mov`), or run "
                   "`reel ae-render`. Premiere clips that use these renders update automatically because file paths stay the same.",
                   "- Arabic: if any line looks disconnected, set **Preferences › Type › Text Engine: South Asian and Middle Eastern**, restart AE."]
    if ps_used:
        n += 1
        extras += ["", f"## {n}. Photoshop",
                   "- `05_photoshop/layered-assets/*.psd` — editable text layers, brand band group, placed client photo, logo."]
    appr_lines = [f"- **{e['event_id']}** ({e['template']}, {e['start_tc']}): {e.get('evidence', '')[:120]}" for e in pend] or ["- none"]
    finish = ["- Frosted-glass cards: overlays carry a translucent fill; for true backdrop blur add an Adjustment Layer under the card with "
              "**Gaussian Blur ≈ 40** masked to the card shape (as in the references).",
              music_note,
              "- Verify all on-screen wording against the content review `01_analysis/medical-content-review.md`.",
              f"- **Export:** `{exp['file_name']}` · {exp['video']} · {exp['audio']}" +
              (f" · deliver to `{exp['folder']}`" if exp.get("folder") else "")]
    L = [f"# Handoff — {paths.video_id}", "",
         f"Generated {now_iso()} by the `whynot-cut` plugin (by The Why Not AI). QC: **{'PASSED' if qc.get('ok') else 'NOT PASSED'}** "
         "(see `08_quality_control/validation-report.md`).", "",
         "## What was automated vs. what you do", ""] + table + [""] + sec1 + extras + \
        ["", f"## {n + 1}. Approvals needed ({len(pend)})"] + appr_lines + ["", f"## {n + 2}. Finishing notes"] + finish + \
        licensed_material_lines(paths)
    write_text(paths.p("09_handoff/README.md"), "\n".join(L) + "\n")

    # ---- the checklist
    if native:
        prem_chk = [f"- [ ] Open `{prproj_rel}` (File › Open Project…), sequence `{seq_name}`: nothing to import"]
        if pb["failed_checks"]:
            prem_chk.append(f"- [ ] Build issues resolved: {', '.join(pb['failed_checks'])}")
        prem_chk += [f"- [ ] Animated captions ({', '.join(cap_lanes) or 'Caption lanes'}) checked against audio" +
                     ("; keep either the stills or the C01 caption track visible, not both" if native_caps else ""),
                     "- [ ] Check no offline media (red frames)", "- [ ] Check punch-ins framing (face/eyes not cropped)",
                     "- [ ] Add frosted backdrop blur under glass cards (optional, reference style)",
                     "- [ ] File › Save (the project stays at the path above)"]
    else:
        prem_chk = [f"- [ ] Import XML, open sequence `{seq_name}`",
                    f"- [ ] Sequence Settings: Custom · {_fps_label} TC · Audio Samples · QuickTime ProRes 422 LT previews {_fw}×{_fh} · Max bit depth OFF · Max render quality OFF · Composite in linear color ON",
                    (f"- [ ] Animated captions (C02) checked against audio; optional `{srt}` caption track kept hidden (CC export only)"
                     if ae_captions else f"- [ ] Captions: import `{srt}` as the caption track (or build natively with `reel ppro-build`)"),
                    "- [ ] Rename tracks per README table", "- [ ] Check no offline media (red frames)",
                    "- [ ] Check punch-ins framing (face/eyes not cropped)",
                    "- [ ] Add frosted backdrop blur under glass cards (optional, reference style)",
                    "- [ ] Save As `.prproj` into `07_premiere/project/`"]
    gfx_chk = ["- [ ] Spot-check every AE comp vs. preview sheet `08_quality_control/previews/_contact_sheet.jpg`",
               "- [ ] Arabic shaping & line breaks correct in AE text layers"] if ae_used else \
              ["- [ ] Spot-check every graphic in the sequence vs. preview sheet `08_quality_control/previews/_contact_sheet.jpg`",
               "- [ ] Arabic shaping & line breaks correct in the graphics and captions"]
    C = ["# Final Editor Checklist — " + paths.video_id, "", "## Before editing",
         "- [ ] Read `09_handoff/README.md`",
         "- [ ] Verify transcript against audio (`02_transcription/subtitle-review.md`) — correct `subtitles.srt`",
         "- [ ] Review `01_analysis/main-topic.md` and `narrative-segments.json`",
         f"- [ ] Approve or reject pending graphics ({len(pend)})",
         "- [ ] Review `01_analysis/medical-content-review.md` (all on-screen medical wording)", "", "## Premiere"] + prem_chk + \
        ["", "## Graphics"] + gfx_chk + ["- [ ] Brand colours and fonts from `output/client_database/branding/` used throughout",
         "", "## Audio", "- [ ] Dialogue peaks ≈ −6 dBFS, integrated ≈ −14 LUFS for social",
         "- [ ] SFX not masking speech; remove any that distract", music_check, "", "## Delivery",
         "- [ ] Final QC pass full-screen at 100%",
         f"- [ ] Export `{exp['file_name']}`: {exp['video']}; audio {exp['audio']}",
         f"- [ ] Deliver to `{exp['folder']}`" if exp.get("folder") else "- [ ] Deliver where the client expects it"]
    write_text(paths.p("09_handoff/final-editor-checklist.md"), "\n".join(C) + "\n")
    return {"readme": str(paths.p("09_handoff/README.md")), "checklist": str(paths.p("09_handoff/final-editor-checklist.md")),
            "export": exp}


def motion_readme(paths: Paths) -> Path:
    """Handoff for a motion video (2.2): the After Effects project, how it is organised, what to edit, fonts, audio,
    renders, licenses and attributions, and what still needs the editor."""
    from .motion_build import aep_path, render_path
    from .stamps import read_compiled
    plan = read_compiled(paths.p("01_analysis/motion-plan.json"), {}) or {}
    qc = read_json(paths.p("08_quality_control/qc-results.json"), {}) or {}
    rr = read_json(paths.p("04_after_effects/motion-render-result.json"), {}) or {}
    br = read_json(paths.p("04_after_effects/motion-build-result.json"), {}) or {}
    fps = float(plan.get("fps") or seq_fps())
    fonts = sorted({e.get("font_ps") for s in plan.get("scenes", []) for e in s.get("elements", []) if e.get("font_ps")})
    music = (plan.get("audio") or {}).get("music")
    L = [f"# {paths.video_id} — motion video handoff", "",
         f"Generated {now_iso()} · QC: {'PASSED' if qc.get('ok') else 'NOT PASSED'} · "
         f"{plan.get('format')} · {plan.get('duration_frames', 0) / fps:.1f} s · {fps:.3f} fps", "",
         "## Open it", "", f"- After Effects project: `{aep_path(paths)}`",
         f"- Main comp: `MAIN_{plan.get('reel_id', paths.video_id)}` (scenes, persistent layers, audio)",
         f"- Master render: `{rr.get('main') or render_path(paths)}`",
         f"- Posting MP4: `{rr.get('mp4') or '(render first)'}` · Cover: `{rr.get('cover') or '—'}`", "",
         "## How it is organised", "",
         "- `NH_BRAND/BRAND_CONTROLS`: brand colours; layers whose colour equals a brand colour follow these controls.",
         "- `NH_SCENES/<scene>_<type>`: one comp per scene, placed in MAIN at its frames with its transition.",
         "- Word-by-word text: each word is its own layer (`<name>_wN`) chained right-to-left by expressions; the "
         "guide layer `<name>` (not rendered) holds the whole line. To change a word, edit its word layer.",
         "- `NH_PERSISTENT`: background, captions, speaker badge, progress, voice pulse.",
         "- Audio layers in MAIN: DIALOGUE (pauses removed, on the sequence clock), MUSIC, SFX_*.", "",
         "## Fonts After Effects needs", ""] + [f"- {f}" for f in fonts] + ["",
         "## Scenes", ""] + [f"- {s['id']} {s['type']} — frames {s['start_frame']}-{s['end_frame']}" for s in plan.get("scenes", [])]
    assets = plan.get("assets") or []
    L += ["", "## Licenses and attributions", ""]
    L += [f"- {a['ref']}: {a['license']}" + (f" — publish with: **{a['attribution']}**" if a.get("attribution") else "")
          for a in assets] or ["- only the client's brand and Lucide icons (ISC)"]
    L += licensed_material_lines(paths)
    warns = (br.get("comparison") or {}).get("warnings") or []
    if warns:
        L += ["", "## Build warnings (After Effects read-back)", ""] + [f"- {w}" for w in warns]
    needs = list(plan.get("approvals") or [])
    if br.get("fallback_font"):
        brand = br.get("brand_fonts") or ["the brand font"]
        are, them = ("are", "them") if len(brand) > 1 else ("is", "it")
        needs.insert(0, f"fonts: this build used the fallback font {br['fallback_font']} because {', '.join(brand)} "
                        f"{are} not installed: install {them} from assets/Fonts, restart After Effects, then "
                        "`reel motion-build` again")
    music_needs = [n for n in plan.get("needs_you") or [] if n.get("kind") == "music"]
    if "needs_you" in plan:         # T4.6: the plan's own music item (no licence / no fitting track), once
        needs += [f"music: {n['text']}" for n in music_needs]
    elif not music:                 # a plan compiled before T4.6
        needs.append("music: add a licensed track (the motion video has dialogue and SFX only)")
    needs += ["final look in After Effects, then render/export for posting",
              "post with the reel's captions from publish/reels (attributions included)"]
    L += ["", "## Needs you", ""] + [f"- [ ] {n}" for n in needs]
    if music_needs:                 # T4.6 (I4): what the music's licence file looks like, for the editor
        from .motion_audio import licence_template
        L += ["", "## Music licence file", "", licence_template()]
    if not qc.get("ok"):
        L += ["", "## QC failures", ""] + [f"- {c['check']}: {c['detail']}" for c in qc.get("failed", [])]
    return write_text(paths.p("09_handoff/README.md"), "\n".join(L) + "\n")
