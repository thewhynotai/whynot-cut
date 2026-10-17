# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N7 - WhyNot Tidy engine services (whynot-cut/engine/reel/lib/tidy/).

What the owner's panel did with Node (adobe/tools/tidy/_upstream/js/engine.js) the engine does, with the same outputs.

Python only (always run):
* TidyDisk: disk_info (no path, directory, missing, one stat per distinct path, no path-key folding);
* TidyMediaRules: the rules of test_media.js, JS regex corner cases ($ before a newline, ASCII-only \\b and /i), image headers;
* TidySniff: head and tail reads, image head only, a file read once per path, unreadable -> names only, RAW originals;
* TidyWavInfo / TidyWavPower: header table, power against a plain numpy reference, pieces, truncated files;
* TidyMediaTokens: every alternative of RENDER_TAGS / CAMERA_TAGS / CAMERA_NAME / RENDER_NAME is read out of the port's
  media.js, expanded and judged by the twin (and by the JS when node is there): a token the twin forgot fails;
  the fixtures of test_media.js are read from the owner's file (skipped without adobe/tools);
* TidyDriftGuard (A3 #7): a lazy (no disk) 60-minute 44.1 kHz recording keeps the click times within 1 ms; 22.05 / 11.025 /
  44.1 stereo recordings of 5 minutes too; without the guard the same file drifts. The 60-minute files on disk (44.1 vs
  48 kHz, 0.66 GB) run with WHYNOT_SLOW_TESTS=1 only;
* TidyBackup, TidyStore, TidyPackage (licence header, no "hoka", no "_upstream" in a file name).
With node and adobe/tools (skipped with a reason otherwise, e.g. in the plugin zip): the same inputs go through the JS
(the port's media.js / sync.js, the upstream engine.js function bodies) and must give identical results:
* TidyMediaParity: fixtures of test_media.js, 400 seeded random items, JS regex corner cases;
* TidyWavInfoParity; TidyEngineParity: disk_info, sniff on generated files, wav_power on generated WAVs (mono / stereo,
  8-96 kHz, odd chunk before data, data size not a multiple of the frame, extensible, truncated, > 9 MiB so several
  4 MiB pieces are read): identical float64 arrays.
Run:  bash tools/test.sh -p test_tidy_engine.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
sys = _sys
sys.path.insert(0, str(SK / "engine" / "reel"))

from lib.tidy import backup as tbackup  # noqa: E402
from lib.tidy import disk as tdisk  # noqa: E402
from lib.tidy import media as tmedia  # noqa: E402
from lib.tidy import sniff as tsniff  # noqa: E402
from lib.tidy import store as tstore  # noqa: E402
from lib.tidy import wavpower as twav  # noqa: E402

ADOBE_TOOLS = REPO / "adobe" / "tools"
RUNNER = ADOBE_TOOLS / "_harness" / "js_runner.js"
PORT = ADOBE_TOOLS / "tidy" / "src"
UPSTREAM = ADOBE_TOOLS / "tidy" / "_upstream"
NODE = shutil.which("node")
TOOLS_PRESENT = RUNNER.is_file() and (UPSTREAM / "js").is_dir() and PORT.is_dir()
NO_TOOLS = "adobe/tools is not in this checkout (the plugin zip ships the tests but not adobe/)"
LIB = SK / "engine" / "reel" / "lib" / "tidy"


def run_js(tc, root, load, calls):
    """Run `calls` through js_runner.js with `load` (files relative to root) in ONE node process; return the results."""
    with tempfile.TemporaryDirectory() as td:
        req = Path(td) / "request.json"
        req.write_text(json.dumps({"load": load, "calls": calls}), encoding="utf-8")
        p = subprocess.run([NODE, str(RUNNER), str(root), str(req)], capture_output=True, text=True,
                           encoding="utf-8", timeout=300)
    tc.assertEqual(p.returncode, 0, p.stderr)
    lines = p.stdout.rstrip("\n").split("\n")
    out = json.loads(lines[-1])["results"]
    tc.assertEqual(len(out), len(calls))
    return out


def call(fn, *args):
    return {"fn": fn, "args": list(args)}


# ---------------------------------------------------------------- generated files

def wav_bytes(rate, channels, samples, *, fmt_tag=1, bits=16, before_data=b"", data_size=None, after=b"", extra_fmt=b""):
    """A RIFF/WAVE file: fmt chunk, `before_data` chunks (raw bytes, caller pads), data chunk of `samples` (int16)."""
    data = np.asarray(samples).astype("<i2").tobytes() if not isinstance(samples, (bytes, bytearray)) else bytes(samples)
    fmt = struct.pack("<HHIIHH", fmt_tag, channels, rate, rate * channels * 2, channels * 2, bits) + extra_fmt
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + before_data
    body += b"data" + struct.pack("<I", len(data) if data_size is None else data_size) + data + after
    return b"RIFF" + struct.pack("<I", len(body)) + body


def chunk(cid: bytes, payload: bytes) -> bytes:
    return cid + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) & 1 else b"")


