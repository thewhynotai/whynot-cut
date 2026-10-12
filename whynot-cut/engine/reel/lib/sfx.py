"""Procedural, original sound effects (no third-party samples -> no licensing questions).

Used when a cue kind is not mapped to an approved client SFX library file. Each cue kind maps
to a short 48 kHz / 24-bit stereo WAV synthesized with ffmpeg filters. Music is NEVER
synthesized or invented: without supplied/licensed music the music track holds markers only.

Client library (3.0 T2.7): `06_audio/sfx-map.json` maps a cue kind (any name the plan's `sound[].type` uses, or one of
the recipes below, which the library file then replaces) to a file of the client's folder:
    {"whoosh": "data/SFX/whoosh_01.mp3", "door_knock": {"file": "data/SFX/knock.wav", "note": "…"}}
The path is absolute or relative to the client folder; keys starting with "_" are notes. `reel sfx` converts each
mapped file to 06_audio/sfx/<kind>.wav (48 kHz / 24-bit stereo, like the synthesised cues) with <kind>.provenance.json
beside it. The client's assets/ and data/ are only read.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import wave
from pathlib import Path

from .common import ffmpeg_exe, now_iso, read_json, run, write_json
from .errors import Guidance

MAP_REL = "06_audio/sfx-map.json"
MAX_SOURCE_S = 30.0          # a cue is a short effect: a longer mapped file is almost surely the wrong one
CONVERT_TIMEOUT_S = 120      # ffmpeg limit for one file (a hung network path must not block `reel sfx`)
_KIND_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}

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
    run([ffmpeg_exe(), "-nostdin", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", src,
         "-t", str(dur), "-af", "aformat=channel_layouts=stereo,alimiter=limit=0.7",
         "-ar", "48000", "-c:a", "pcm_s24le", str(out)], timeout=CONVERT_TIMEOUT_S)
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


# --------------------------------------------------------------------------- the client library map (T2.7)
def check_kind_name(kind) -> str:
    """A cue kind becomes the file name <kind>.wav: letters, digits, '_' and '-' only (a letter or digit first, 64 characters
    at most, no Windows device name), so a map key can never point outside 06_audio/sfx. Anything else is Guidance."""
    if (not isinstance(kind, str) or not _KIND_RE.fullmatch(kind) or kind.lower() in _RESERVED):
        raise Guidance(f"{MAP_REL}: the SFX kind {kind!r} cannot be used as a file name",
                       "Use letters, digits, '_' or '-' only, starting with a letter or digit, up to 64 characters "
                       f"(for example \"whoosh_01\") — rename that key in {MAP_REL}", MAP_REL)
    return kind


def load_map(path: Path) -> dict:
    """{kind: entry} from 06_audio/sfx-map.json ({} when there is none). An entry is a path string or an object with
    `file`; "_" keys are notes. Anything else is guidance naming the file."""
    data = read_json(Path(path), {})
    if not isinstance(data, dict):
        raise Guidance(f"{MAP_REL} must be a JSON object {{\"kind\": \"path to the client's sound file\"}}",
                       f"Rewrite {path} as an object, for example {{\"whoosh\": \"data/SFX/whoosh_01.mp3\"}}",
                       str(path))
    out = {}
    for kind, entry in data.items():
        if str(kind).startswith("_"):
            continue
        check_kind_name(kind)
        ok = (isinstance(entry, str) and entry.strip()) or (isinstance(entry, dict) and isinstance(entry.get("file"), str)
                                                              and entry["file"].strip())
        if not ok:
            raise Guidance(f"{MAP_REL}: the entry for '{kind}' must be a file path or an object with \"file\"",
                           f"Fix '{kind}' in {path}: \"{kind}\": \"data/SFX/<file>\"", str(path))
        out[str(kind)] = entry
    return out


def valid_kinds(sfx_map: dict) -> list[str]:
    """Every cue kind a plan may use: the procedural recipes plus the mapped client kinds, sorted."""
    return sorted(set(RECIPES) | set(sfx_map or {}))


def _entry_file(entry) -> str:
    return (entry if isinstance(entry, str) else entry["file"]).strip()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_seconds(path: Path) -> float | None:
    """Duration of a media file via the engine's probe (None when it cannot tell: ffmpeg then reports the real problem)."""
    try:
        from .media import probe
        d = probe(path).get("duration_s")
        return float(d) if d else None
    except Exception:
        return None


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return round(w.getnframes() / float(w.getframerate()), 3)


