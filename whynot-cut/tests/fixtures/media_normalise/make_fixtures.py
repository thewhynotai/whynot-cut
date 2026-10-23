# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Regenerate the intake-normalisation fixtures (Phase 4 Task 26, R-4.4): tiny synthetic clips made with FFmpeg's
test sources (no client footage), 320x180, 2-3 s, each a frame-rate or colour case.

    python make_fixtures.py [ffmpeg]        (default: the engine's ffmpeg, lib.common.ffmpeg_exe)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SIZE = "320x180"
X264 = ["-c:v", "libx264", "-preset", "veryslow", "-crf", "30", "-pix_fmt", "yuv420p"]
AUDIO = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]


def src(rate: str, dur: float) -> list:
    return ["-f", "lavfi", "-i", f"testsrc2=size={SIZE}:rate={rate}:duration={dur}"]


def hdr(transfer: str, tag_trc: bool = True, npl: int = 100) -> list:
    """10-bit HEVC with BT.2020 primaries and the given transfer tag (or none); SDR white placed at `npl` nits."""
    params = "colorprim=bt2020:colormatrix=bt2020nc" + (f":transfer={transfer}" if tag_trc else "")
    conv = (f"zscale=tin=bt709:min=bt709:pin=bt709:t={transfer}:m=bt2020nc:p=bt2020:npl={npl},format=yuv420p10le"
            if tag_trc else "format=yuv420p10le")       # SDR white placed at 100 nits on the HDR curve (a real grade)
    out = ["-vf", conv, "-c:v", "libx265", "-preset", "fast", "-crf", "30", "-x265-params",
           params + ":log-level=error", "-color_primaries", "bt2020", "-colorspace", "bt2020nc", "-tag:v", "hvc1"]
    if tag_trc:
        out += ["-color_trc", transfer]
    return out


CASES = {
    "cfr30": src("30", 3) + AUDIO + ["-t", "3", *X264, "-c:a", "aac", "-shortest"],
    "tag60_real30": src("30", 3) + AUDIO + ["-t", "3", "-vf", "fps=60", *X264, "-r", "60", "-c:a", "aac", "-shortest"],
    "ntsc2997": src("30000/1001", 3) + ["-t", "3", *X264],
    "film23976": src("24000/1001", 3) + ["-t", "3", *X264],
    "film24": src("24", 3) + ["-t", "3", *X264],
    "pal50": src("50", 2) + ["-t", "2", *X264],
    "phone120": src("120", 2) + ["-t", "2", *X264],
    "vfr": src("30", 3) + AUDIO + ["-t", "3", "-vf", r"select='not(mod(n\,3))+between(n\,30\,55)'", "-fps_mode", "vfr",
                                   *X264, "-c:a", "aac", "-shortest"],
    "still": ["-f", "lavfi", "-i", f"color=c=0x335577:size={SIZE}:rate=30:duration=3", "-t", "3", *X264],
    "hdr_pq": src("30", 2) + ["-t", "2", *hdr("smpte2084")],
    "hdr_hlg": src("30", 2) + ["-t", "2", *hdr("arib-std-b67")],
    "pq_tag_8bit": src("30", 2) + ["-t", "2", *X264, "-x264-params",
                                   "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                                   "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc"],
    "untagged_10bit_bt2020": src("30", 2) + ["-t", "2", *hdr("smpte2084", tag_trc=False)],
    # review round 1: highlights at 1000 nits, 3:2 pulldown (24 in 60), a slow near-static true 60, a phone rotation
    "hdr_pq1000": src("30", 2) + ["-t", "2", *hdr("smpte2084", npl=1000)],
    "pulldown24_in60": src("24", 3) + ["-t", "3", "-vf", "fps=60", *X264, "-r", "60"],
    "slow60": ["-f", "lavfi", "-i", f"color=c=0x335577:size={SIZE}:rate=60:duration=3", "-t", "3", "-vf",
               "drawbox=x='20+t*12':y=60:w=40:h=40:color=white@1:t=fill", *X264],
    "sdr_ref": src("30", 2) + ["-t", "2", "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv420p"],
    # BL-26 r2: VFR at the NTSC rates (the copy's frame grid is not a whole number of ms), with sound
    "vfr2997": src("30000/1001", 3) + AUDIO + ["-t", "3", "-vf", r"select='not(mod(n\,3))+between(n\,30\,55)'",
                                               "-fps_mode", "vfr", *X264, "-c:a", "aac", "-shortest"],
    "vfr5994": src("60000/1001", 3) + AUDIO + ["-t", "3", "-vf", r"select='not(mod(n\,3))+between(n\,60\,110)'",
                                               "-fps_mode", "vfr", *X264, "-c:a", "aac", "-shortest"],
}


def main(ff: str | None = None):
    if ff is None:
        sys.path.insert(0, str(REPO / "whynot-cut" / "engine" / "reel"))
        from lib.common import ffmpeg_exe
        ff = ffmpeg_exe()
    for name, args in CASES.items():
        ext = ".mov" if name.startswith(("hdr", "untagged")) else ".mp4"
        subprocess.run([ff, "-v", "error", "-y", *args, str(HERE / f"{name}{ext}")], check=True, capture_output=True)
    # a phone clip with a 90-degree display rotation (display matrix side data, as ffmpeg 7 writes it)
    subprocess.run([ff, "-v", "error", "-y", "-display_rotation", "90", "-i", str(HERE / "cfr30.mp4"), "-c", "copy",
                    str(HERE / "rot90.mp4")], check=True, capture_output=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
