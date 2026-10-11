"""Stage 9: human-editor handoff package (README + checklist) generated from real state."""
from __future__ import annotations

from pathlib import Path

from .common import Paths, project_prefix, frame_to_tc, load_config, now_iso, read_json, seq_fps, write_text


def export_spec(paths: Paths) -> dict:
    """The client's delivery spec (style.json `export`: name pattern, video/audio settings, folder) for this video.
    Pattern fields: {episode} (the raw file's stem), {video_id}, {name} (the range label without the id), {prefix},
    {version}. Example: "{episode}_{video_id}_{name}_9x16_AR_v{version:02d}.mp4" -> EP02_R02_Tennis_Racket_Tasleem_..."""
    from .common import source_range
    ex = load_config("style.json").get("export") or {}
    rng = source_range(paths)
    label = (rng.get("label") or "").strip()
    name = label[len(paths.video_id):].strip(" _-") if label.startswith(paths.video_id) else label
    fields = {"episode": Path(rng["footage"]).stem if rng else paths.video_id, "video_id": paths.video_id,
              "name": (name or paths.video_id).replace(" ", "_"), "prefix": project_prefix(),
              "version": int(ex.get("version", 1))}
    try:
        file_name = (ex.get("name") or "{video_id}_{prefix}_9x16_v{version:02d}.mp4").format(**fields)
    except (KeyError, ValueError, IndexError) as e:
        file_name = f"{paths.video_id}_{project_prefix()}_9x16_v01.mp4 (export.name pattern error: {e})"
    fps = seq_fps()
    return {"file_name": file_name,
            "video": ex.get("video") or f"H.264 High Profile, 1080x1920 at {fps:.2f} fps, high bitrate (or ProRes)",
            "audio": ex.get("audio") or "AAC 320 kbps, 48 kHz stereo, -14 LUFS integrated, true peak <= -1 dB",
            "folder": ex.get("folder")}


