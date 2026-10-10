"""Premiere Pro interchange: FCP7 XML (xmeml v4) built from timeline-spec.json.

Why XML: Premiere Pro (2026) exposes no AppleScript/CLI entry point to build a .prproj, and
.prproj is an undocumented format we must not fabricate. FCP7 XML is Premiere's long-standing
supported import format. Premiere's own tick values (pproTicksIn/Out, 254016000000 per second)
are written so mixed-rate media (25 fps source in a 24 fps sequence) maps exactly.

Coverage (honest): sequence size/rate/PAR/fields/audio rate, track layout, clip placement,
Basic Motion scale/center, linked A/V, sequence markers. NOT covered: caption tracks
(import subtitles.srt in Premiere), preview codec settings, track names, adjustment layers,
Essential Graphics, Lumetri. See references/premiere-assembly.md.
"""
from __future__ import annotations

import math
import uuid
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from .common import still_category, seq_fps, ticks_per_frame, Paths, project_prefix, load_config, now_iso, read_json, write_json, write_text, frame_to_tc

TPS = 254016000000  # Premiere ticks per second


def pathurl(p: Path) -> str:
    """FCP7 file URL Premiere accepts on both systems: file://localhost/Volumes/x/a%20b.mov (macOS) and
    file://localhost/C:/Users/x/a%20b.mov (Windows). Backslashes or an encoded drive colon break media linking."""
    posix = Path(p).resolve().as_posix()
    if not posix.startswith("/"):
        posix = "/" + posix
    return "file://localhost" + quote(posix, safe="/:")


def path_from_url(url: str) -> Path:
    """Inverse of pathurl (also reads URLs written by older releases)."""
    from urllib.parse import unquote
    s = unquote(url.replace("file://localhost", "", 1).replace("file://", "", 1))
    if len(s) > 2 and s[0] == "/" and s[2] == ":":       # /C:/Users/... -> C:/Users/...
        s = s[1:]
    return Path(s)


def rate(fps: float) -> str:
    """FCP7 rate: 29.97 -> timebase 30 + NTSC TRUE (a fractional timebase is invalid XML), 25 -> 25 + FALSE."""
    tb = round(fps)
    ntsc = abs(fps - tb) > 0.001
    return f"<rate><timebase>{tb}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"


class XB:
    def __init__(self):
        self.files = {}  # path -> (id, emitted)
        self.n_clip = 0

    def file_el(self, path: Path, kind: str, dur_frames: int, tb: int, w=None, h=None, audio_ch=None,
                still=False) -> str:
        key = str(path)
        if key in self.files:
            return f'<file id="{self.files[key]}"/>'
        fid = f"file-{len(self.files) + 1}"
        self.files[key] = fid
        media = ""
        if kind in ("video", "still"):
            media += (f"<video><samplecharacteristics>{rate(tb)}<width>{w}</width><height>{h}</height>"
                      f"<anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio>"
                      f"<fielddominance>none</fielddominance></samplecharacteristics></video>")
        if audio_ch:
            # Premiere exports stereo media as TWO mono channels (verified with seq.exportAsFinalCutProXML on
            # Premiere 26.5); declaring one stereo channel made its importer drop all audio.
            for ch, lab in ((1, "left"), (2, "right"))[:max(1, audio_ch)]:
                media += (f"<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>"
                          f"</samplecharacteristics><channelcount>1</channelcount><layout>stereo</layout>"
                          f"<audiochannel><sourcechannel>{ch}</sourcechannel><channellabel>{lab}</channellabel></audiochannel></audio>")
        return (f'<file id="{fid}"><name>{escape(Path(path).name)}</name><pathurl>{pathurl(path)}</pathurl>'
                f"{rate(tb)}<duration>{dur_frames}</duration><media>{media}</media></file>")

    def clip_id(self) -> str:
        self.n_clip += 1
        return f"clipitem-{self.n_clip}"


def audio_duration(path: Path) -> float:
    """Duration in seconds (PyAV handles WAVE_FORMAT_EXTENSIBLE 24-bit files that `wave` rejects)."""
    try:
        import av
        with av.open(str(path)) as c:
            a = c.streams.audio[0]
            if a.duration is not None:
                return float(a.duration * a.time_base)
            return c.duration / 1e6
    except Exception:
        import wave
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()


