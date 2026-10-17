# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Regenerate the burned-in caption fixtures (Phase 4 Task 24, R-4.2): small synthetic clips made with FFmpeg
`drawtext` / `drawbox` over a moving gradient (no client footage), each with the words.json of its "speech".

    python make_fixtures.py [ffmpeg]        (default: the engine's ffmpeg, lib.common.ffmpeg_exe)

Fonts: the repo's own IBM Plex Sans Arabic and Inter (OFL), so the clips do not depend on the machine. The text
shaping of Arabic needs an FFmpeg built with libharfbuzz + libfribidi (the engine's pinned 7.1 is).
Speech schedule (12 s): words every 0.4 s from 0.5 s to 5.3 s, a pause until 8.5 s, words again to 11.3 s. Burned
captions are groups of THREE words (another tool's grouping, not ours), shown from the first word to the last.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
FONT_AR = REPO / "adobe" / "panel-ui" / "fonts" / "ibmplexsansarabic" / "IBMPlexSansArabic-SemiBold.ttf"
FONT_EN = REPO / "adobe" / "panel-ui" / "fonts" / "inter" / "Inter-Regular.ttf"
W, H, FPS, DUR = 640, 360, 15, 12.0

EN = ("today we talk about sleep and why the body needs it every night to repair the brain and the heart "
      "so let us start with the basics of a good night").split()
AR = ("النهارده هنتكلم عن النوم وليه الجسم محتاجه كل ليلة عشان يصلح المخ والقلب وكمان المناعة "
      "فخلينا نبدأ بالأساسيات بتاعة الليلة الحلوة والراحة").split()


def schedule(words: list, dur: float = DUR) -> list:
    """[(word, start_s, end_s)]: 0.4 s per word in [0.5, 5.3) and [8.5, 11.3) (a long pause between)."""
    out, i = [], 0
    for a, b in ((0.5, 5.3), (8.5, 11.3)):
        t = a
        while t + 0.35 <= min(b, dur - 0.2) and i < len(words):
            out.append((words[i], round(t, 2), round(t + 0.35, 2)))
            t += 0.4
            i += 1
    return out


def words_json(sched: list) -> dict:
    return {"words": [{"id": k + 1, "word": w, "start_ms": int(a * 1000), "end_ms": int(b * 1000), "probability": 0.95}
                      for k, (w, a, b) in enumerate(sched)]}


def cues(sched: list, n: int = 3) -> list:
    out = []
    for k in range(0, len(sched), n):
        g = sched[k:k + n]
        gap_split = [g[0]]
        for x in g[1:]:                                   # never one cue across the pause
            if x[1] - gap_split[-1][2] > 1.0:
                break
            gap_split.append(x)
        out.append((" ".join(w for w, _, _ in gap_split), gap_split[0][1], gap_split[-1][2] + 0.05))
        rest = g[len(gap_split):]
        if rest:
            out.append((" ".join(w for w, _, _ in rest), rest[0][1], rest[-1][2] + 0.05))
    return out


def background() -> str:
    # a slowly moving gradient and a moving "head" (a soft box): motion without any text-like strokes
    return (f"gradients=s={W}x{H}:r={FPS}:c0=0x2b4a6f:c1=0x8a6d4f:c2=0x3d6b4f:speed=0.015:d={DUR},"
            f"drawbox=x='220+40*sin(t)':y=70:w=200:h=240:color=0xd0b090@0.9:t=fill")


def caption_filters(tmp: Path, cue_list: list, font: str, y_expr: str, size: int = 24, tag: str = "c") -> list:
    fs = []
    for k, (text, a, b) in enumerate(cue_list):
        tf = f"{tag}_cue{k:02d}.txt"
        (tmp / tf).write_text(text, encoding="utf-8")
        fs.append(f"drawtext=fontfile={font}:textfile={tf}:fontsize={size}:fontcolor=white:borderw=2:bordercolor=black"
                  f":x=(w-text_w)/2:y={y_expr}:enable='between(t,{a},{b})'")
    return fs


def build(ff: str, name: str, tmp: Path, filters: list, dur: float = DUR, vfr: bool = False, black: bool = False):
    src = f"color=c=black:s={W}x{H}:r={FPS}:d={dur}" if black else background().replace(f"d={DUR}", f"d={dur}")
    vf = ",".join(filters) if filters else "null"
    args = [ff, "-v", "error", "-y", "-f", "lavfi", "-i", src, "-vf", vf]
    if vfr:     # drop 2 of every 3 frames in the first half: a variable frame rate file
        args[-1] = vf + r",select='not(lt(t\,6))+not(mod(n\,3))'"
        args += ["-fps_mode", "vfr"]
    args += ["-t", str(dur), "-c:v", "libx264", "-preset", "veryslow", "-crf", "34", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", f"{name}.mp4"]
    subprocess.run(args, cwd=tmp, check=True, capture_output=True)
    shutil.copyfile(tmp / f"{name}.mp4", HERE / f"{name}.mp4")


def main(ff: str | None = None):
    if ff is None:
        sys.path.insert(0, str(REPO / "whynot-cut" / "engine" / "reel"))
        from lib.common import ffmpeg_exe
        ff = ffmpeg_exe()
    tmp = Path(tempfile.mkdtemp(prefix="wnc-burned-"))
    try:
        shutil.copyfile(FONT_AR, tmp / "ar.ttf")
        shutil.copyfile(FONT_EN, tmp / "en.ttf")
        en, ar = schedule(EN), schedule(AR)
        bottom, top = "h*0.80", "h*0.06"
        specs = {
            "en_bottom": (en, caption_filters(tmp, cues(en), "en.ttf", bottom, tag="enb")),
            "ar_bottom": (ar, caption_filters(tmp, cues(ar), "ar.ttf", bottom, tag="arb")),
            "en_top": (en, caption_filters(tmp, cues(en), "en.ttf", top, tag="ent")),
            "lower_third": (en, ["drawbox=x=40:y=ih*0.70:w=360:h=ih*0.13:color=black@0.65:t=fill:enable='between(t,2,7)'",
                                 "drawtext=fontfile=en.ttf:text='Dr. Sample Name':fontsize=26:fontcolor=white"
                                 ":x=56:y=h*0.72:enable='between(t,2,7)'"]),
            "logo": (en, ["drawbox=x=iw-110:y=12:w=96:h=34:color=0x10306a@0.9:t=fill",
                          "drawtext=fontfile=en.ttf:text='WNC TV':fontsize=20:fontcolor=white:x=w-100:y=18"]),
            "watermark": (en, ["drawtext=fontfile=en.ttf:text='SAMPLE  PREVIEW':fontsize=44:fontcolor=white@0.35"
                               ":x=(w-text_w)/2:y=h*0.74"]),
            "ticker": (en, ["drawbox=x=0:y=ih*0.88:w=iw:h=ih*0.10:color=black@0.7:t=fill",
                            "drawtext=fontfile=en.ttf:text='BREAKING  markets open higher  weather sunny  sports "
                            "tonight  more news at nine':fontsize=22:fontcolor=white:x=w-mod(t*90\\,w+text_w):y=h*0.895"]),
            "clean": (en, []),
        }
        for name, (sched, fl) in specs.items():
            build(ff, name, tmp, fl)
            (HERE / f"{name}.words.json").write_text(json.dumps(words_json(sched), ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
        build(ff, "black", tmp, [], black=True)
        (HERE / "black.words.json").write_text(json.dumps(words_json(en), indent=1), encoding="utf-8")
        short = [x for x in en if x[2] <= 2.0]
        build(ff, "short_2s", tmp, caption_filters(tmp, cues(short), "en.ttf", bottom, tag="short"), dur=2.0)
        (HERE / "short_2s.words.json").write_text(json.dumps(words_json(short), indent=1), encoding="utf-8")
        build(ff, "vfr", tmp, caption_filters(tmp, cues(en), "en.ttf", bottom, tag="vfr"), vfr=True)
        (HERE / "vfr.words.json").write_text(json.dumps(words_json(en), indent=1), encoding="utf-8")
        hard(ff, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- the harder set (review round 1)
LONG_EN = (EN * 3)


def continuous(words: list, dur: float, gap_every: int = 6, gap: float = 0.5) -> list:
    """Continuous speech: 0.4 s per word, a short breath (gap s, never a long pause) every gap_every words."""
    out, t, i = [], 0.4, 0
    while t + 0.35 <= dur - 0.3 and i < len(words):
        out.append((words[i], round(t, 2), round(t + 0.35, 2)))
        i += 1
        t += 0.4 + (gap if i % gap_every == 0 else 0.0)
    return out


def with_pause(words: list, dur: float, pause=(9.0, 12.5)) -> list:
    return [x for x in continuous(words, dur) if not (pause[0] - 0.4 < x[1] < pause[1])]


def build_sized(ff: str, name: str, tmp: Path, filters: list, dur: float, w: int, h: int):
    src = (f"gradients=s={w}x{h}:r={FPS}:c0=0x2b4a6f:c1=0x8a6d4f:c2=0x3d6b4f:speed=0.015:d={dur},"
           f"drawbox=x='{w // 3}+{w // 16}*sin(t)':y={h // 5}:w={w // 3}:h={h * 2 // 3}:color=0xd0b090@0.9:t=fill")
    args = [ff, "-v", "error", "-y", "-f", "lavfi", "-i", src, "-vf", ",".join(filters) if filters else "null",
            "-t", str(dur), "-c:v", "libx264", "-preset", "veryslow", "-crf", "34", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", f"{name}.mp4"]
    subprocess.run(args, cwd=tmp, check=True, capture_output=True)
    shutil.copyfile(tmp / f"{name}.mp4", HERE / f"{name}.mp4")


def hard(ff: str, tmp: Path):
    """Continuous speech (no long pause), other tools' groupings, long two-line cues, small text on a vertical frame,
    swapping name supers, a ticker over continuous speech, a short clip without a pause."""
    def save(name, sched):
        (HERE / f"{name}.words.json").write_text(json.dumps(words_json(sched), ensure_ascii=False, indent=1), encoding="utf-8")
    cont = continuous(LONG_EN, 20.0)
    build(ff, "cont_bottom", tmp, caption_filters(tmp, cues(cont, 5), "en.ttf", "h*0.80", tag="cont"), dur=20.0)
    save("cont_bottom", cont)
    build(ff, "karaoke", tmp, caption_filters(tmp, cues(cont, 1), "en.ttf", "h*0.80", tag="kara"), dur=20.0)
    save("karaoke", cont)
    pz = with_pause(LONG_EN, 20.0)
    two, runs, cur = [], [], []
    for x in pz:                                # never one cue across the pause
        if cur and x[1] - cur[-1][2] > 1.0:
            runs.append(cur)
            cur = []
        cur.append(x)
    runs.append(cur)
    for run in runs:  # never one cue across the pause
        for k in range(0, len(run), 10):      # two lines of five words, about 4 s on screen each
            g = run[k:k + 10]
            if g:
                text = " ".join(w for w, _, _ in g[:5]) + ("\n" + " ".join(w for w, _, _ in g[5:]) if g[5:] else "")
                two.append((text, g[0][1], g[-1][2] + 0.05))
    fl = []
    for k, (text, a, b) in enumerate(two):
        (tmp / f"long_cue{k:02d}.txt").write_text(text, encoding="utf-8")
        fl.append(f"drawtext=fontfile=en.ttf:textfile=long_cue{k:02d}.txt:fontsize=20:fontcolor=white:borderw=2"
                  f":bordercolor=black:line_spacing=-10:x=(w-text_w)/2:y=h*0.76:enable='between(t,{a},{b})'")
    build(ff, "long_cues", tmp, fl, dur=20.0)
    save("long_cues", pz)
    build_sized(ff, "small_vertical", tmp, caption_filters(tmp, cues(pz, 3), "en.ttf", "h*0.78", size=28, tag="vert"),
                20.0, 540, 960)
    save("small_vertical", pz)
    names = ["Dr. Sample Name", "Prof. Other Guest", "Host Name Here", "Dr. Fourth Person", "Guest Number Five",
             "Dr. Sixth Name"]
    fl = []
    for k, nm in enumerate(names):
        a, b = 0.5 + k * 3.5, 0.5 + (k + 1) * 3.5 - 0.05
        fl += [f"drawbox=x=30:y=ih*0.72:w=330:h=ih*0.12:color=black@0.65:t=fill:enable='between(t,{a},{b})'",
               f"drawtext=fontfile=en.ttf:text='{nm}':fontsize=24:fontcolor=white:x=44:y=h*0.74:enable='between(t,{a},{b})'"]
    build(ff, "lt_swaps", tmp, fl, dur=20.0)
    save("lt_swaps", cont)
    build(ff, "ticker_cont", tmp, ["drawbox=x=0:y=ih*0.88:w=iw:h=ih*0.10:color=black@0.7:t=fill",
                                   "drawtext=fontfile=en.ttf:text='BREAKING  markets open higher  weather sunny  sports "
                                   "tonight  more news at nine  traffic is light':fontsize=22:fontcolor=white"
                                   ":x=w-mod(t*90\\,w+text_w):y=h*0.895"], dur=20.0)
    save("ticker_cont", cont)
    short = continuous(EN, 8.0)
    build(ff, "short_cont", tmp, caption_filters(tmp, cues(short, 3), "en.ttf", "h*0.80", tag="shc"), dur=8.0)
    save("short_cont", short)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
