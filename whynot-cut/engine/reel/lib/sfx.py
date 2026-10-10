"""Procedural, original sound effects (no third-party samples -> no licensing questions).

Used only when no approved SFX library is supplied in data/ (role 'sfx'). Each cue kind maps
to a short 48 kHz / 24-bit stereo WAV synthesized with ffmpeg filters. Music is NEVER
synthesized or invented: without supplied/licensed music the music track holds markers only.
"""
from __future__ import annotations

from pathlib import Path

from .common import ffmpeg_exe, run

RECIPES = {
    # kind: (lavfi source graph, duration_s, description)
    "whoosh": ("anoisesrc=c=pink:r=48000:d=0.7:a=0.9,highpass=f=250,lowpass=f=5200,"
               "volume='if(lt(t,0.32),pow(t/0.32,2),exp(-(t-0.32)*9))':eval=frame", 0.7,
               "airy pink-noise swell for full-screen B-roll / transitions"),
    "whoosh_soft": ("anoisesrc=c=pink:r=48000:d=0.55:a=0.6,highpass=f=400,lowpass=f=2600,"
                    "volume='if(lt(t,0.22),pow(t/0.22,2),exp(-(t-0.22)*10))':eval=frame", 0.55,
                    "gentle swell for cards / overlays"),
    "pop": ("aevalsrc='0.8*sin(2*PI*(380+900*exp(-t*40))*t)*exp(-t*28)':s=48000:d=0.18", 0.18,
            "soft tonal pop for title reveals"),
    "click": ("aevalsrc='0.6*sin(2*PI*2200*t)*exp(-t*160)+0.25*(random(0)*2-1)*exp(-t*400)':s=48000:d=0.07", 0.07,
              "crisp UI click for term callouts"),
    "tick": ("aevalsrc='0.5*sin(2*PI*1600*t)*exp(-t*70)':s=48000:d=0.1", 0.1,
             "light tick for checklist items"),
    "riser_soft": ("aevalsrc='0.35*sin(2*PI*(220+380*t)*t)*min(1,t/1.2)*if(gt(t,1.3),exp(-(t-1.3)*12),1)':s=48000:d=1.6,"
                   "lowpass=f=3000", 1.6, "subtle tonal rise into outro"),
    "hit_soft": ("aevalsrc='0.9*sin(2*PI*70*t)*exp(-t*9)+0.2*(random(0)*2-1)*exp(-t*35)':s=48000:d=0.6,lowpass=f=1800", 0.6,
                 "low soft impact for a strong statement (use sparingly)"),
    "shimmer": ("aevalsrc='0.18*(sin(2*PI*2637*t)+sin(2*PI*3136*t)+sin(2*PI*3951*t))*exp(-t*5)*(0.6+0.4*sin(2*PI*14*t))':s=48000:d=0.9", 0.9,
                "light sparkle for logo/CTA"),
}


def synth(kind: str, out: Path) -> Path:
    if kind not in RECIPES:
        raise KeyError(f"unknown sfx kind {kind}")
    src, dur, _ = RECIPES[kind]
    out.parent.mkdir(parents=True, exist_ok=True)
    run([ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", src,
         "-t", str(dur), "-af", "aformat=channel_layouts=stereo,alimiter=limit=0.7",
         "-ar", "48000", "-c:a", "pcm_s24le", str(out)])
    return out


def synth_needed(kinds: set[str], out_dir: Path) -> dict:
    res = {}
    for k in sorted(kinds):
        p = out_dir / f"{k}.wav"
        if not p.exists():
            synth(k, p)
        res[k] = {"file": str(p), "duration_s": RECIPES[k][1], "description": RECIPES[k][2],
                  "license": "original procedural synthesis by this pipeline — no third-party material"}
    return res