def motion_filter(scale: float, cx: float = 0.0, cy: float = 0.0) -> str:
    return ("<filter><effect><name>Basic Motion</name><effectid>basic</effectid>"
            "<effectcategory>motion</effectcategory><effecttype>motion</effecttype><mediatype>video</mediatype>"
            f"<parameter authoringApp=\"PremierePro\"><parameterid>scale</parameterid><name>Scale</name>"
            f"<valuemin>0</valuemin><valuemax>1000</valuemax><value>{scale:.3f}</value></parameter>"
            f"<parameter authoringApp=\"PremierePro\"><parameterid>center</parameterid><name>Center</name>"
            f"<value><horiz>{cx:.5f}</horiz><vert>{cy:.5f}</vert></value></parameter>"
            "</effect></filter>")


NATIVE_GFX_TRACKS = ["V07", "V04", "V09", "V05", "V12"]   # graphic layers (bottom->top) placed natively in Premiere


def broll_clipitem(xb: "XB", ev: dict, paths: Paths, W: int, H: int, fps: int) -> str | None:
    """A full-screen licensed B-roll video clip: cover-scaled to the vertical frame (crop_center optional), source in-point
    `in` seconds, VIDEO ONLY (no linked audio), hard cut."""
    from .media import probe
    p = ev["params"]
    vid = paths.root / p["video"]
    if not vid.exists():
        return None
    pr = probe(vid)
    v = pr.get("video")
    if not v:
        return None
    sfps = v.get("fps") or fps
    s, e = ev["start_frame"], ev["end_frame"]
    n = e - s
    in_s = float(p.get("in", 0) or 0)
    tin = round(in_s * TPS)
    fin = round(in_s * fps)
    dw, dh = v["display_width"], v["display_height"]
    cover = max(W / dw, H / dh)
    cc = p.get("crop_center") or [0.5, 0.5]
    ox = max(-(dw * cover - W) / 2, min((dw * cover - W) / 2, (0.5 - float(cc[0])) * dw * cover))
    oy = max(-(dh * cover - H) / 2, min((dh * cover - H) / 2, (0.5 - float(cc[1])) * dh * cover))
    src_frames = math.floor((pr.get("duration_s") or 0) * fps + 1e-6)
    fe = xb.file_el(vid, "video", round((pr.get("duration_s") or 0) * sfps), sfps, dw, dh)
    return (f'<clipitem id="{xb.clip_id()}"><name>{escape(ev["event_id"] + " · B-roll · " + vid.name)}</name>'
            f"<enabled>TRUE</enabled><duration>{src_frames}</duration>{rate(fps)}<start>{s}</start><end>{e}</end>"
            f"<in>{fin}</in><out>{fin + n}</out><pproTicksIn>{tin}</pproTicksIn><pproTicksOut>{tin + n * ticks_per_frame(fps)}"
            f"</pproTicksOut><alphatype>none</alphatype>{fe}{motion_filter(cover * 100, ox / W, oy / H)}</clipitem>")


