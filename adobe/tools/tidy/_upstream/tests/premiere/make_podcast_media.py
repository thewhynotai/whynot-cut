"""Make the podcast sync test media (own test files only): a long mic WAV and camera clips cut from it at known
offsets, plus one clip from another recording. usage: make_podcast_media.py <out_dir> <speech.wav> <other.wav>"""
import sys
from pathlib import Path

import av
import numpy as np
import soundfile as sf

RATE = 48000
OFFSETS = {"CamA/C0101.MP4": (3.217, 120.0), "CamB/IMG_0201.MOV": (20.0, 200.0), "CamC/A001C003.MP4": (7.5, 150.0)}
# what real cameras write (and no ffmpeg "Lavf" stamp, which marks a render)
TAGS = {"CamA": {"comment": "DJI OsmoPocket3"},
        "CamB": {"com.apple.quicktime.make": "Apple", "com.apple.quicktime.model": "iPhone 16 Pro Max"},
        "CamC": {"comment": "Sony ILCE-7SM3 NonRealTimeMeta"}}


def load(p):
    a, r = sf.read(p, dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    if r != RATE:
        a = np.interp(np.arange(0, len(a), r / RATE), np.arange(len(a)), a).astype(np.float32)
    return a


def clip(path, audio, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = av.open(str(path), "w", format="mov" if path.suffix.lower() == ".mov" else "mp4",
                options={"movflags": "use_metadata_tags", "fflags": "+bitexact"})
    c.metadata.update(TAGS.get(path.parent.name, {}))
    v = c.add_stream("libx264", rate=30)
    v.width, v.height, v.pix_fmt = 320, 180, "yuv420p"
    s = c.add_stream("aac", rate=RATE)
    s.layout = "mono"
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    frame[:] = color
    for _ in range(int(len(audio) / RATE * 30)):
        for p in v.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
            c.mux(p)
    for i in range(0, len(audio), 1024):
        f = av.AudioFrame.from_ndarray(audio[None, i:i + 1024], format="flt", layout="mono")
        f.sample_rate = RATE
        for p in s.encode(f):
            c.mux(p)
    for st in (v, s):
        for p in st.encode(None):
            c.mux(p)
    c.close()


def main(out, speech, other):
    out = Path(out)
    full = np.concatenate([load(speech), load(other)[: RATE * 150]])        # ~230 s "recorder" file
    sf.write(out / "ZOOM0001.WAV", full, RATE, subtype="PCM_16")
    sf.write(out / "ZOOM0002.WAV", full[int(10 * RATE):int(215 * RATE)] * 0.8, RATE, subtype="PCM_16")   # 2nd mic, 10 s late
    for i, (name, (a, b)) in enumerate(OFFSETS.items()):
        clip(out / name, full[int(a * RATE):int(b * RATE)] * 0.6, (40 + 80 * i, 90, 160))
    stranger = load(sys.argv[4]) if len(sys.argv) > 4 else np.random.default_rng(5).standard_normal(RATE * 40).astype(np.float32) * 0.1
    clip(out / "CamB/IMG_0202.MOV", stranger[: RATE * 40], (200, 60, 60))
    print("mic %.1f s" % (len(full) / RATE), {k: v for k, v in OFFSETS.items()})


if __name__ == "__main__":
    main(*sys.argv[1:4])