def install_mapped(kind: str, entry, root: Path, out_dir: Path) -> dict:
    """Convert the client's library file for `kind` to out_dir/<kind>.wav (48 kHz, 24-bit stereo, like synth) and write
    out_dir/<kind>.provenance.json (source path, sha256, converted_at, the map entry). Reused when the source's sha256
    matches the recorded one. A missing or unreadable file is Guidance; nothing is left behind then."""
    check_kind_name(kind)
    rel = _entry_file(entry)
    src = Path(rel).expanduser()
    src = (src if src.is_absolute() else Path(root) / src).resolve()
    if not src.is_file():
        raise Guidance(f"SFX '{kind}' is mapped to {rel}, which does not exist (looked for {src})",
                       f"Put the file there, or fix the '{kind}' entry in {MAP_REL}, or remove it to use the "
                       f"built-in sound", MAP_REL)
    out = Path(out_dir) / f"{kind}.wav"
    prov_p = Path(out_dir) / f"{kind}.provenance.json"
    digest = _sha256(src)
    prev = read_json(prov_p, {}) if prov_p.exists() else {}
    if out.exists() and isinstance(prev, dict) and prev.get("sha256") == digest and prev.get("source") == str(src):
        return {"file": str(out), "duration_s": _wav_seconds(out), "provenance": str(prov_p), "reused": True}
    secs = _source_seconds(src)
    if secs is not None and secs > MAX_SOURCE_S:
        raise Guidance(f"SFX '{kind}' is mapped to {src.name}, which is {secs:.0f} s long (a sound effect is at most "
                       f"{MAX_SOURCE_S:.0f} s)",
                       f"Map '{kind}' to the short effect file in {MAP_REL} (or trim {src.name} first)", str(src))
    exe = ffmpeg_exe()
    if not exe:
        raise Guidance("ffmpeg is not available, so the client's SFX files cannot be converted",
                       "Run `reel setup` to install the engine's ffmpeg, then run `reel sfx` again")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    tmp = Path(out_dir) / f".{kind}.converting.wav"
    try:
        try:
            run([exe, "-nostdin", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vn", "-af",
                 "aformat=channel_layouts=stereo", "-ar", "48000", "-c:a", "pcm_s24le", str(tmp)],
                timeout=CONVERT_TIMEOUT_S)
        except subprocess.TimeoutExpired as e:
            raise Guidance(f"SFX '{kind}': converting {src.name} took more than {CONVERT_TIMEOUT_S} s and was stopped",
                           f"Check that {src} opens (a file on a slow or disconnected network drive can hang), copy it "
                           "to the client folder, or map a shorter file", str(src)) from e
        except (subprocess.CalledProcessError, OSError) as e:
            raise Guidance(f"SFX '{kind}': ffmpeg could not read {src.name} as audio "
                           f"({(getattr(e, 'stderr', '') or str(e)).strip()[:200]})",
                           f"Replace the file or fix the '{kind}' entry in {MAP_REL}", str(src)) from e
        try:
            tmp.replace(out)
        except OSError as e:                 # on Windows: Premiere / After Effects / a player holds the old wav open
            raise Guidance(f"SFX '{kind}': cannot replace {out.name} — the file is in use ({e})",
                           "Close the Premiere project (and any player) that has the file open, then run `reel sfx` "
                           "again", str(out)) from e
    finally:
        tmp.unlink(missing_ok=True)
    write_json(prov_p, {"kind": kind, "source": str(src), "sha256": digest, "converted_at": now_iso(),
                        "map_entry": entry, "output": out.name, "format": "wav 48000 Hz pcm_s24le stereo"})
    return {"file": str(out), "duration_s": _wav_seconds(out), "provenance": str(prov_p), "reused": False}


def install_needed(kinds: set[str], sfx_map: dict, root: Path, out_dir: Path) -> dict:
    """Every kind of the cue sheet as out_dir/<kind>.wav: the client's mapped file where the map has one, the procedural
    recipe otherwise. A kind that is neither is Guidance listing the valid kinds."""
    res = {}
    for k in sorted(kinds):
        if k in (sfx_map or {}):
            r = install_mapped(k, sfx_map[k], root, out_dir)
            res[k] = {"file": r["file"], "duration_s": r["duration_s"], "provenance": r["provenance"],
                      "description": f"client SFX library file {_entry_file(sfx_map[k])}",
                      "license": "client-supplied library file — source and sha256 in the provenance file"}
        elif k in RECIPES:
            stale = Path(out_dir) / f"{k}.provenance.json"
            if stale.exists():                      # the kind was mapped before: that library file must not linger
                stale.unlink()
                (Path(out_dir) / f"{k}.wav").unlink(missing_ok=True)
            res.update(synth_needed({k}, out_dir))
        else:
            raise Guidance(f"unknown SFX kind '{k}' in the cue sheet",
                           f"Use one of: {', '.join(valid_kinds(sfx_map))} — or map '{k}' to a client library file in "
                           f"{MAP_REL} and run `reel plan` again", MAP_REL)
    return res