def build_xml(paths: Paths, prefer_ae_renders: bool = True, native_graphics: bool = False,
              lanes: list | None = None) -> dict:
    """native_graphics=True (Premiere-only mode): the XML carries footage/punch-ins/dialogue/SFX and
    EMPTY graphic tracks; graphics + captions are placed inside Premiere by the WhyNot Cut Bridge (ppro-build)."""
    spec = read_json(paths.p("01_analysis/timeline-spec.json"))
    if not spec:
        raise FileNotFoundError("timeline-spec.json missing — run `reel plan` first")
    seq_cfg = load_config("sequence-settings.json")
    tpl = load_config("graphics-templates.json")
    pre = read_json(paths.p("00_inputs/preflight.json"))
    W, H = seq_cfg["general"]["frame_width"], seq_cfg["general"]["frame_height"]
    fps = seq_fps()          # 24, 25, 29.97 ... (frames below count real frames at this rate)
    TPF = ticks_per_frame(fps)
    main = Path(spec["main_footage"])
    if not main.is_absolute():
        main = paths.root / main
    mp = next((f for f in pre["files"] if Path(f["path"]).resolve() == main.resolve()), None)
    if mp is None:
        raise FileNotFoundError(f"{main} not in preflight — run `reel preflight` for it")
    v = mp["video"]
    src_fps = v["fps"]
    src_dur_s = mp["duration_s"]
    base_scale = spec.get("base_scale_percent") or min(W / v["display_width"], H / v["display_height"]) * 100
    dur = spec["duration_frames"]
    xb = XB()
    missing, used_media = [], []

    # ---------------- V01 main footage (split at camera points) + A01 dialogue
    v1, a1, a2, o1, o2 = [], [], [], [], []
    vcut, cut_bg = [], []       # source cutaways: the card whole on its own track over a (blurred) cover copy on V1
    src_frames_seq = math.floor(src_dur_s * fps + 1e-6)
    clean = paths.p("06_audio/dialogue/dialogue_clean.wav")
    use_clean = clean.exists() and spec.get("use_clean_dialogue", True)
    off_ms = float(spec.get("source_in_ms") or 0)   # a reel cut from a longer file: camera clips point into the original
    for i, seg in enumerate(spec["main_segments"]):
        s, e = seg["start_frame"], seg["end_frame"]
        if e <= s:
            continue
        sin_ms = seg.get("src_in_ms", s * 1000 / fps)
        tin = round((sin_ms + off_ms) * TPS / 1000)
        tout = tin + (e - s) * TPF
        fin = round((sin_ms + off_ms) * fps / 1000)
        fout = fin + (e - s)
        # the cleaned dialogue was extracted from the range: its clock starts at the in-point
        dtin, dfin = (round(sin_ms * TPS / 1000), round(sin_ms * fps / 1000)) if use_clean else (tin, fin)
        dtout, dfout = dtin + (e - s) * TPF, dfin + (e - s)
        vid, aidL, aidR = xb.clip_id(), xb.clip_id(), xb.clip_id()
        scale = base_scale * seg["scale_factor"]
        cx = (seg["offset_x"] + spec.get("base_offset_x", 0.0)) / W
        cy = (seg["offset_y"] + spec.get("base_offset_y", 0.0)) / H
        fe = xb.file_el(main, "video", round(src_dur_s * src_fps), src_fps, v["display_width"], v["display_height"], audio_ch=2)
        if seg.get("decision_id") == "AUTO_CUTAWAY":
            # the whole card goes on the cutaway track; V1 keeps a cover-framed copy as the background (the bridge blurs
            # it in Premiere), like an editor's "fit + blurred fill" for a 16:9 card in a 9:16 reel
            cut_id = xb.clip_id()
            vcut.append(f'<clipitem id="{cut_id}"><name>{escape(main.name)} [source cutaway, whole]</name><enabled>TRUE</enabled>'
                        f"<duration>{src_frames_seq}</duration>{rate(fps)}<start>{s}</start><end>{e}</end>"
                        f"<in>{fin}</in><out>{fout}</out><pproTicksIn>{tin}</pproTicksIn><pproTicksOut>{tout}</pproTicksOut>"
                        f'<alphatype>none</alphatype><file id="{xb.files[str(main)]}"/>'
                        f"{motion_filter(scale, cx, cy)}</clipitem>")
            cut_bg.append(len(v1))
            scale = base_scale
            cx, cy = spec.get("base_offset_x", 0.0) / W, spec.get("base_offset_y", 0.0) / H
        name = f"{main.name} [{seg['camera']}{' ' + seg['decision_id'] if seg.get('decision_id') else ''}]"
        links = (f"<link><linkclipref>{vid}</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>{i+1}</clipindex></link>"
                 f"<link><linkclipref>{aidL}</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>{i+1}</clipindex><groupindex>1</groupindex></link>"
                 f"<link><linkclipref>{aidR}</linkclipref><mediatype>audio</mediatype><trackindex>2</trackindex><clipindex>{i+1}</clipindex><groupindex>1</groupindex></link>")
        v1.append(f'<clipitem id="{vid}"><name>{escape(name)}</name><enabled>TRUE</enabled>'
                  f"<duration>{src_frames_seq}</duration>{rate(fps)}<start>{s}</start><end>{e}</end>"
                  f"<in>{fin}</in><out>{fout}</out><pproTicksIn>{tin}</pproTicksIn><pproTicksOut>{tout}</pproTicksOut>"
                  f"<alphatype>none</alphatype>{fe}{motion_filter(scale, cx, cy)}{links}</clipitem>")
        # A1/A2: cleaned dialogue (same clock as the camera file -> identical in/out) linked to the picture
        dfile = clean if use_clean else main
        dfe = xb.file_el(clean, "audio", round(src_dur_s * fps), fps, audio_ch=2) if use_clean else f'<file id="{xb.files[str(main)]}"/>'
        for aid, ch, lst, fel in ((aidL, 1, a1, dfe), (aidR, 2, a2, f'<file id="{xb.files[str(dfile)]}"/>')):
            lst.append(f'<clipitem id="{aid}" premiereChannelType="mono"><name>{escape(dfile.name)}</name><enabled>TRUE</enabled>'
                       f"<duration>{src_frames_seq}</duration>{rate(fps)}<start>{s}</start><end>{e}</end>"
                       f"<in>{dfin}</in><out>{dfout}</out><pproTicksIn>{dtin}</pproTicksIn><pproTicksOut>{dtout}</pproTicksOut>"
                       f"{fel}<sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack>"
                       f"{links}</clipitem>")
        if use_clean:  # original camera audio kept, DISABLED, for A/B (A7/A8)
            for ch, lst in ((1, o1), (2, o2)):
                oid = xb.clip_id()
                lst.append(f'<clipitem id="{oid}" premiereChannelType="mono"><name>ORIGINAL camera audio ch{ch} (muted A/B)</name>'
                           f"<enabled>FALSE</enabled><duration>{src_frames_seq}</duration>{rate(fps)}<start>{s}</start><end>{e}</end>"
                           f"<in>{fin}</in><out>{fout}</out><pproTicksIn>{tin}</pproTicksIn><pproTicksOut>{tout}</pproTicksOut>"
                           f'<file id="{xb.files[str(main)]}"/><sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack></clipitem>')
    used_media.append(str(main))
    if use_clean:
        used_media.append(str(clean))

    # ---------------- graphic tracks
    tracks = {k: [] for k in tpl["track_order_bottom_to_top"] if k != "V01"}
    # licensed B-roll VIDEOS are real clips in the XML (video only: no audio item, so dialogue can't be overwritten),
    # in native mode on the "broll" lane, otherwise on the template's track
    lane_items = {}
    for ev in spec["events"]:
        if ev["template"] != "broll_video":
            continue
        item = broll_clipitem(xb, ev, paths, W, H, fps)
        if item is None:
            missing.append(ev["event_id"])
            continue
        used_media.append(str(paths.root / ev["params"]["video"]))
        if native_graphics:
            lane_items.setdefault("broll", []).append(item)
        else:
            tracks.setdefault(ev["track"], []).append(item)
    for ev in ([] if native_graphics else spec["events"]):
        if ev["template"] == "broll_video":
            continue
        n = ev["end_frame"] - ev["start_frame"]
        ae = paths.p(f"04_after_effects/compositions/{ev['event_id']}.mov")
        cat = still_category(ev["template"])
        png = paths.p(f"03_broll/{cat}/{ev['event_id']}.png")
        if prefer_ae_renders and ae.exists():
            media, kind, tb = ae, "video", fps
        elif png.exists():
            media, kind, tb = png, "still", fps
        else:
            missing.append(ev["event_id"])
            continue
        used_media.append(str(media))
        cid = xb.clip_id()
        fe = xb.file_el(media, kind, n if kind == "video" else 86400, tb, W, H)
        tracks.setdefault(ev["track"], []).append(
            f'<clipitem id="{cid}"><name>{escape(ev["event_id"] + " · " + ev["template"])}</name><enabled>TRUE</enabled>'
            f"<duration>{n if kind == 'video' else 86400}</duration>{rate(fps)}<start>{ev['start_frame']}</start>"
            f"<end>{ev['end_frame']}</end><in>0</in><out>{n}</out>"
            f"<alphatype>{'straight' if kind == 'still' else 'straight'}</alphatype>{fe}{motion_filter(100.0)}</clipitem>")

    # captions overlay (single AE render spanning the video) if present
    cap = paths.p("04_after_effects/compositions/CAPTIONS.mov")
    if cap.exists() and not native_graphics and prefer_ae_renders:
        cid = xb.clip_id()
        tracks.setdefault("C02", []).append(
            f'<clipitem id="{cid}"><name>CAPTIONS · animated</name><enabled>TRUE</enabled><duration>{dur}</duration>'
            f"{rate(fps)}<start>0</start><end>{dur}</end><in>0</in><out>{dur}</out><alphatype>straight</alphatype>"
            f"{xb.file_el(cap, 'video', dur, fps, W, H)}{motion_filter(100.0)}</clipitem>")
        used_media.append(str(cap))

    # ---------------- audio cues
    cues = read_json(paths.p("06_audio/audio-cue-sheet.json"), {"cues": []})["cues"]
    atracks = {}
    last_end = {}
    for c in cues:
        f = paths.p(c["source_file"])
        if not f.exists():
            missing.append(c["cue_id"])
            continue
        secs = audio_duration(f)
        n = max(1, math.ceil(secs * fps))
        tr = c["track"]
        s = c["start_frame"]
        if last_end.get(tr, -1) > s:  # avoid overlap on the same track -> push to A03
            tr = "A03" if tr != "A03" else "A05"
        last_end[tr] = s + n
        gain = c.get("gain_db", -14)
        lvl = 10 ** (gain / 20)
        fe = xb.file_el(f, "audio", n, fps, audio_ch=2)
        idL, idR = xb.clip_id(), xb.clip_id()
        lv = (f"<filter><effect><name>Audio Levels</name><effectid>audiolevels</effectid><effectcategory>audiolevels</effectcategory>"
              f"<effecttype>audiolevels</effecttype><mediatype>audio</mediatype><parameter><parameterid>level</parameterid>"
              f"<name>Level</name><valuemin>0</valuemin><valuemax>3.98109</valuemax><value>{lvl:.5f}</value></parameter></effect></filter>")
        pair = atracks.setdefault(tr, ([], []))
        k = len(pair[0]) + 1
        # absolute track numbers are only known after ordering -> placeholders, resolved below
        links = (f"<link><linkclipref>{idL}</linkclipref><mediatype>audio</mediatype><trackindex>__TL_{tr}__</trackindex><clipindex>{k}</clipindex><groupindex>1</groupindex></link>"
                 f"<link><linkclipref>{idR}</linkclipref><mediatype>audio</mediatype><trackindex>__TR_{tr}__</trackindex><clipindex>{k}</clipindex><groupindex>1</groupindex></link>")
        for cid, ch, lst, fel in ((idL, 1, pair[0], fe), (idR, 2, pair[1], f'<file id="{xb.files[str(f)]}"/>')):
            lst.append(f'<clipitem id="{cid}" premiereChannelType="mono"><name>{escape(c["cue_id"])}</name><enabled>TRUE</enabled>'
                       f"<duration>{n}</duration>{rate(fps)}<start>{s}</start><end>{s + n}</end><in>0</in><out>{n}</out>"
                       f"{fel}<sourcetrack><mediatype>audio</mediatype><trackindex>{ch}</trackindex></sourcetrack>{lv}{links}</clipitem>")
        used_media.append(str(f))

    # ---------------- markers (every decision/event, for the editor)
    markers = []
    for ev in spec["events"]:
        markers.append(f"<marker><name>{escape(ev['event_id'])}</name><comment>{escape(ev['template'] + ' | ' + (ev.get('evidence') or '')[:180])}</comment>"
                       f"<in>{ev['start_frame']}</in><out>-1</out></marker>")
    if spec.get("music", {}).get("status") != "PLACED":
        for m in spec.get("music", {}).get("cue_points", []):
            markers.append(f"<marker><name>MUSIC: {escape(m.get('label', 'cue'))}</name><comment>{escape(m.get('note', ''))}</comment>"
                           f"<in>{m['frame']}</in><out>-1</out></marker>")

    def vtrack(items, name):
        return f"<track><enabled>TRUE</enabled><locked>FALSE</locked>{''.join(items)}</track>"

    # Premiere 26.5 silently skips audio <track>s that lack its own track attributes (found by bisecting
    # against seq.exportAsFinalCutProXML output); copy them verbatim.
    ATTRS = ('TL.SQTrackAudioKeyframeStyle="0" TL.SQTrackShy="0" TL.SQTrackExpandedHeight="41" TL.SQTrackExpanded="0" '
             'MZ.TrackTargeted="1" PannerCurrentValue="0.5" PannerIsInverted="true" '
             'PannerStartKeyframe="-91445760000000000,0.5,0,0,0,0,0,0" PannerName="Balance" '
             'currentExplodedTrackIndex="0" totalExplodedTrackCount="1" premiereTrackType="Stereo"')

    def atrack(items, outch):
        return (f'<track {ATTRS}>{"".join(items)}<enabled>TRUE</enabled><locked>FALSE</locked>'
                f"<outputchannelindex>{outch}</outputchannelindex></track>")

    vorder = [("V01", v1)] + ([("VCUT", vcut)] if vcut else []) +         [(k, tracks.get(k, [])) for k in tpl["track_order_bottom_to_top"] if k != "V01"]
    if native_graphics:   # keep the graphic layers as empty, ordered tracks for the bridge to fill
        vorder = [("V01", v1)] + ([("VCUT", vcut)] if vcut else []) +             [(k, lane_items.get(k, [])) for k in (lanes or NATIVE_GFX_TRACKS)]
    else:
        vorder = [(k, it) for k, it in vorder if it]  # no empty tracks
    aorder = [("A01", (a1, a2))] + [(k, atracks[k]) for k in ("A03", "A04", "A05", "A06") if atracks.get(k)]
    if o1:
        aorder.append(("A07", (o1, o2)))
    seq_name = f"{paths.video_id}_{project_prefix()}_EDIT"
    trackno = {k: (2 * i + 1, 2 * i + 2) for i, (k, _) in enumerate(aorder)}
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">'
           f'<sequence id="sequence-1"><uuid>{uuid.uuid5(uuid.NAMESPACE_URL, seq_name)}</uuid><name>{escape(seq_name)}</name>'
           f"<duration>{dur}</duration>{rate(fps)}"
           f"<timecode>{rate(fps)}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>"
           "<media><video><format><samplecharacteristics>"
           f"{rate(fps)}<width>{W}</width><height>{H}</height><anamorphic>FALSE</anamorphic>"
           "<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance><colordepth>24</colordepth>"
           "</samplecharacteristics></format>"
           + "".join(vtrack(it, k) for k, it in vorder) +
           "</video><audio><numOutputChannels>2</numOutputChannels><format><samplecharacteristics>"
           "<depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format>"
           "<outputs><group><index>1</index><numchannels>1</numchannels><downmix>0</downmix><channel><index>1</index></channel></group>"
           "<group><index>2</index><numchannels>1</numchannels><downmix>0</downmix><channel><index>2</index></channel></group></outputs>"
           + "".join(atrack(L, 1) + atrack(R, 2) for k, (L, R) in aorder) +
           "</audio></media>" + "".join(markers) + "</sequence></xmeml>\n")
    for k, (l, r) in trackno.items():
        xml = xml.replace(f"__TL_{k}__", str(l)).replace(f"__TR_{k}__", str(r))
    assert "__TL_" not in xml and "__TR_" not in xml
    out = paths.p(f"07_premiere/interchange/{seq_name}{'_base' if native_graphics else ''}.xml")
    write_text(out, xml)
    track_map = {"video": [{"xml_index": i + 1, "id": k, "name": tpl["track_names"].get(k, k), "clips": len(it)}
                           for i, (k, it) in enumerate(vorder)],
                 "audio": [{"xml_index": f"{2 * i + 1}-{2 * i + 2}", "id": k, "name": tpl["audio_tracks"].get(k, k) + " (L/R mono pair)",
                            "clips": len(it[0])} for i, (k, it) in enumerate(aorder)]}
    tm = {"generated": now_iso(), "xml": str(out), "sequence_name": seq_name, "fps": fps,
          "mode": "premiere_native_graphics" if native_graphics else "rendered_graphics_in_xml",
          "frame_size": [W, H], "duration_frames": dur, "duration_tc": frame_to_tc(dur),
          "source_fps": v["fps"], "base_scale_percent": round(base_scale, 3),
          "tracks": track_map, "media": sorted(set(used_media)), "missing_events": missing,
          "markers": len(markers),
          "cutaways": {"track": "VCUT" if vcut else None, "blur_v1_clip_indices": cut_bg},
          "captions": {"srt": str(paths.p("02_transcription/subtitles.srt")),
                       "how": "File > Import the SRT, drag onto the sequence -> Premiere creates the caption track (C01)."},
          "note": "Premiere ignores track names from XML; use this map (xml_index -> role)."}
    write_json(paths.p("07_premiere/" + ("base-manifest.json" if native_graphics else "timeline-manifest.json")), tm)
    write_json(paths.p("07_premiere/sequence-settings.json"), seq_cfg)
    return tm
