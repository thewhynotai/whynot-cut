"""Shared media helpers (3.0 T2.17, engine MI-7 / MI-9): one time parser, one single-frame grab, one contact-sheet
builder. They replace four time parsers, four frame grabs and seven hand-built contact sheets.

Resource rules (a long-lived `reel serve` must not leak): every image file is opened in a `with` block (or loaded and
closed at once by `open_rgb`); frames come through a pipe (rawvideo), never a temp file; subprocess pipes are closed.
"""
from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path

# --------------------------------------------------------------------------- time
_CLOCK = re.compile(r"(?:(\d+):)?(\d+):(\d+)(?:[.,](\d+))?")


def parse_time(v, *, int_is_ms: bool = False) -> int:
    """A time -> integer milliseconds. Accepts seconds as a number or numeric string (40, 40.5, "40.5"), "MM:SS",
    "H:MM:SS" and either with a fraction after "." or "," ("00:01:02,345", "1:30.5"). `int_is_ms`: an int (not a
    float or string) is already milliseconds — edit-decisions.json's convention (plan.to_ms); everywhere else a bare
    number is seconds. Raises ValueError on anything else. SRT timestamps keep their strict grammar in
    common.parse_ts, which validates and then parses here."""
    if isinstance(v, bool):
        raise ValueError(f"Bad time: {v!r}")
    if isinstance(v, int):
        return v if int_is_ms else v * 1000
    if isinstance(v, float):
        return int(round(v * 1000))
    s = str(v).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return int(round(float(s) * 1000))
    m = _CLOCK.fullmatch(s)
    if not m:
        raise ValueError(f"Bad time: {v!r}")
    h, mi, sec, frac = m.groups()
    ms = ((int(h or 0) * 60 + int(mi)) * 60 + int(sec)) * 1000
    return ms + (int(round(float("0." + frac) * 1000)) if frac else 0)


# --------------------------------------------------------------------------- ffmpeg timeouts (3.0 T2.15, MI-17)
FF_TIMEOUT_BASE_S, FF_TIMEOUT_PER_MEDIA_S = 10, 3     # 10 s + 3 x the media duration
FF_TIMEOUT_UNKNOWN_S = 3600                           # no -t and no probe-able input (a lavfi source): 1 h


def is_ff(cmd) -> bool:
    """An ffmpeg / ffprobe argv (also imageio-ffmpeg's ffmpeg-win-x86_64-v7.1.exe)."""
    if not isinstance(cmd, (list, tuple)) or not cmd:
        return False
    return Path(str(cmd[0])).name.lower().startswith(("ffmpeg", "ffprobe"))


def media_duration_s(path) -> float | None:
    """A media file's duration in seconds (PyAV reads the header), None when it has none or cannot be opened."""
    try:
        st = Path(path).stat()
    except (OSError, ValueError):
        return None
    return _duration_cached(str(path), st.st_size, st.st_mtime_ns)


@functools.lru_cache(maxsize=256)
def _duration_cached(path: str, size: int, mtime_ns: int) -> float | None:      # keyed by the file's stat
    try:
        import av  # type: ignore
        with av.open(path) as c:
            return c.duration / 1_000_000 if c.duration else None
    except Exception:  # noqa: BLE001
        return None


def ff_timeout(cmd) -> float | None:
    """The timeout for an ffmpeg / ffprobe call: 10 s + 3 x the media duration (the largest `-t`, else the longest
    `-i` input), FF_TIMEOUT_UNKNOWN_S when neither is known; None for any other command."""
    if not is_ff(cmd):
        return None
    args = [str(a) for a in cmd[1:]]
    ts, ins = [], []
    for k, v in zip(args, args[1:]):
        if k == "-t":
            try:
                ts.append(parse_time(v))
            except ValueError:
                pass
        elif k == "-i":
            ins.append(v)
    if ts:
        dur = max(ts) / 1000
    else:
        ds = [d for d in (media_duration_s(i) for i in ins if i not in ("-", "pipe:", "pipe:0")) if d]
        if not ds:
            return FF_TIMEOUT_UNKNOWN_S
        dur = max(ds)
    return FF_TIMEOUT_BASE_S + FF_TIMEOUT_PER_MEDIA_S * dur


# --------------------------------------------------------------------------- frames
def _ffmpeg() -> str:
    from .common import ffmpeg_exe
    return ffmpeg_exe()