def noise(n, seed, scale=6000):
    r = np.random.RandomState(seed)
    x = np.cumsum(r.randn(n)) * 40 + r.randn(n) * scale
    x[:: max(1, n // 7)] = -32768
    x[1:: max(1, n // 5)] = 32767
    return np.clip(x, -32768, 32767).astype("<i2")


def write_click_wav(path, rate, seconds, click_times, click_ms=4, amp=12000, channels=1):
    """A WAV of silence with a click (constant amp) of click_ms at each time; streamed, never held in memory."""
    n = int(round(seconds * rate))
    clicks = [(int(np.ceil(t * rate)), int(round(click_ms / 1000 * rate))) for t in click_times]
    block = 4 * 1024 * 1024 // (2 * channels)
    size = n * 2 * channels
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + size) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate,
                                                                                     rate * channels * 2, channels * 2, 16))
        f.write(b"data" + struct.pack("<I", size))
        for s0 in range(0, n, block):
            m = min(block, n - s0)
            x = np.zeros(m, dtype="<i2")
            for c0, ln in clicks:
                a, b = max(c0, s0), min(c0 + ln, s0 + m)
                if a < b:
                    x[a - s0:b - s0] = amp
            f.write((np.repeat(x, channels) if channels > 1 else x).tobytes())


def onsets(power, thr=0.01):
    """Frame index (= ms) where each click starts: first frame above thr after a quiet one."""
    hot = power > thr
    return np.flatnonzero(hot[1:] & ~hot[:-1]) + 1


class LazyClickWav:
    """A file-like 16-bit WAV that never exists on disk: seek / tell / read generate a silent recording with clicks, so a
    60-minute recording costs no disk. `dataOffset` bytes of header are zeros (the resampler is given `info` directly)."""

    def __init__(self, rate, seconds, click_times, channels=1, click_ms=4, amp=12000, offset=44):
        self.rate, self.ch, self.offset, self.amp = rate, channels, offset, amp
        self.n = int(round(seconds * rate))
        self.size = offset + self.n * 2 * channels
        self.clicks = [(int(np.ceil(t * rate)), int(round(click_ms / 1000 * rate))) for t in click_times]
        self.pos = 0

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        end = self.size if n is None or n < 0 else min(self.size, self.pos + n)
        if end <= self.pos:
            return b""
        out = bytearray(end - self.pos)
        lo, hi = max(self.pos, self.offset), end
        if hi > lo:
            first = (lo - self.offset) // (2 * self.ch)
            last = (hi - self.offset + 2 * self.ch - 1) // (2 * self.ch)
            x = np.zeros((last - first, self.ch), dtype="<i2")
            for c0, ln in self.clicks:
                a, b = max(c0, first), min(c0 + ln, last)
                if a < b:
                    x[a - first:b - first, :] = self.amp
            raw = x.tobytes()
            skip = (lo - self.offset) - first * 2 * self.ch
            out[lo - self.pos:hi - self.pos] = raw[skip:skip + (hi - lo)]
        self.pos = end
        return bytes(out)


def js_string(lit):
    """The value of a JS single-quoted string literal (test_media.js uses \\uXXXX, \\\\ and \\' escapes only)."""
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c == "\\":
            n = lit[i + 1]
            if n == "u":
                out.append(chr(int(lit[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(n, n))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def load_media_fixtures():
    """The byte strings test_media.js feeds the rules (DJI, IPHONE, AE, COMPOSE, LAVF), read from the owner's file;
    None when adobe/tools is not there (the plugin zip)."""
    p = UPSTREAM / "tests" / "test_media.js"
    if not p.is_file():
        return None
    src = p.read_text(encoding="utf-8")
    out = {}
    for name in ("DJI", "IPHONE", "AE", "COMPOSE", "LAVF"):
        m = re.search(r"^var %s = '((?:\\.|[^'\\])*)';" % name, src, re.M)
        if not m:
            return None
        out[name] = js_string(m.group(1))
    return out


def js_regex_literal(name):
    """(source, flags) of `var NAME = /.../flags;` in the port's media.js."""
    src = (PORT / "js" / "media.js").read_text(encoding="utf-8")
    m = re.search(r"^\s*var %s = /(.*)/([a-z]*);" % name, src, re.M)
    assert m, name
    return m.group(1), m.group(2)


def _split_top(pat):
    parts, depth, cur, i = [], 0, "", 0
    while i < len(pat):
        c = pat[i]
        if c == "\\":
            cur += pat[i:i + 2]
            i += 2
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "|" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    parts.append(cur)
    return parts


def expand_regex(pat):
    """Every alternative of a small JS regex (groups, |, \\d{n}, \\d+, x?, \\., \\b, ^, $) as one concrete string."""
    import itertools
    out = []
    for alt in _split_top(pat):
        elems, i = [], 0
        while i < len(alt):
            c = alt[i]
            if c == "\\":
                n = alt[i + 1]
                i += 2
                if n == "d":
                    k = 1
                    m = re.match(r"\{(\d+)\}", alt[i:])
                    if m:
                        k = int(m.group(1))
                        i += m.end()
                    elif alt[i:i + 1] == "+":
                        k = 2
                        i += 1
                    elems.append(["1" * k])
                else:
                    elems.append([""] if n == "b" else [n])
            elif c == "(":
                depth, j = 1, i + 1
                while depth:
                    if alt[j] == "\\":
                        j += 1
                    elif alt[j] == "(":
                        depth += 1
                    elif alt[j] == ")":
                        depth -= 1
                    j += 1
                inner = alt[i + 1:j - 1]
                elems.append(expand_regex(inner[2:] if inner.startswith("?:") else inner))
                i = j
            elif c in "^$":
                elems.append([""])
                i += 1
            elif c in "[]{}*+.":
                raise ValueError("unsupported regex syntax %r in %r" % (c, pat))
            else:
                elems.append([c])
                i += 1
            if alt[i:i + 1] == "?":
                elems[-1] = [""] + elems[-1]
                i += 1
        out.extend("".join(t) for t in itertools.product(*elems))
    return out


_FIX = []


def fixtures():
    """The test_media.js fixtures, parsed lazily (never at import: a changed owner file must not break the module); None
    when they are not there or the file has another shape."""
    if not _FIX:
        _FIX.append(load_media_fixtures())
    return _FIX[0]


def need_fixtures(tc):
    fx = fixtures()
    if fx is None:
        tc.skipTest(NO_TOOLS + " or test_media.js changed shape")
    return fx

# Source Text values (textEditValue) the pure parity test sends through both implementations; the last six are the
# surrogate cases of the Task 8 review: an escaped emoji (two \u escapes = ONE character in JS), a lone high, a lone low,
# a high then a non-low, a reversed pair, and two pairs in a row
TEXT_VALUES = (
    '{"textEditValue":"a\\nb  c"}', '{"textEditValue" : "x\\u0041\\"q\\\\z"}', None, "", 5, '{"textEditValue":"unterminated',
    '{"textEditValue":"a b"}', '{"textEditValue":"\\ x"}', '{"textEditValue":"\\\nx"}', '{"textEditValue":"    ﻿ x 　 "}',
    '{"textEditValue":"\\u062d\\u0644\\u0642\\u0629"}',
    '{"textEditValue":"hi \\ud83d\\ude00"}', '{"textEditValue":"a\\ud83db"}', '{"textEditValue":"a\\ude00b"}',
    '{"textEditValue":"\\ud83dx\\ude00"}', '{"textEditValue":"\\ude00\\ud83d"}', '{"textEditValue":"\\ud83d\\ude00\\ud83d\\ude01"}',
    '{"textEditValue":"raw ' + chr(0x1F600) + ' emoji"}',
)


class Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.tmp = Path(self._td.name)

    def put(self, name, data: bytes) -> str:
        p = self.tmp / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return str(p)


# ---------------------------------------------------------------- Python only

class TidyDisk(Tmp):
    def test_cases(self):
        f = self.put("a/clip.mp4", b"x" * 1234)
        d = str(self.tmp / "a")
        items = [{"path": ""}, {"name": "no path"}, {"path": f}, {"path": f}, {"path": d}, {"path": str(self.tmp / "missing.mp4")}]
        out = tdisk.disk_info(items)
        self.assertIs(out, items)
        self.assertEqual([(i["exists"], i["size"]) for i in items],
                         [(True, 0), (True, 0), (True, 1234), (True, 1234), (True, 0), (False, 0)])

    def test_one_stat_per_distinct_path_and_no_path_key_folding(self):
        f = self.put("Clip.MP4", b"abc")
        low = str(self.tmp / "clip.mp4")
        seen = []
        real = os.stat

        def spy(p, *a, **k):
            seen.append(str(p))
            return real(p, *a, **k)
        with mock.patch("os.stat", spy):
            tdisk.disk_info([{"path": f}, {"path": f}, {"path": low}, {"path": f}])
        self.assertEqual(seen.count(f), 1)
        self.assertEqual(seen.count(low), 1)          # a differently spelled path is its own path here (the plan folds)

    def test_unreadable_path_is_missing(self):
        out = tdisk.disk_info([{"path": "bad\0name"}])
        self.assertEqual((out[0]["exists"], out[0]["size"]), (False, 0))


class TidyMediaRules(unittest.TestCase):
    def fx(self):
        """The fixtures of test_media.js, read from the owner's file (skipped without adobe/tools)."""
        return need_fixtures(self)

    def test_video_kind_like_test_media_js(self):
        f = self.fx()
        k = tmedia.video_kind
        self.assertEqual(k(f["DJI"], "Script 1 - 2.mp4"), "camera")
        self.assertEqual(k(f["IPHONE"], "IMG_3886.MOV.mov"), "camera")
        self.assertEqual(k(f["AE"], "Script 4.mp4"), "render")
        self.assertEqual(k(f["COMPOSE"], "dji_export_20261010_234451_0.f_compose_0.mov"), "render")
        self.assertEqual(k(f["LAVF"], "clip.mp4"), "render")
        self.assertEqual(k("", "C0890.MP4"), "camera")
        self.assertEqual(k("", "A001C002_220101_R1AB.mov"), "camera")
        self.assertEqual(k("", "clip.mp4"), "render")
        self.assertEqual(k("...NonRealTimeMeta...Sony...", "Interview.MP4"), "camera")
        self.assertEqual((k(f["DJI"], "Interview final.mp4"), k(f["DJI"], "Ahmed edit.mp4")), ("camera", "camera"))
        self.assertEqual(k("", "Interview final.mp4"), "render")
        self.assertEqual(k("", "00001.MTS"), "camera")
        self.assertEqual((k(None, None), k("", "")), ("render", "render"))

    def test_camera_id_and_model(self):
        f = self.fx()
        self.assertEqual(tmedia.camera_id(f["DJI"], "a.mp4", "/RAW/A"), "DJI OsmoPocket3 | /RAW/A")
        self.assertEqual(tmedia.camera_model(f["IPHONE"]), "iPhone 16 Pro Max")
        self.assertEqual(tmedia.camera_id("", "C0001.MP4", "/x/Cam B"), "folder:/x/Cam B")
        self.assertNotEqual(tmedia.camera_id(f["DJI"], "a.mp4", "/P/Cam A"), tmedia.camera_id(f["DJI"], "b.mp4", "/P/Cam B"))
        self.assertEqual(tmedia.camera_id(f["DJI"], "a.mp4", "/P/Cam A"), tmedia.camera_id(f["DJI"], "c.mp4", "/P/Cam A"))
        self.assertEqual(tmedia.camera_model("x ILCE-7M4 y"), "ILCE-7M4")
        self.assertEqual(tmedia.camera_model(None), "")

    def test_js_regex_semantics_are_kept(self):
        # $ is the very end only: a name ending in a newline is not a 00001.MTS
        self.assertEqual(tmedia.video_kind("", "00001.MTS\n"), "render")
        self.assertEqual(tmedia.needs_bytes({"path": "/a/b.mp4\n"}), None)
        # \b and /i are ASCII only
        self.assertEqual(tmedia.video_kind("", "C0001\u00e9edit.mp4"), "render")     # e-acute is no word character in JS: \bedit\b matches
        self.assertEqual(tmedia.video_kind("", "C0001xedit.mp4"), "camera")           # a letter before it: no word boundary
        self.assertEqual(tmedia.video_kind("", "C0001compo\u017fe.mp4"), "camera")    # /i does not fold the long s into "compose"
        # the model stops at a non-alphanumeric byte or at the very end
        self.assertEqual(tmedia.camera_model("DJI Osmo Pocket 3"), "DJI Osmo Pocket 3")
        self.assertEqual(tmedia.camera_model("DJI OsmoPocket3\n"), "DJI OsmoPocket3")

    def test_image_sizes(self):
        def b(arr):
            return "".join(chr(c) for c in arr)
        png = b([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0, 0, 0, 64, 0, 0, 0, 48])
        self.assertEqual(tmedia.image_size(png, "png"), {"w": 64, "h": 48})
        png_big = b([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0xFF, 0xFF, 0xFF, 0xFF, 0x80, 0, 0, 1])
        self.assertEqual(tmedia.image_size(png_big, "png"), {"w": 4294967295, "h": 2147483649})
        jpg = b([0xFF, 0xD8, 0xFF, 0xE0, 0, 16, 0x4A, 0x46, 0x49, 0x46, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 0xFF, 0xC0, 0, 17, 8, 0x04, 0x38, 0x07, 0x80, 3])
        self.assertEqual(tmedia.image_size(jpg, "jpg"), {"w": 1920, "h": 1080})
        self.assertIsNone(tmedia.image_size("", "png"))
        self.assertIsNone(tmedia.image_size(None, "png"))
        self.assertIsNone(tmedia.image_size("x" * 30, "png"))
        gif = "GIF89a" + b([0x40, 0x01, 0xF0, 0x00]) + "\0" * 20
        self.assertEqual(tmedia.image_size(gif, "gif"), {"w": 320, "h": 240})
        vp8x = "RIFF\0\0\0\0WEBPVP8X" + "\0" * 8 + b([0x0F, 0x02, 0, 0xDF, 0x01, 0])
        self.assertEqual(tmedia.image_size(vp8x, "webp"), {"w": 528, "h": 480})
        vp8l = "RIFF\0\0\0\0WEBPVP8L" + "\0" * 5 + b([0x2F]) + b([0x3F, 0x00, 0x80, 0x00]) + "\0" * 6
        self.assertIsNotNone(tmedia.image_size(vp8l, "webp"))

    def test_is_icon_and_needs_bytes_and_describe(self):
        f = self.fx()
        self.assertTrue(tmedia.is_icon("a.png", "png", {"w": 64, "h": 48}))
        self.assertFalse(tmedia.is_icon("bg.jpg", "jpg", {"w": 1920, "h": 1080}))
        self.assertTrue(tmedia.is_icon("Company Logo.png", "png", {"w": 2000, "h": 2000}))
        self.assertTrue(tmedia.is_icon("x.svg", "svg", None))
        self.assertFalse(tmedia.is_icon("photo.png", "png", None))
        n = tmedia.needs_bytes
        self.assertEqual((n({"path": "/a/b.MOV"}), n({"path": "/a/b.jpeg"}), n({"path": "/a/b.wav"}), n({"path": ""}), n({})),
                         ("video", "image", None, None, None))
        v = {"name": "Script 1 - 2.mp4", "path": "/Volumes/X/RAW/Script 1/Script 1 - 2.mp4"}
        self.assertIs(tmedia.describe(v, f["DJI"]), v)
        self.assertEqual((v["kind"], v["camId"]), ("camera", "DJI OsmoPocket3 | /Volumes/X/RAW/Script 1"))
        u = {"name": "C0001.MP4", "path": "/x/Cam B/C0001.MP4"}
        tmedia.describe(u, None)
        self.assertEqual((u["kind"], u["camId"]), ("camera", "folder:/x/Cam B"))
        doc = {"name": "notes.txt", "path": "/x/notes.txt"}
        tmedia.describe(doc, "abc")
        self.assertEqual(doc, {"name": "notes.txt", "path": "/x/notes.txt"})
        raw = {"name": "A001_C002_0101AB.R3D", "path": "/r/A001_C002_0101AB.R3D"}
        tmedia.describe(raw, None)
        self.assertEqual(raw["kind"], "camera")
        win = {"name": "a.mp4", "path": "C:\\RAW\\Cam A\\a.mp4"}
        tmedia.describe(win, "")
        self.assertEqual(win["camId"], "folder:C:\\RAW\\Cam A")

    def test_text_from_value(self):
        t = tmedia.text_from_value
        self.assertEqual(t('{"mTextParam":{"mStyleSheet":{}},"textEditValue":"\u0627\u0644\u062a\u0631\u0642\u064a\u0629\\nNow"}'),
                         "\u0627\u0644\u062a\u0631\u0642\u064a\u0629 Now")
        self.assertEqual((t('xx{"textEditValue":"5"}'), t('{"fontSize":40}'), t(None), t("")), ("5", "", "", ""))
        self.assertEqual(t('{"textEditValue" : "a\\u0041\\"b\\\\c  d"}'), 'aA"b\\c d')

    def test_text_from_value_joins_escaped_surrogate_pairs_like_js(self):
        t = tmedia.text_from_value
        self.assertEqual(t('{"textEditValue":"hi \\ud83d\\ude00"}'), "hi " + chr(0x1F600))
        self.assertEqual(t('{"textEditValue":"\\ud83d\\ude00\\ud83d\\ude01"}'), chr(0x1F600) + chr(0x1F601))
        self.assertEqual(t('{"textEditValue":"a\\ud83db"}'), "a" + chr(0xD83D) + "b")                 # a lone high stays lone
        self.assertEqual(t('{"textEditValue":"a\\ude00b"}'), "a" + chr(0xDE00) + "b")                 # a lone low too
        self.assertEqual(t('{"textEditValue":"\\ude00\\ud83d"}'), chr(0xDE00) + chr(0xD83D))          # reversed: no pair
        self.assertEqual(t('{"textEditValue":"raw ' + chr(0x1F600) + '"}'), "raw " + chr(0x1F600))
        # the result is always safe to write as UTF-8 after the log's backslashreplace
        for v in (t('{"textEditValue":"a\\ud83db"}'), t('{"textEditValue":"\\ude00"}')):
            v.encode("utf-8", "backslashreplace")

    def test_the_media_regex_alternatives_are_all_known(self):
        """Mimo (Task 8 review I1): a DJI Mimo file is a camera original (the model regex of media.js does not know Mimo,
        so it has no model name, as in the JS)."""
        self.assertEqual(tmedia.video_kind("..DJI Mimo..", "clip.mp4"), "camera")
        self.assertEqual(tmedia.camera_model("..DJI Mimo 2.."), "")

    def test_video_kind_without_the_fixtures(self):
        k = tmedia.video_kind
        self.assertEqual(k("..DJI OsmoPocket3..", "Script 1 - 2.mp4"), "camera")
        self.assertEqual(k("..Mainconcept..DJI Osmo..", "x.mp4"), "render")
        self.assertEqual(k("", "C0890.MP4"), "camera")
        self.assertEqual(k("", "Interview final.mp4"), "render")


def js_to_py(src):
    """A JS regex source as the twin writes it: the same text, except that `$` (the very end in JS) is `\\Z` in Python."""
    out, i = [], 0
    while i < len(src):
        c = src[i]
        if c == "\\":
            out.append(src[i:i + 2])
            i += 2
            continue
        out.append("\\Z" if c == "$" else c)
        i += 1
    return "".join(out)


def js_literals():
    """{name: (source, flags)} of the regex literals of the port's media.js that the twin must copy: the tag and name
    lists, the extension lists, the RAW list, the three camera-model regexes and the icon-name regex. None if the file
    has another shape (the test then skips instead of failing to import)."""
    src = (PORT / "js" / "media.js").read_text(encoding="utf-8")
    out = {}
    for name in ("RENDER_TAGS", "RENDER_NAME", "CAMERA_TAGS", "CAMERA_NAME", "CAMERA_RAW", "VIDEO_EXT", "IMAGE_EXT"):
        m = re.search(r"\b%s = /((?:\\.|[^/\\\n])+)/([a-z]*)[;,]" % name, src)
        if not m:
            return None
        out[name] = (m.group(1), m.group(2))
    models = re.findall(r"/((?:\\.|[^/\\\n])+)/\.exec\(text", src)
    icon = re.search(r"/((?:\\.|[^/\\\n])+)/(i)\.test\(name \|\| ''\)", src)
    if len(models) != 3 or not icon:
        return None
    out["DJI_MODEL"], out["IPHONE"], out["OTHER_MODEL"] = ((s, "") for s in models)
    out["ICON_NAME"] = (icon.group(1), icon.group(2))
    return out


# JS literal name -> the compiled pattern of media.py that must be the same text
PY_REGEXES = {"RENDER_TAGS": "RENDER_TAGS", "RENDER_NAME": "RENDER_NAME", "CAMERA_TAGS": "CAMERA_TAGS", "CAMERA_NAME": "CAMERA_NAME",
              "CAMERA_RAW": "CAMERA_RAW", "VIDEO_EXT": "_VIDEO_EXT", "IMAGE_EXT": "_IMAGE_EXT", "DJI_MODEL": "_DJI_MODEL",
              "IPHONE": "_IPHONE", "OTHER_MODEL": "_OTHER_MODEL", "ICON_NAME": "_ICON_NAME"}


@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyMediaTokens(unittest.TestCase):
    """Task 8 review I1 / re-review N1, N2. Hand-picked texts cannot catch a token the twin forgot, so the guard has two
    halves that can each fail:
    * SOURCE: the regex literals of adobe/tools/tidy/src/js/media.js (tag and name lists, video / image / RAW extension lists,
      the three camera-model regexes, the icon-name regex) are read and compared, text for text (after `$` -> `\\Z`, and
      the flags), with the pattern media.py compiled. A token added or removed on EITHER side differs.
    * BEHAVIOUR: every alternative of the four lists is expanded to a concrete string and judged by the twin (here, no
      node) and by the JS (test below, node). The render cases carry camera evidence that the render tag must beat
      (text `..<tag>..DJI Osmo..`, name `C1111 <word>.mp4`), so a render token the twin forgot gives `camera` and fails
      (without that evidence `render` is the default answer and the case proves nothing).
    The mutation tests prove both halves by breaking the twin in memory."""

    @staticmethod
    def cases():
        lits = js_literals()
        out = [("..%s..DJI Osmo.." % a, "C1111.mp4", "render", "RENDER_TAGS") for a in expand_regex(lits["RENDER_TAGS"][0])]
        out += [("..%s.." % a, "clip.mp4", "camera", "CAMERA_TAGS") for a in expand_regex(lits["CAMERA_TAGS"][0])]
        out += [("", a, "camera", "CAMERA_NAME") for a in expand_regex(lits["CAMERA_NAME"][0])]
        out += [("", "C1111 %s.mp4" % a, "render", "RENDER_NAME") for a in expand_regex(lits["RENDER_NAME"][0])]
        return out

    @classmethod
    def source_problems(cls):
        lits = js_literals()
        out = []
        for js_name, py_name in PY_REGEXES.items():
            rx = getattr(tmedia, py_name)
            src, flags = lits[js_name]
            if rx.pattern != js_to_py(src):
                out.append("%s: media.py has %r, media.js has %r" % (js_name, rx.pattern, js_to_py(src)))
            want = re.ASCII | (re.I if "i" in flags else 0)
            if rx.flags & (re.I | re.A | re.U) != want:
                out.append("%s: flags differ (twin %r, JS %r)" % (js_name, rx.flags & (re.I | re.A | re.U), flags))
        return out

    @classmethod
    def case_problems(cls):
        return ["%s: video_kind(%r, %r) is %r, the regex says %s" % (where, text, name, tmedia.video_kind(text, name), want)
                for text, name, want, where in cls.cases() if tmedia.video_kind(text, name) != want]

    @classmethod
    def problems(cls):
        return cls.source_problems() + cls.case_problems()

    def setUp(self):
        if js_literals() is None:
            self.skipTest("media.js has another shape than the guard reads")

    def test_the_expander_reads_the_whole_literal(self):
        alts = [c[0].split("..")[1] for c in self.cases() if c[3] == "CAMERA_TAGS"]
        for want in ("DJI Osmo", "DJI Pocket", "DJI Action", "DJI Mini", "DJI Mavic", "DJI Air", "DJI Avata", "DJI Neo", "DJI Mimo",
                     "com.apple.quicktime.model", "NonRealTimeMeta", "GoPro", "Insta360", "Canon", "Panasonic", "Blackmagic",
                     "FUJIFILM", "NIKON", "com.android.manufacturer", "samsung"):
            self.assertIn(want, alts)
        names = [c[1] for c in self.cases() if c[3] == "CAMERA_NAME"]
        for want in ("C1111", "IMG_1", "DSC1", "DSC_1", "GX111111", "A111C111", "11111.MTS"):
            self.assertTrue(any(n.startswith(want) or n == want for n in names), want)
        render = [c for c in self.cases() if c[3] in ("RENDER_TAGS", "RENDER_NAME")]
        self.assertEqual(len(render), 14)
        self.assertGreaterEqual(len(self.cases()), 49)

    def test_the_twin_is_the_same_text_as_the_js_and_judges_every_alternative(self):
        self.assertEqual(self.problems(), [])

    def test_the_render_cases_have_camera_evidence_to_beat(self):
        """Without evidence the answer `render` is the default: show that each render case really is a contest."""
        for text, name, want, where in self.cases():
            if where == "RENDER_TAGS":
                self.assertEqual(tmedia.camera_model(text), "DJI Osmo")                         # the text says camera
                self.assertEqual(tmedia.video_kind(text.replace(text.split("..")[1], "x"), name), "camera", text)
            if where == "RENDER_NAME":
                self.assertEqual(tmedia.video_kind("", name.replace(name.split()[1].split(".mp4")[0], "x")), "camera", name)

    # --- the guard can fail: break the twin in memory and require a report (N1) ---
    def mutated(self, name, old, new):
        rx = getattr(tmedia, name)
        self.assertIn(old, rx.pattern)
        return mock.patch.object(tmedia, name, re.compile(rx.pattern.replace(old, new, 1), rx.flags))

    def test_a_token_added_only_in_python_is_caught(self):
        with self.mutated("CAMERA_TAGS", "NIKON", "NIKON|Foo"):
            probs = self.source_problems()
        self.assertTrue([p for p in probs if p.startswith("CAMERA_TAGS")], probs)
        with self.mutated("RENDER_TAGS", "CapCut", "CapCut|Foo"):
            self.assertTrue([p for p in self.source_problems() if p.startswith("RENDER_TAGS")])
        with self.mutated("CAMERA_NAME", "PXL_", "PXL_|FOO_"):
            self.assertTrue([p for p in self.source_problems() if p.startswith("CAMERA_NAME")])

    def test_a_token_removed_from_the_python_render_name_regex_is_caught_by_both_halves(self):
        with self.mutated("RENDER_NAME", "compose|", ""):
            src, beh = self.source_problems(), self.case_problems()
        self.assertTrue([p for p in src if p.startswith("RENDER_NAME")], src)
        self.assertTrue([p for p in beh if p.startswith("RENDER_NAME") and "compose" in p], beh)

    def test_a_render_tag_removed_from_python_is_caught_by_both_halves(self):
        with self.mutated("RENDER_TAGS", "CapCut|", ""):
            src, beh = self.source_problems(), self.case_problems()
        self.assertTrue([p for p in src if p.startswith("RENDER_TAGS")], src)
        self.assertTrue([p for p in beh if p.startswith("RENDER_TAGS") and "CapCut" in p], beh)

    def test_extension_lists_and_model_regexes_are_compared_too(self):
        """N2: dropping mkv, a RAW extension or a camera-model token is a source difference (no seeded test needed)."""
        with self.mutated("_VIDEO_EXT", "mkv|", ""):
            self.assertTrue([p for p in self.source_problems() if p.startswith("VIDEO_EXT")])
        with self.mutated("_IMAGE_EXT", "|icns", ""):
            self.assertTrue([p for p in self.source_problems() if p.startswith("IMAGE_EXT")])
        with self.mutated("CAMERA_RAW", "braw|", ""):
            self.assertTrue([p for p in self.source_problems() if p.startswith("CAMERA_RAW")])
        with self.mutated("_DJI_MODEL", "Neo", "Neo|Mimo"):
            self.assertTrue([p for p in self.source_problems() if p.startswith("DJI_MODEL")])
        with self.mutated("_IPHONE", "mini", "mini|Ultra"):
            self.assertTrue([p for p in self.source_problems() if p.startswith("IPHONE")])
        with self.mutated("_OTHER_MODEL", "BMPCC", "BMPCC|ARRI"):
            self.assertTrue([p for p in self.source_problems() if p.startswith("OTHER_MODEL")])
        with self.mutated("_ICON_NAME", "emoji", "emoji|glyph"):
            self.assertTrue([p for p in self.source_problems() if p.startswith("ICON_NAME")])

    def test_a_flag_difference_is_caught(self):
        rx = tmedia.RENDER_NAME
        with mock.patch.object(tmedia, "RENDER_NAME", re.compile(rx.pattern, re.ASCII)):
            self.assertTrue([p for p in self.source_problems() if "flags differ" in p])
        with mock.patch.object(tmedia, "RENDER_NAME", re.compile(rx.pattern, re.I)):          # Unicode instead of ASCII
            self.assertTrue([p for p in self.source_problems() if "flags differ" in p])

    @unittest.skipUnless(NODE, "node is not installed")
    def test_the_js_and_the_twin_agree_on_every_alternative(self):
        cases = self.cases()
        js = run_js(self, PORT, ["js/media.js"], [call("TidyMedia.videoKind", t, n) for t, n, _, _ in cases])
        self.assertEqual(js, [c[2] for c in cases])
        self.assertEqual(js, [tmedia.video_kind(t, n) for t, n, _, _ in cases])


class TidySniff(Tmp):
    def video(self, name, head=b"", mid=0, tail=b"", **kw):
        return self.put(name, head + b"\0" * mid + tail)

    def test_head_and_tail_of_a_video_are_read_and_the_middle_is_not(self):
        dji = b"..DJI OsmoPocket3\0.."
        tail_tag = self.video("tail/Interview.mp4", b"ftypisom", 5 * 1024 * 1024, dji)
        mid_tag = self.video("mid/Interview.mp4", b"ftypisom", 1024 * 1024, b"\0" * 0)
        data = bytearray(b"ftypisom" + b"\0" * (6 * 1024 * 1024))
        data[3 * 1024 * 1024:3 * 1024 * 1024 + len(dji)] = dji          # in the middle: never read
        mid = self.put("mid2/Interview.mp4", bytes(data))
        items = [{"name": "Interview.mp4", "path": p} for p in (tail_tag, mid)]
        tsniff.sniff(items)
        self.assertEqual(items[0]["kind"], "camera")
        self.assertTrue(items[0]["camId"].startswith("DJI OsmoPocket3 | "))
        self.assertEqual(items[1]["kind"], "render")
        self.assertTrue(items[1]["camId"].startswith("folder:"))
        small = {"name": "Interview.mp4", "path": mid_tag}
        tsniff.sniff([small])
        self.assertEqual(small["kind"], "render")

    def test_exactly_2_mib_files_and_reads_never_exceed_head_plus_tail(self):
        p = self.put("c/a.mp4", b"\0" * (2 * 1024 * 1024) + b"DJI Mavic3\0")
        reads = []
        real_open = open

        class Spy:
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                self.f.__enter__()
                return self

            def __exit__(self, *a):
                return self.f.__exit__(*a)

            def read(self, n=-1):
                d = self.f.read(n)
                reads.append(len(d))
                return d

            def __getattr__(self, k):
                return getattr(self.f, k)

        def spy_open(path, mode="r", *a, **k):
            f = real_open(path, mode, *a, **k)
            return Spy(f) if str(path) == p else f
        with mock.patch("builtins.open", spy_open):
            it = {"name": "a.mp4", "path": p}
            tsniff.sniff([it])
        self.assertEqual(reads, [2097152, 11])
        self.assertEqual(it["kind"], "camera")

    def test_images_read_64_kib_only(self):
        png = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0, 0, 0, 64, 0, 0, 0, 48]) + b"\0" * 200000
        small = self.put("i/a.png", png)
        big = self.put("i/photo.png", png[:16] + struct.pack(">II", 4000, 3000) + b"\0" * 200000)
        items = [{"name": "a.png", "path": small}, {"name": "photo.png", "path": big}, {"name": "x.svg", "path": self.put("i/x.svg", b"<svg/>")}]
        tsniff.sniff(items)
        self.assertEqual((items[0]["icon"], items[0]["imgW"], items[0]["imgH"]), (True, 64, 48))
        self.assertEqual((items[1]["icon"], items[1]["imgW"], items[1]["imgH"]), (False, 4000, 3000))
        self.assertEqual(items[2]["icon"], True)
        self.assertNotIn("imgW", items[2])

    def test_unreadable_files_fall_back_to_names_and_raw_originals_need_no_file(self):
        items = [{"name": "C0001.MP4", "path": str(self.tmp / "x" / "C0001.MP4")}, {"name": "clip.mov", "path": str(self.tmp / "clip.mov")},
                 {"name": "logo.png", "path": str(self.tmp / "logo.png")},
                 {"name": "A.R3D", "path": str(self.tmp / "A.R3D")}, {"name": "notes.txt", "path": str(self.tmp / "n.txt")}, {"name": "nopath"}]
        tsniff.sniff(items)
        self.assertEqual((items[0]["kind"], items[0]["camId"]), ("camera", "folder:" + str(self.tmp / "x")))
        self.assertEqual(items[1]["kind"], "render")
        self.assertEqual(items[2]["icon"], True)                      # name says logo, no size
        self.assertNotIn("imgW", items[2])
        self.assertEqual(items[3]["kind"], "camera")
        self.assertNotIn("kind", items[4])
        self.assertNotIn("kind", items[5])

    def test_a_file_is_read_once_per_path_and_every_item_gets_the_description(self):
        p = self.put("d/a.mp4", b"..DJI OsmoPocket3\0..")
        opened = []
        real_open = open

        def spy_open(path, *a, **k):
            if str(path) == p:
                opened.append(1)
            return real_open(path, *a, **k)
        items = [{"name": "a.mp4", "path": p}, {"name": "copy.mp4", "path": p}]
        with mock.patch("builtins.open", spy_open):
            tsniff.sniff(items)
        self.assertEqual(len(opened), 1)
        self.assertEqual([i["kind"] for i in items], ["camera", "camera"])
        self.assertEqual(items[0]["camId"], items[1]["camId"])
        # the cache keeps the fields, not the bytes
        self.assertEqual(set(items[1]) - {"name", "path"}, {"kind", "camId"})


class TidyWavInfo(unittest.TestCase):
    def info(self, data):
        return twav.wav_info(data.decode("latin-1"))

    def test_table(self):
        pcm = wav_bytes(48000, 2, [0, 0, 0, 0])
        self.assertEqual(self.info(pcm), {"rate": 48000, "channels": 2, "bits": 16, "dataOffset": 44, "dataSize": 8})
        self.assertEqual(self.info(wav_bytes(8000, 1, [0], fmt_tag=65534, extra_fmt=b"\0" * 24))["rate"], 8000)
        self.assertIsNone(self.info(wav_bytes(48000, 1, [0], fmt_tag=3)))                        # float
        self.assertIsNone(self.info(wav_bytes(48000, 1, [0], bits=8)))
        self.assertIsNone(twav.wav_info("RIFF....WAVEfmt "))
        self.assertIsNone(twav.wav_info("not a wav at all, not a wav at all, not a wav at all"))
        self.assertIsNone(twav.wav_info(""))
        self.assertIsNone(twav.wav_info(None))
        odd = wav_bytes(44100, 1, [1, 2, 3], before_data=chunk(b"LIST", b"abcde"))
        self.assertEqual(self.info(odd)["dataOffset"], 44 + 8 + 6)
        self.assertEqual(twav.wav_info(odd), self.info(odd))                                      # bytes accepted too
        self.assertIsNone(self.info(wav_bytes(48000, 1, [0])[:30]))                              # cut inside fmt
        data_before_fmt = b"RIFF" + struct.pack("<I", 100) + b"WAVE" + b"data" + struct.pack("<I", 4) + b"\0\0\0\0"
        self.assertIsNone(self.info(data_before_fmt))


class TidyWavPower(Tmp):
    @staticmethod
    def reference(x, rate, ch, data_size=None):
        """Plain numpy: mean of squares per frame, nothing clever (compared with allclose, not exactly)."""
        frame = (rate // 1000) * ch
        v = x.astype(np.float64) / 32768.0
        n = len(v) // frame
        return (v[:n * frame].reshape(n, frame) ** 2).mean(axis=1)

    def test_against_a_plain_numpy_reference(self):
        for rate, ch in ((48000, 1), (48000, 2), (16000, 1), (8000, 2), (96000, 1)):
            x = noise(rate * ch * 2 + 37, rate + ch)
            p = self.put("w%d_%d.wav" % (rate, ch), wav_bytes(rate, ch, x))
            got = twav.wav_power(p)
            self.assertEqual(got.dtype, np.float64)
            self.assertTrue(np.allclose(got, self.reference(x, rate, ch), rtol=1e-12, atol=0), (rate, ch))
            self.assertEqual(len(got), (len(x) // ((rate // 1000) * ch)))

    def test_pieces_borders_and_partial_frames(self):
        x = noise(48000 * 2 * 61, 5)                      # 11.7 MB: three 4 MiB pieces
        p = self.put("big.wav", wav_bytes(48000, 2, x))
        got = twav.wav_power(p)
        self.assertEqual(len(got), 61000)
        self.assertTrue(np.allclose(got, self.reference(x, 48000, 2), rtol=1e-12, atol=0))
        # a different piece size gives the very same array (frames cross piece borders in the carry path)
        with mock.patch.object(twav, "PIECE", 100003):
            small = twav.wav_power(p)
        self.assertTrue(np.array_equal(got, small))

    def test_truncated_file_and_odd_sizes(self):
        x = noise(48000 * 2 + 11, 6)
        data = x.astype("<i2").tobytes()
        p = self.put("t.wav", wav_bytes(48000, 1, data[:-1] + b"\x01\x02\x03", data_size=len(data) * 3))   # claims 3x, odd tail
        got = twav.wav_power(p)
        self.assertEqual(len(got), ((len(data) - 1 + 3) // 2) // 48)               # whole frames that are in the file
        empty = self.put("e.wav", wav_bytes(48000, 1, b""))
        self.assertEqual(len(twav.wav_power(empty)), 0)

    def test_errors(self):
        p = self.put("n.wav", b"not a wav" * 100)
        with self.assertRaises(twav.WavPowerError) as cm:
            twav.wav_power(p)
        self.assertEqual(str(cm.exception), "Not a 16-bit WAV: " + p)
        with self.assertRaises(twav.WavPowerError):
            twav.wav_power(self.put("z.wav", wav_bytes(48000, 0, [0, 0])))
        with self.assertRaises(OSError):
            twav.wav_power(str(self.tmp / "missing.wav"))


class TidyDriftGuard(Tmp):
    """A3 #7: a rate that is not a multiple of 1000 Hz must not drift (the JS frame of 44 samples for 44.1 kHz is 8 s per hour)."""

    @staticmethod
    def times(seconds, step=31.7137, first=5.123):
        out, t = [], first
        while t + 0.1 < seconds:
            out.append(t)
            t += step
        return out

    def click_frames(self, rate, seconds, ch=1, name=None):
        t = self.times(seconds)
        p = str(self.tmp / ((name or "c%d_%d") % (rate, ch) + ".wav"))
        write_click_wav(p, rate, seconds, t, channels=ch)
        try:
            return t, onsets(twav.wav_power(p)), p
        finally:
            os.unlink(p)

    def test_a_lazy_60_minute_recording_needs_no_disk_and_does_not_drift(self):
        """Task 8 review M3: the resampler's positions are exact integers, so the error does not grow with time. A file-like
        object generates the 60-minute click track on the fly (nothing is written), the clicks run to the last minute."""
        t = self.times(3600)
        f = LazyClickWav(44100, 3600, t)
        info = {"rate": 44100, "channels": 1, "bits": 16, "dataOffset": 44, "dataSize": f.n * 2}
        power = twav._power_resampled(f, info)
        self.assertEqual(len(power), 3_600_000)
        on = onsets(power)
        self.assertEqual(len(on), len(t))
        self.assertGreater(t[-1], 3560)
        self.assertLessEqual(float(np.max(np.abs(on - np.floor(np.array(t) * 1000)))), 1)

    @unittest.skipUnless(os.environ.get("WHYNOT_SLOW_TESTS") == "1", "set WHYNOT_SLOW_TESTS=1 for the 60-minute files (0.66 GB on disk, ~25 s)")
    def test_44100_matches_48000_within_1_ms_over_60_minutes(self):
        t, a, _ = self.click_frames(48000, 3600)
        _, b, _ = self.click_frames(44100, 3600)
        self.assertEqual(len(a), len(t))
        self.assertEqual(len(a), len(b))
        self.assertGreaterEqual(len(a), 100)
        self.assertLessEqual(int(np.max(np.abs(a - b))), 1)
        # and both are the real click times (ms), within 1 ms
        self.assertLessEqual(float(np.max(np.abs(a - np.floor(np.array(t) * 1000)))), 1)
        self.assertLessEqual(float(np.max(np.abs(b - np.floor(np.array(t) * 1000)))), 1)

    def test_other_rates_and_stereo(self):
        t = None
        for rate, ch in ((22050, 1), (11025, 2), (44100, 2), (32000, 1)):
            t, a, _ = self.click_frames(rate, 300, ch=ch)
            self.assertEqual(len(a), len(t), (rate, ch))
            self.assertLessEqual(float(np.max(np.abs(a - np.floor(np.array(t) * 1000)))), 1, (rate, ch))

    def test_without_the_guard_the_same_file_drifts(self):
        t = self.times(300)
        p = str(self.tmp / "d.wav")
        write_click_wav(p, 44100, 300, t)
        with open(p, "rb") as f:
            info = twav.wav_info(f.read(65536).decode("latin-1"))
            naive = twav._power_direct(f, info, 44)                 # the upstream rule: round(44.1) samples per "ms"
        drift = onsets(naive)[-1] - np.floor(t[-1] * 1000)
        self.assertGreater(abs(drift), 500)                         # ~0.68 s after 5 minutes (8 s per hour)

    def test_framer_carries_frames_across_pieces(self):
        r = np.random.RandomState(4)
        sq = r.rand(10000)
        one = twav._Framer(96, 10 ** 9)
        one.feed(sq)
        cut = twav._Framer(96, 10 ** 9)
        pos = 0
        for n in (1, 95, 96, 97, 5, 1000, 2, 7777, 20):
            cut.feed(sq[pos:pos + n])
            pos += n
        cut.feed(sq[pos:])
        self.assertTrue(np.array_equal(one.result(), cut.result()))
        self.assertEqual(len(one.result()), 10000 // 96)
        capped = twav._Framer(96, 3)
        capped.feed(sq)
        self.assertEqual(len(capped.result()), 3)

    def test_48000_is_not_resampled(self):
        x = noise(48000 * 3, 3)
        p = self.put("n48.wav", wav_bytes(48000, 1, x))
        with mock.patch.object(twav, "_power_resampled", side_effect=AssertionError("resampled")):
            got = twav.wav_power(p)
        self.assertEqual(len(got), 3000)

    def test_resampling_borders_and_piece_size(self):
        x = noise(44100 * 7, 8, scale=3000)
        p = self.put("n441.wav", wav_bytes(44100, 1, x))
        a = twav.wav_power(p)
        with mock.patch.object(twav, "PIECE", 100002):
            b = twav.wav_power(p)
        self.assertTrue(np.array_equal(a, b))                       # piece borders leave no trace
        self.assertEqual(len(a), 7000)
        # a constant signal stays constant through the interpolation
        c = self.put("c441.wav", wav_bytes(44100, 1, np.full(44100 * 2, 10000, dtype="<i2")))
        got = twav.wav_power(c)
        self.assertEqual(len(got), 2000)
        self.assertTrue(np.allclose(got, (10000 / 32768) ** 2, rtol=1e-12))
        # a 1 s file: every sample is inside the recording and the last frames are full
        short = self.put("s.wav", wav_bytes(22050, 1, np.full(22050, 20000, dtype="<i2")))
        self.assertEqual(len(twav.wav_power(short)), 1000)
        tiny = self.put("tiny.wav", wav_bytes(44100, 1, np.full(30, 20000, dtype="<i2")))
        self.assertEqual(len(twav.wav_power(tiny)), 0)


class TidyBackup(Tmp):
    NOW = datetime(2026, 10, 12, 15, 42, 33)

    def test_name_and_copy(self):
        p = self.put("Episode 12.prproj", b"project bytes")
        os.utime(p, (1_700_000_000, 1_700_000_123))
        dst = tbackup.backup(p, self.NOW)
        self.assertEqual(Path(dst).name, "Episode 12 (WhyNot Tidy backup 2026-10-12 154233).prproj")
        self.assertEqual(Path(dst).parent, Path(p).parent)
        self.assertEqual(Path(dst).read_bytes(), b"project bytes")
        self.assertEqual(int(os.stat(dst).st_mtime), 1_700_000_123)

    def test_never_overwrites(self):
        p = self.put("A.prproj", b"one")
        first = tbackup.backup(p, self.NOW)
        Path(p).write_bytes(b"two")
        with self.assertRaises(FileExistsError):
            tbackup.backup(p, self.NOW)
        self.assertEqual(Path(first).read_bytes(), b"one")
        later = tbackup.backup(p, datetime(2026, 10, 12, 15, 42, 34))
        self.assertEqual(Path(later).read_bytes(), b"two")

    def test_missing_project_and_failed_copy_leave_nothing(self):
        with self.assertRaises(FileNotFoundError):
            tbackup.backup(str(self.tmp / "none.prproj"), self.NOW)
        p = self.put("B.prproj", b"x" * 10)
        with mock.patch("shutil.copyfileobj", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                tbackup.backup(p, self.NOW)
        self.assertEqual(sorted(x.name for x in self.tmp.iterdir()), ["B.prproj"])

    def test_a_destination_that_cannot_be_opened_is_never_deleted(self):
        """Task 8 review M2: only a file this call created may be removed. An exclusive open that fails for any reason
        (Windows: PermissionError for a file pending delete or a folder of that name) leaves what is there alone."""
        p = self.put("C.prproj", b"project")
        dst = Path(p).with_name(tbackup.backup_name(p, self.NOW))
        dst.write_bytes(b"somebody else's file")
        real_open = open

        def deny(path, mode="r", *a, **k):
            if str(path) == str(dst) and "x" in mode:
                raise PermissionError(13, "denied")
            return real_open(path, mode, *a, **k)
        with mock.patch("builtins.open", deny):
            with self.assertRaises(PermissionError):
                tbackup.backup(p, self.NOW)
        self.assertEqual(dst.read_bytes(), b"somebody else's file")

    def test_a_folder_in_the_way_is_left_alone(self):
        p = self.put("D.prproj", b"project")
        dst = Path(p).with_name(tbackup.backup_name(p, self.NOW))
        dst.mkdir()
        (dst / "keep.txt").write_bytes(b"k")
        with self.assertRaises(OSError):
            tbackup.backup(p, self.NOW)
        self.assertEqual((dst / "keep.txt").read_bytes(), b"k")

    def test_a_failing_copystat_does_not_fail_a_complete_backup(self):
        """The copy is whole and exclusive; only the attribute copy failed. The backup exists, so the call succeeds."""
        p = self.put("E.prproj", b"project bytes")
        with mock.patch("shutil.copystat", side_effect=OSError("denied")):
            dst = tbackup.backup(p, self.NOW)
        self.assertEqual(Path(dst).read_bytes(), b"project bytes")

    def test_names_without_the_extension_and_current_time(self):
        self.assertEqual(tbackup.backup_name("x/Name.prproj", self.NOW), "Name (WhyNot Tidy backup 2026-10-12 154233).prproj")
        self.assertEqual(tbackup.backup_name("x/Name.PRPROJ", self.NOW), "Name.PRPROJ (WhyNot Tidy backup 2026-10-12 154233).prproj")
        self.assertEqual(tbackup.backup_name("x/.prproj", self.NOW), ".prproj (WhyNot Tidy backup 2026-10-12 154233).prproj")
        self.assertRegex(tbackup.backup_name("x/N.prproj"), r"^N \(WhyNot Tidy backup \d{4}-\d\d-\d\d \d{6}\)\.prproj$")

    def test_is_backup_name(self):
        yes = ["A (Tidy backup 2026-10-12 1542).prproj", "A (WhyNot Tidy backup 2026-10-12 154233).prproj", "(Tidy backup x"]
        no = ["A.prproj", "A Tidy backup.prproj", "A (Hush backup 10:00:00)", "A (tidy backup 1)", "", None]
        self.assertEqual([tbackup.is_backup_name(n) for n in yes], [True] * 3)
        self.assertEqual([tbackup.is_backup_name(n) for n in no], [False] * 6)


class TidyStore(Tmp):
    def store(self):
        return tstore.Store(self.tmp / "engine-home")

    def test_layout_and_log(self):
        s = self.store()
        self.assertEqual(s.home, self.tmp / "engine-home" / "tools" / "tidy")
        self.assertTrue(s.log("hello\nworld\r\nagain"))
        self.assertTrue(s.log("second"))
        lines = s.log_file.read_text(encoding="utf-8").split("\n")
        self.assertEqual(s.log_file, s.home / "logs" / "whynot-tidy.log")
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z  hello world again$")
        self.assertTrue(lines[1].endswith("  second"))
        self.assertEqual(lines[2], "")

    def test_log_never_raises(self):
        """Task 8 review M1: a log line must never stop a run: lone surrogates, a missing security module, anything."""
        s = self.store()
        self.assertTrue(s.log("lone " + chr(0xD83D) + " high and " + chr(0xDE00) + " low"))
        text = s.log_file.read_text(encoding="utf-8")
        self.assertIn("lone \\ud83d high and \\ude00 low", text)                 # backslashreplace: visible, not lost
        self.assertTrue(s.log(tmedia.text_from_value('{"textEditValue":"a\\ud83db"}')))
        self.assertTrue(s.log("emoji " + chr(0x1F600)))
        with mock.patch.object(tstore, "_security", side_effect=ImportError("no serve")):
            self.assertFalse(s.log("x"))
        with mock.patch.object(s, "_dir", side_effect=RuntimeError("boom")):
            self.assertFalse(s.log("x"))
        self.assertFalse(s.log(object.__new__(type("Bad", (), {"__str__": lambda self: 1 / 0}))))

    def test_settings(self):
        s = self.store()
        self.assertEqual(s.load_settings({"a": 1}), {"a": 1})
        self.assertTrue(s.save_settings({"b": 2, "name": "\u0627"}))
        self.assertEqual(s.load_settings({"a": 1, "b": 0}), {"a": 1, "b": 2, "name": "\u0627"})
        self.assertTrue(s.settings_file.is_file())
        self.assertFalse((s.home / "settings.json.tmp").exists())
        s.settings_file.write_text("{broken", encoding="utf-8")
        self.assertEqual(s.load_settings({"a": 1}), {"a": 1})
        s.settings_file.write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(s.load_settings({"a": 1}), {"a": 1})
        self.assertFalse(s.save_settings({"x": object()}))
        self.assertEqual(s.load_settings({}), {})

    def test_temp_wav_and_remove(self):
        s = self.store()
        p = s.temp_wav("cam 1/../x")
        self.assertEqual(p.parent, s.sync_dir)
        self.assertEqual(p.name, "cam_1_.._x.wav")
        self.assertEqual(s.temp_wav("../..").name, "_.wav")
        self.assertEqual(s.temp_wav("...").name, "tmp.wav")
        p.write_bytes(b"x")
        outside = self.tmp / "keep.wav"
        outside.write_bytes(b"y")
        self.assertFalse(s.remove(outside))
        self.assertTrue(outside.exists())
        self.assertFalse(s.remove(s.sync_dir / ".." / "settings.json"))
        self.assertTrue(s.remove(p))
        self.assertFalse(p.exists())
        self.assertTrue(s.remove(p))                                  # already gone: still fine (the caller's finally)

    def test_everything_is_user_only(self):
        from serve import security
        s = self.store()
        s.log("x")
        s.save_settings({"a": 1})
        s.temp_wav("t")
        for d in (s.home, s.logs, s.sync_dir):
            if os.name == "nt":
                self.assertTrue(security.user_only(d, directory=True), d)
            else:
                self.assertEqual(os.stat(d).st_mode & 0o077, 0, d)
        for f in (s.log_file, s.settings_file):
            if os.name == "nt":
                self.assertTrue(security.user_only(f), f)
            else:
                self.assertEqual(os.stat(f).st_mode & 0o077, 0, f)

    def test_default_store_is_under_the_sandboxed_engine_home(self):
        from lib import plat
        self.assertEqual(tstore.home(), plat.engine_home() / "tools" / "tidy")
        self.assertEqual(tstore.settings_path().name, "settings.json")


class TidyPackage(unittest.TestCase):
    def test_headers_and_names(self):
        files = sorted(LIB.glob("*.py"))
        self.assertEqual([f.name for f in files], ["__init__.py", "backup.py", "classify.py", "disk.py", "jsutil.py", "media.py", "plan.py", "sniff.py", "store.py", "sync.py", "wavpower.py"])
        for f in files:
            body = f.read_text(encoding="utf-8")
            lines = body.split("\n")
            self.assertEqual(lines[0], "# SPDX-License-Identifier: GPL-3.0-or-later", f.name)
            self.assertEqual(lines[1], "# \u00a9 2026 The Why Not AI (thewhynot.ai)", f.name)
            self.assertNotIn("hoka", body.lower(), f.name)
            self.assertNotIn("_upstream", f.name)

    def test_the_package_never_writes_next_to_media(self):
        # the only writers: backup (a new file beside the project), store (the engine home), nothing else opens a file for writing
        for name in ("disk.py", "sniff.py", "media.py", "wavpower.py"):
            body = (LIB / name).read_text(encoding="utf-8")
            for bad in ('"wb"', "'wb'", '"ab"', '"xb"', '"r+b"', ".write(", "unlink", "os.remove", "os.rename", "os.replace", ".rename(", "truncate"):
                self.assertNotIn(bad, body, (name, bad))
            for args in re.findall(r"\bopen\(([^)]*)\)", body):
                self.assertTrue(args.rstrip().endswith('"rb"'), (name, args))


# ---------------------------------------------------------------- JS parity (node + adobe/tools)

def rand_items(n, seed):
    r = random.Random(seed)
    names = ["clip", "C0123", "IMG_3886", "DJI_0042", "GX010203", "Interview final", "Ahmed edit", "render 3", "EDIT", "Edit.v2",
             "caf\u00e9 edit", "x\u212aedit", "A001C002_220101", "00001", "Company Logo", "photo", "icon", "emoji_2", "notes", "export_final",
             "MVI_1234", "P1010101", "PXL_2026", "VID_001", "x edit y", "re\u00a0edit"]
    exts = [".mp4", ".MOV", ".mkv", ".MTS", ".png", ".JPG", ".jpeg", ".gif", ".webp", ".svg", ".txt", ".wav", ".r3d", ".BRAW", ".insv", ".m2ts", ""]
    tails = ["", "", "\n", "\r", " ", chr(0x2028)]
    dirs = ["/RAW/A", "C:\\RAW\\Cam B", "/x/Cam B", "", "/", "\\\\NAS\\share\\Cam C", "/a/b/c"]
    texts = ["", None, "DJI OsmoPocket3\0..", "..DJI Mavic 3 Classic\n..", "DJI Pocket", "com.apple.quicktime.model..iPhone 16 Pro Max",
             "iPhone 15 Pro", "iPhone 8 Plus e", "ILCE-7M4", "ZV-E10 ", "FX3 x", "EOS R5 C", "HERO12 Black", "Insta360 X3", "BMPCC6K",
             "NonRealTimeMeta", "Lavf61.7.100", "CreatorTool", "GoPro", "Canon", "samsung", "DaVinci Resolve", "CapCut", "HandBrake",
             "Mainconcept DJI Osmo", "caf\u00e9 DJI OsmoAction4\u00e9", "DJI Neo\n", "DJI Avata 2 ", "DJI Air 3S\r\n"]
    out = []
    for i in range(n):
        name = r.choice(names) + r.choice(exts) + r.choice(tails)
        path = r.choice(dirs) + r.choice("/\\") + name if r.random() < 0.9 else r.choice(["", None, name])
        it = {"nodeId": "n%d" % i, "name": name if r.random() < 0.95 else None}
        if path is not None:
            it["path"] = path
        out.append((it, r.choice(texts) if r.random() < 0.85 else None))
    return out


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyMediaParity(unittest.TestCase):
    LOAD = ["js/media.js"]

    def test_describe_on_400_seeded_items_and_the_test_media_fixtures(self):
        fx = need_fixtures(self)
        cases = rand_items(400, 11)
        dji = fx["DJI"]
        for name, path, text in (("Script 1 - 2.mp4", "/Volumes/X/RAW/Script 1/Script 1 - 2.mp4", dji), ("C0001.MP4", "/x/Cam B/C0001.MP4", None),
                                 ("a.png", "/x/a.png", "".join(chr(c) for c in [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0, 0, 0, 64, 0, 0, 0, 48])),
                                 ("notes.txt", "/x/notes.txt", "abc"), ("A.R3D", "/r/A.R3D", None), ("clip.braw", "/r/clip.braw", None),
                                 ("x.mp4", "/x.mp4", fx["IPHONE"]), ("y.mp4", "/y.mp4", fx["AE"]), ("z.mp4", "/z.mp4", fx["COMPOSE"])):
            cases.append(({"name": name, "path": path}, text))
        calls = [call("TidyMedia.describe", it, text) for it, text in cases]
        js = run_js(self, PORT, self.LOAD, calls)
        for (it, text), want in zip(cases, js):
            got = tmedia.describe(dict(it), text)
            self.assertEqual(got, want, (it, text))
        self.assertGreater(sum(1 for r in js if "kind" in r), 50)
        self.assertGreater(sum(1 for r in js if "icon" in r), 20)

    def test_pure_functions_and_regex_corner_cases(self):
        fx = need_fixtures(self)
        texts = [t for _, t in rand_items(300, 12)] + [fx["DJI"], fx["IPHONE"], "DJI Osmo", "DJI Osmo\n", "DJI Osmo Action 5 Pro!", "iPhone 16 Pro Max Plus e mini"]
        names = [it.get("name") for it, _ in rand_items(300, 13)] + ["00001.MTS", "00001.MTS\n", "x\u00e9edit.mp4", "xedit.mp4", " edit ", "EDIT", "re_edit"]
        calls = [call("TidyMedia.cameraModel", t) for t in texts]
        calls += [call("TidyMedia.videoKind", t, n) for t, n in zip(texts * 2, names)]
        calls += [call("TidyMedia.videoKind", "", n) for n in names]                       # names alone decide when the file says nothing
        calls += [call("TidyMedia.needsBytes", {"path": n}) for n in names]
        calls += [call("TidyMedia.isIcon", n, e, s) for n, e, s in (("a", "svg", None), ("Logo", "png", None), ("big", "png", {"w": 513, "h": 9}),
                                                                   ("small", "png", {"w": 512, "h": 512}), (None, "jpg", None), ("emoji", "", None))]
        tvals = TEXT_VALUES
        calls += [call("TidyMedia.textFromValue", v) for v in tvals]
        js = run_js(self, PORT, self.LOAD, calls)
        want = [tmedia.camera_model(t) for t in texts]
        want += [tmedia.video_kind(t, n) for t, n in zip(texts * 2, names)]
        want += [tmedia.video_kind("", n) for n in names]
        want += [tmedia.needs_bytes({"path": n}) for n in names]
        want += [tmedia.is_icon(n, e, s) for n, e, s in (("a", "svg", None), ("Logo", "png", None), ("big", "png", {"w": 513, "h": 9}),
                                                         ("small", "png", {"w": 512, "h": 512}), (None, "jpg", None), ("emoji", "", None))]
        want += [tmedia.text_from_value(v) for v in tvals]
        self.assertEqual(js, want)
        # the escaped emoji really is one character, and a lone surrogate stays lone (JS strings are UTF-16)
        by_text = dict(zip(tvals, js[-len(tvals):]))
        self.assertEqual(by_text['{"textEditValue":"hi \\ud83d\\ude00"}'], "hi " + chr(0x1F600))
        self.assertEqual(by_text['{"textEditValue":"a\\ud83db"}'], "a" + chr(0xD83D) + "b")

    def test_image_sizes_on_generated_headers(self):
        r = random.Random(14)
        heads = []
        for i in range(250):
            kind = r.choice(["png", "jpg", "gif", "webp-x", "webp-l", "webp-8", "junk"])
            body = bytes(r.randrange(256) for _ in range(r.choice([0, 10, 23, 24, 25, 28, 30, 31, 40, 80])))
            if kind == "png":
                s = b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + bytes(r.randrange(256) for _ in range(8)) + body
            elif kind == "jpg":
                s = b"\xff\xd8\xff\xe0\0\x10JFIF\0\x01\x01\0\0\x01\0\x01\0\0" + r.choice([b"\xff\xc0\0\x11\x08", b"\xff\xc2\0\x11\x08", b"\xff\xc4\0\x11\x08\xff\xe1\0\x04ab\xff\xc0\0\x11\x08"]) + body
            elif kind == "gif":
                s = b"GIF89a" + bytes(r.randrange(256) for _ in range(4)) + body
            elif kind == "webp-x":
                s = b"RIFF\0\0\0\0WEBPVP8X" + body
            elif kind == "webp-l":
                s = b"RIFF\0\0\0\0WEBPVP8L" + body
            elif kind == "webp-8":
                s = b"RIFF\0\0\0\0WEBPVP8 " + body
            else:
                s = body
            heads.append(s.decode("latin-1"))
        js = run_js(self, PORT, self.LOAD, [call("TidyMedia.imageSize", h, "x") for h in heads])
        self.assertEqual(js, [tmedia.image_size(h, "x") for h in heads])
        self.assertGreater(sum(1 for r_ in js if r_), 100)


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyWavInfoParity(Tmp):
    def test_headers(self):
        r = random.Random(15)
        blobs = [wav_bytes(48000, 2, [0] * 8), wav_bytes(44100, 1, [1, 2, 3], before_data=chunk(b"LIST", b"abcde")),
                 wav_bytes(8000, 1, [0], fmt_tag=65534, extra_fmt=b"\0" * 24), wav_bytes(48000, 1, [0], fmt_tag=3), wav_bytes(48000, 1, [0], bits=8),
                 wav_bytes(48000, 1, [0], before_data=chunk(b"JUNK", b"x" * 100) + chunk(b"LIST", b"y" * 33)),
                 b"RIFF....WAVEfmt ", b"", b"x" * 40, wav_bytes(48000, 1, [0])[:30], wav_bytes(48000, 1, [0])[:20],
                 b"RIFF" + struct.pack("<I", 100) + b"WAVE" + b"data" + struct.pack("<I", 4) + b"\0\0\0\0",
                 wav_bytes(48000, 1, [0], data_size=0xFFFFFFFF), wav_bytes(96000, 6, [0] * 12)]
        base = wav_bytes(48000, 2, [0] * 16, before_data=chunk(b"LIST", b"abc"))
        for _ in range(200):                                    # byte-flipped copies of a good header
            b = bytearray(base)
            for _ in range(r.choice([1, 2, 3])):
                b[r.randrange(min(len(b), 80))] = r.randrange(256)
            blobs.append(bytes(b[:r.choice([len(b), 40, 60, 80])]))
        js = run_js(self, PORT, ["js/sync.js"], [call("TidySync.wavInfo", b.decode("latin-1")) for b in blobs])
        self.assertEqual(js, [twav.wav_info(b.decode("latin-1")) for b in blobs])
        self.assertGreater(sum(1 for x in js if x), 60)


HARNESS = r"""
'use strict';
// loads the UPSTREAM engine.js (the owner's Node code) the way the panel does: window is the global object, require is
// node's, TidyMedia / TidySync are the upstream modules. HOME / USERPROFILE point at a temp folder (engine.js makes its
// ~/Library/Application Support/Tidy folder when it loads).
var fs = require('fs'), vm = require('vm'), path = require('path');
globalThis.window = globalThis;
globalThis.require = require;
var root = process.argv[2], spec = JSON.parse(fs.readFileSync(process.argv[3], 'utf8')), out = {};
['js/media.js', 'js/sync.js', 'js/engine.js'].forEach(function (f) {
    vm.runInThisContext(fs.readFileSync(path.join(root, f), 'utf8'), { filename: f });
});
var E = window.TidyEngine;
if (spec.disk) { out.disk = E.diskInfo(spec.disk); }
if (spec.sniff) { out.sniff = E.sniff(spec.sniff); }
if (spec.wav) {
    out.wav = spec.wav.map(function (f) {
        try { return Array.from(E.wavPower(f)); } catch (e) { return { error: String(e.message) }; }
    });
}
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(NODE, "node is not installed")
@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class TidyEngineParity(Tmp):
    def js(self, spec):
        home = self.tmp / "jshome"
        home.mkdir(exist_ok=True)
        script = self.tmp / "harness.js"
        script.write_text(HARNESS, encoding="utf-8")
        req = self.tmp / "spec.json"
        req.write_text(json.dumps(spec), encoding="utf-8")
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
        p = subprocess.run([NODE, str(script), str(UPSTREAM), str(req)], capture_output=True, text=True, encoding="utf-8",
                           timeout=600, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout.rstrip("\n").split("\n")[-1])

    def test_disk_info(self):
        f = self.put("a/Clip.mp4", b"x" * 1234)
        items = [{"path": ""}, {"name": "no path"}, {"path": f}, {"path": f}, {"path": str(self.tmp / "a")}, {"path": str(self.tmp / "missing.mp4")}]
        js = self.js({"disk": items})["disk"]
        self.assertEqual(tdisk.disk_info([dict(i) for i in items]), js)

    def test_sniff_on_generated_files(self):
        dji = b"..DJI OsmoPocket3\0.."
        png = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0, 0, 0, 64, 0, 0, 0, 48]) + b"\0" * 100000
        files = {
            "v/head.mp4": b"ftypisom" + dji + b"\0" * 1000,
            "v/tail.mp4": b"ftypisom" + b"\0" * (5 * 1024 * 1024) + dji,
            "v/mid.mp4": b"ftypisom" + b"\0" * (3 * 1024 * 1024) + dji + b"\0" * (3 * 1024 * 1024),
            "v/exact.mp4": b"\0" * (2 * 1024 * 1024) + b"DJI Mavic3\0",
            "v/render.mov": b"ftypqt  ..Mainconcept..DJI OsmoAction4\0\0",
            "v/iphone.MOV": b"ftypqt  ..com.apple.quicktime.model..iPhone 16 Pro Max..",
            "v/C0001.MP4": b"nothing",
            "v/empty.mp4": b"",
            "i/a.png": png, "i/photo.png": png[:16] + struct.pack(">II", 4000, 3000) + b"\0" * 100000,
            "i/x.svg": b"<svg/>", "i/logo.jpg": b"\xff\xd8\xff\xe0\0\x10JFIF\0\x01\x01\0\0\x01\0\x01\0\0\xff\xc0\0\x11\x08\x04\x38\x07\x80\x03" + b"\0" * 50,
            "i/big.gif": b"GIF89a" + struct.pack("<HH", 1280, 720) + b"\0" * 40,
            "o/notes.txt": b"abc",
        }
        paths = {k: self.put(k, v) for k, v in files.items()}
        items = []
        for i, (k, p) in enumerate(paths.items()):
            items.append({"nodeId": "n%d" % i, "name": Path(p).name, "path": p})
        items.append({"nodeId": "dup", "name": "dup.mp4", "path": paths["v/tail.mp4"]})            # the same file again: cached
        items.append({"nodeId": "gone", "name": "C9999.MP4", "path": str(self.tmp / "v" / "gone" / "C9999.MP4")})
        items.append({"nodeId": "gone2", "name": "clip.png", "path": str(self.tmp / "i" / "none" / "clip.png")})
        items.append({"nodeId": "raw", "name": "A.R3D", "path": str(self.tmp / "r" / "A.R3D")})
        (self.tmp / "v" / "folder.mp4").mkdir()
        items.append({"nodeId": "dir", "name": "folder.mp4", "path": str(self.tmp / "v" / "folder.mp4")})
        items.append({"nodeId": "np", "name": "nopath"})
        js = self.js({"sniff": items})["sniff"]
        got = tsniff.sniff([dict(i) for i in items])
        self.assertEqual(got, js)
        by = {i["nodeId"]: i for i in got}
        self.assertEqual(by["n1"]["kind"], "camera")                                            # tail.mp4: tag in the last 2 MiB
        self.assertEqual(by["n2"]["kind"], "render")                                            # mid.mp4: tag in the middle, not read
        self.assertEqual(by["dup"]["kind"], "camera")

    CORPUS = [
        # name, rate, channels, frames, kwargs (as wav_bytes), raw data bytes override
        ("mono48", 48000, 1, 3 * 48000, {}),
        ("stereo48_big", 48000, 2, 61 * 48000, {}),                       # 11.7 MB: several 4 MiB pieces
        ("odd_chunk", 16000, 1, 2 * 16000, {"before_data": chunk(b"LIST", b"abcde")}),
        ("kHz8_ext", 8000, 1, 8000 * 3, {"fmt_tag": 65534, "extra_fmt": b"\0" * 24}),
        ("hi96", 96000, 1, 96000, {}),
        ("quad32", 32000, 4, 32000 * 2, {}),
        ("ms_odd", 24000, 2, 24000 * 2 + 5, {}),
    ]

    def test_wav_power_on_generated_wavs_is_identical(self):
        paths = []
        for name, rate, ch, frames, kw in self.CORPUS:
            x = noise(frames * ch, sum(map(ord, name)))
            paths.append(self.put(name + ".wav", wav_bytes(rate, ch, x, **kw)))
        x = noise(48000 * 2 * 3 + 7, 21)
        data = x.tobytes()
        paths.append(self.put("frame_multiple.wav", wav_bytes(48000, 2, data + b"\x05\x06\x07", data_size=len(data) + 3)))   # data size not a multiple of the frame
        paths.append(self.put("truncated.wav", wav_bytes(48000, 2, data[:-1], data_size=len(data) * 4)))                    # claims 4x, odd end
        paths.append(self.put("big_truncated.wav", wav_bytes(48000, 2, noise(48000 * 2 * 40, 22), data_size=48000 * 2 * 2 * 90)))   # several pieces, then EOF
        paths.append(self.put("empty.wav", wav_bytes(48000, 1, b"")))
        paths.append(self.put("junk.wav", b"this is not a wav file" * 50))
        paths.append(self.put("float.wav", wav_bytes(48000, 1, [0, 0], fmt_tag=3)))
        js = self.js({"wav": paths})["wav"]
        self.assertEqual(len(js), len(paths))
        for p, want in zip(paths, js):
            if isinstance(want, dict):
                with self.assertRaises(twav.WavPowerError) as cm:
                    twav.wav_power(p)
                self.assertEqual(str(cm.exception), want["error"], p)
                continue
            got = twav.wav_power(p)
            self.assertEqual(got.dtype, np.float64)
            self.assertEqual(len(got), len(want), p)
            self.assertTrue(np.array_equal(got, np.array(want, dtype=np.float64)), p)      # bit for bit
        self.assertGreater(sum(len(w) for w in js if isinstance(w, list)), 100000)


if __name__ == "__main__":
    unittest.main()