def build(paths: Paths) -> dict:
    from .premiere_xml import timeline_manifest
    tm = timeline_manifest(paths)
    _fps = seq_fps()
    _fps_num = f"{_fps:.2f}"
    _fps_label = f"{_fps:.2f} fps Non-Drop-Frame" if abs(_fps - round(_fps)) > 0.001 else f"{round(_fps)} fps"
    qc = read_json(paths.p("08_quality_control/qc-results.json"), {})
    exp = export_spec(paths)
    style = load_config("style.json")
    music_note = (f"- Music: {style['music']}." if isinstance(style.get("music"), str) and style["music"].lower().startswith("none")
                  else "- Music: add your licensed track to A06 using the MUSIC markers; duck −18 to −22 dB under dialogue.")
    music_check = ("- [ ] No music (client style)" if music_note.startswith("- Music: none")
                   else "- [ ] Add licensed music on A06, duck under dialogue")
    spec = read_json(paths.p("01_analysis/timeline-spec.json"), {})
    ae = read_json(paths.p("04_after_effects/ae-build-result.json"), {})
    aer = read_json(paths.p("04_after_effects/ae-render-result.json"), {})
    ps = read_json(paths.p("05_photoshop/ps-build-result.json"), {})
    seq = load_config("sequence-settings.json")
    rel = lambda p: str(Path(p).relative_to(paths.project)) if p and str(p).startswith(str(paths.project)) else p
    pend = [e for e in spec.get("events", []) if e.get("approval_required")]
    from .verify import status as vstatus
    vs = vstatus(paths)
    appr = read_json(paths.p("01_analysis/plan-approval.json"), {})
    vtr = "\n".join(f"| V{t['xml_index']} | {t['id']} — {t['name']} | {t['clips']} |" for t in tm.get("tracks", {}).get("video", []))
    atr = "\n".join(f"| A{t['xml_index']} | {t['id']} — {t['name']} | {t['clips']} |" for t in tm.get("tracks", {}).get("audio", []))
    R = f"""# Handoff — {paths.video_id}

Generated {now_iso()} by the `whynot-cut` plugin (by The Why Not AI). QC: **{'PASSED' if qc.get('ok') else 'NOT PASSED'}** (see `08_quality_control/validation-report.md`).

## What was automated vs. what you do

| Component | Status |
|---|---|
| Transcription (Whisper large-v3, word timing) | Automated — **needs your verification** (`02_transcription/subtitle-review.md`) |
| Topic / narrative / statement analysis | Automated by Claude (`01_analysis/`) |
| Edit plan → frame-accurate timeline spec | Automated (`01_analysis/timeline-spec.json`, readable: `edit-plan.md`) |
| Edit plan approval | {('approved by ' + appr.get('by', '?') + (' (stale: plan changed)' if appr.get('stale') else '')) if appr else 'NOT approved'} |
| Visual verification of renders/PSDs | {'PASS' if vs['ok'] else 'NOT PASSED'}: {vs['detail']} |
| After Effects comps (.aep, editable) | {ae.get('status', 'SCRIPT ONLY — run the JSX')} |
| AE renders (ProRes 4444 + alpha) | {aer.get('status', 'not rendered')} |
| Photoshop layered PSDs | {ps.get('status', 'SCRIPT ONLY — run the JSX')} |
| Premiere sequence | FCP7 XML interchange (automated) → **you import + save as .prproj** |
| Captions | Animated captions rendered from AE on C02 (automated); SRT for optional CC track |
| SFX | Original procedural SFX placed on A-tracks |
| Music | {"None, by the client's style" if music_check.startswith("- [ ] No music") else "**Not supplied** — markers only"} |
| Final mix, polish, render | You |

## 1. Open in Premiere Pro (≈3 min)

1. Premiere Pro → open/create your project → **File › Import…** → `{rel(tm.get('xml'))}`.
   Premiere creates a bin with the sequence **{tm.get('sequence_name')}** and all linked media.
2. Open the sequence → **Sequence › Sequence Settings…** and confirm/set the values the XML cannot carry:
   - Editing Mode **Custom**, Display Format **{_fps_label} Timecode**, Audio Display Format **Audio Samples**
   - Preview File Format **QuickTime**, Codec **Apple ProRes 422 LT**, Preview **1080 × 1920**
   - Maximum Bit Depth **off**, Maximum Render Quality **off**, **Composite in Linear Color on**
   - (Verify XML-set values: 1080×1920, {_fps_num} fps, Square Pixels, No Fields, 48000 Hz stereo.)
3. Burned-in animated captions are **already on the C02 track** (AE render). Optionally **File › Import…** `02_transcription/subtitles.srt` → drag onto the sequence to get an editable caption track (C01) for closed captions/sidecar export — **turn its visibility off** so captions don't appear twice. If you correct caption text, fix it in AE (CAPTIONS comp) or re-run the pipeline after editing the SRT.
4. Rename tracks (Premiere does not read track names from XML):

| XML track | Role | Clips |
|---|---|---|
{vtr}
{atr}

5. **File › Save As…** `07_premiere/project/{paths.video_id}_{project_prefix()}_EDIT.prproj`.

Main footage: source is {float(tm.get('source_fps') or 0):.5g} fps in a {_fps_num} fps sequence, kept at native speed (no interpretation change), so dialogue sync is exact; base scale {tm.get('base_scale_percent')}%. Punch-ins are separate V1 clips with Scale/Position in Motion.
Every graphic and decision also appears as a **sequence marker** (ID + transcript evidence).

## 2. After Effects
- Project: `{rel(ae.get('aep') or str(paths.p(f'04_after_effects/project/{paths.video_id}_{project_prefix()}_GFX.aep')))}`. Folders: NH_BRAND (edit colours once in **BRAND_CONTROLS › BRAND**), NH_COMPS (one comp per event, named by event ID), NH_CAPTIONS.
- Re-render after edits: Render Queue already set (High Quality with Alpha → `04_after_effects/compositions/<ID>.mov`), or run `reel ae-render`. Premiere clips update automatically because file paths stay the same.
- Arabic: if any line looks disconnected, set **Preferences › Type › Text Engine: South Asian and Middle Eastern**, restart AE.

## 3. Photoshop
- `05_photoshop/layered-assets/*.psd` — editable text layers, brand band group, placed client photo, logo.

## 4. Approvals needed ({len(pend)})
""" + ("\n".join(f"- **{e['event_id']}** ({e['template']}, {e['start_tc']}): {e.get('evidence', '')[:120]}" for e in pend) or "- none") + f"""

## 5. Finishing notes
- Frosted-glass cards: overlays carry a translucent fill; for true backdrop blur add an Adjustment Layer under the card with **Gaussian Blur ≈ 40** masked to the card shape (as in the references).
{music_note}
- Verify all on-screen wording against the content review `01_analysis/medical-content-review.md`.
- **Export:** `{exp['file_name']}` · {exp['video']} · {exp['audio']}{f" · deliver to `{exp['folder']}`" if exp.get('folder') else ""}
"""
    write_text(paths.p("09_handoff/README.md"), R)
    C = f"""# Final Editor Checklist — {paths.video_id}

## Before editing
- [ ] Read `09_handoff/README.md`
- [ ] Verify transcript against audio (`02_transcription/subtitle-review.md`) — correct `subtitles.srt`
- [ ] Review `01_analysis/main-topic.md` and `narrative-segments.json`
- [ ] Approve or reject pending graphics ({len(pend)})
- [ ] Review `01_analysis/medical-content-review.md` (all on-screen medical wording)

## Premiere
- [ ] Import XML, open sequence `{tm.get('sequence_name')}`
- [ ] Sequence Settings: Custom · {_fps_label} TC · Audio Samples · QuickTime ProRes 422 LT previews 1080×1920 · Max bit depth OFF · Max render quality OFF · Composite in linear color ON
- [ ] Animated captions (C02) checked against audio; optional `subtitles.srt` caption track kept hidden (CC export only)
- [ ] Rename tracks per README table
- [ ] Check no offline media (red frames)
- [ ] Check punch-ins framing (face/eyes not cropped)
- [ ] Add frosted backdrop blur under glass cards (optional, reference style)
- [ ] Save As `.prproj` into `07_premiere/project/`

## Graphics
- [ ] Spot-check every AE comp vs. preview sheet `08_quality_control/previews/_contact_sheet.jpg`
- [ ] Arabic shaping & line breaks correct in AE text layers
- [ ] Brand colours and fonts from `output/client_database/branding/` used throughout

## Audio
- [ ] Dialogue peaks ≈ −6 dBFS, integrated ≈ −14 LUFS for social
- [ ] SFX not masking speech; remove any that distract
{music_check}

## Delivery
- [ ] Final QC pass full-screen at 100%
- [ ] Export `{exp['file_name']}`: {exp['video']}; audio {exp['audio']}
{f"- [ ] Deliver to `{exp['folder']}`" if exp.get('folder') else "- [ ] Deliver where the client expects it"}
"""
    write_text(paths.p("09_handoff/final-editor-checklist.md"), C)
    return {"readme": str(paths.p("09_handoff/README.md")), "checklist": str(paths.p("09_handoff/final-editor-checklist.md")),
            "export": exp}


def motion_readme(paths: Paths) -> Path:
    """Handoff for a motion video (2.2): the After Effects project, how it is organised, what to edit, fonts, audio,
    renders, licenses and attributions, and what still needs the editor."""
    from .motion_build import aep_path, render_path
    plan = read_json(paths.p("01_analysis/motion-plan.json"), {}) or {}
    qc = read_json(paths.p("08_quality_control/qc-results.json"), {}) or {}
    rr = read_json(paths.p("04_after_effects/motion-render-result.json"), {}) or {}
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
    needs = list(plan.get("approvals") or [])
    if not music:
        needs.append("music: add a licensed track (the motion video has dialogue and SFX only)")
    needs += ["final look in After Effects, then render/export for posting",
              "post with the reel's captions from publish/reels (attributions included)"]
    L += ["", "## Needs you", ""] + [f"- [ ] {n}" for n in needs]
    if not qc.get("ok"):
        L += ["", "## QC failures", ""] + [f"- {c['check']}: {c['detail']}" for c in qc.get("failed", [])]
    return write_text(paths.p("09_handoff/README.md"), "\n".join(L) + "\n")