def grab_frame_file(video: Path, t_s: float, out: Path, *, vf: str | None = None, quality: int | None = None,
                    ss_digits: int = 3) -> Path | None:
    """One frame at t_s seconds written to `out` (format from its extension), or None when nothing was written.
    Input seeking: ffmpeg decodes only from the keyframe before t_s. vf: a filter chain (scale ...); quality: -q:v.
    A file already at `out` is removed first."""
    from .common import run
    out = Path(out)
    out.unlink(missing_ok=True)            # an older file at `out` must never count as this grab's frame
    cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{max(0.0, float(t_s)):.{ss_digits}f}", "-i", str(video),
           "-frames:v", "1"]
    cmd += ["-vf", vf] if vf else []
    cmd += ["-q:v", str(quality)] if quality is not None else []
    run(cmd + [str(out)], check=False)
    return out if out.exists() else None


def grab_frame(video: Path, t_s: float, w: int, h: int, *, fit: str = "pad", mode: str = "RGB"):
    """One frame at t_s seconds as a w x h PIL image (no temp file: rawvideo through a pipe), or None past the end.
    fit "pad": letterboxed inside w x h; "crop": scaled to fill w x h and centre-cropped."""
    from PIL import Image
    if fit == "crop":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
    cmd = [_ffmpeg(), "-loglevel", "error", "-ss", f"{t_s:.3f}", "-i", str(video), "-an", "-frames:v", "1",
           "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=ff_timeout(cmd))
    if r.returncode or len(r.stdout) < w * h * 3:
        return None
    im = Image.frombytes("RGB", (w, h), r.stdout[:w * h * 3])
    return im if mode == "RGB" else im.convert(mode)


def open_rgb(path: Path, mode: str = "RGB"):
    """The image at `path`, loaded and converted, with its file already closed (Windows can then delete or replace it)."""
    from PIL import Image
    with Image.open(path) as im:
        return im.convert(mode)


# --------------------------------------------------------------------------- contact sheets
def contact_sheet(tiles: list, out: Path, *, cols: int, tile_w: int, tile_h: int, label_h: int = 0,
                  fit: str = "stretch", label_xy: tuple = (6, 6), line_h: int = 12, label_box: tuple | None = None,
                  quality: int = 85) -> Path | None:
    """A labelled grid of exactly the tiles given (G73: no empty columns or rows; the tile count is the sheet's
    count): min(cols, n) columns, ceil(n / columns) rows. Returns `out`, or None when there are no tiles.

    tiles: (image, label) pairs; image = a path (opened and closed here) or a PIL image (the caller's); label = text
    (yellow), or a list of (text, fill) lines drawn line_h apart. Each cell is tile_w x (label_h + tile_h): the label
    strip on top, the picture under it.
    fit: "stretch" (resized to tile_w x tile_h), "contain" (aspect kept, top-left), "bottom" (resized to tile_w wide,
    the bottom tile_h kept: name supers).
    label_box: (w, h) black box drawn behind the label (a label over the picture when label_h is 0)."""
    from PIL import Image, ImageDraw
    tiles = list(tiles)
    if not tiles:
        return None
    ncols = max(1, min(int(cols), len(tiles)))
    nrows = -(-len(tiles) // ncols)
    cell_h = label_h + tile_h
    sheet = Image.new("RGB", (ncols * tile_w, nrows * cell_h), "black")
    dr = ImageDraw.Draw(sheet)
    for i, (src, label) in enumerate(tiles):
        x, y = (i % ncols) * tile_w, (i // ncols) * cell_h
        sheet.paste(_fit(src, fit, tile_w, tile_h), (x, y + label_h))
        if label_box:
            dr.rectangle([x, y, x + label_box[0], y + label_box[1]], fill="black")
        lines = [(label, "yellow")] if isinstance(label, str) else list(label or [])
        for k, (text, fill) in enumerate(lines):
            if text:
                dr.text((x + label_xy[0], y + label_xy[1] + k * line_h), text, fill=fill)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=quality)
    return out


def _fit(src, fit: str, w: int, h: int):
    from PIL import Image
    if isinstance(src, Image.Image):
        im = src.convert("RGB")
    else:
        im = open_rgb(src)
    if fit == "contain":
        im.thumbnail((w, h))
        return im
    if fit == "bottom":
        hh = round(im.height * w / im.width)
        return im.resize((w, hh)).crop((0, max(0, hh - h), w, hh))
    return im.resize((w, h))
