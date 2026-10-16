# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 tools track, N1 - WhyNot Hush characterization tests: the owner's pure modules pinned as they behave today.

Hush (the silence and filler-word cutter) has no upstream tests, so before it is ported this file records what
`adobe/tools/hush/_upstream/js/{wav,detect,fillers}.js` actually does, one test per item of the portability audit
(docs/superpowers/specs/addendum-a/portability-audit.md section 6.3, items 1-11) and per FR of the Hush PRD
(section 4.3, FR-8..FR-16; section 11 "Pure").

* The JS runs under node through adobe/tools/_harness/js_runner.js (the modules load the way the panel's jsc harness
  loads them: `window` is the global object, files in order).
* Expected values are written in Python: PRD formulas, or constants hand-derived with the arithmetic in a comment.
  They are never pasted from JS output. Where upstream differs from the PRD the test asserts what upstream does and
  says so ("QUIRK" / "PRD vs upstream" in the comment).
* WAV fixtures are generated into a temp dir by the tests (no binary fixtures are committed).
* `HushCharacterizationMixin.ROOT` is the tool root (a directory holding js/wav.js, js/detect.js, js/fillers.js).
  `HushCharacterizationUpstream` runs every test on the owner's code; `HushCharacterizationPort` (3.0 N3) runs the same
  tests on the port (ROOT = adobe/tools/hush/src), overriding only the one expectation the port changes on purpose
  (`HushDetect.fmt` near a rounding edge). Nothing below hard-codes a root inside a test method.
Run:  bash tools/test.sh -p test_hush_characterization.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
import wave  # noqa: E402
from pathlib import Path  # noqa: E402

SK = Path(__file__).resolve().parents[1]
REPO = SK.parent
ADOBE_TOOLS = REPO / "adobe" / "tools"
RUNNER = ADOBE_TOOLS / "_harness" / "js_runner.js"
NODE = shutil.which("node")
# the plugin zip ships whynot-cut/tests but not adobe/: without adobe/tools these tests skip with a reason
TOOLS_PRESENT = RUNNER.is_file() and (ADOBE_TOOLS / "hush" / "_upstream" / "js").is_dir()
NO_TOOLS = "adobe/tools is not in this checkout (the plugin zip ships the tests but not adobe/)"

LOAD = ["js/wav.js", "js/detect.js", "js/fillers.js"]


def run_js(tc, root, load, calls):
    """Run `calls` through js_runner.js with `load` (files relative to root); return the list of results."""
    with tempfile.TemporaryDirectory() as td:
        req = Path(td) / "request.json"
        req.write_text(json.dumps({"load": load, "calls": calls}), encoding="utf-8")
        p = subprocess.run([NODE, str(RUNNER), str(root), str(req)], capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
    tc.assertEqual(p.returncode, 0, p.stderr)
    lines = p.stdout.strip().splitlines()
    tc.assertTrue(lines, "runner printed nothing: " + p.stderr)
    out = json.loads(lines[-1])["results"]
    tc.assertEqual(len(out), len(calls))
    return out


def call(fn, *args, typed=None, bytes_file=None):
    c = {"fn": fn, "args": list(args)}
    if typed:
        c["typed"] = {str(k): v for k, v in typed.items()}
    if bytes_file:
        c["bytes_file"] = str(bytes_file)
    return c


def FILE(path):
    return {"$file": str(path)}


# ---------------------------------------------------------------- WAV writers (stdlib wave / manual RIFF) ----------
GUID_TAIL = bytes([0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71])


def chunk(cid, payload):
    """A RIFF chunk: id, little-endian length, payload, pad byte when the length is odd."""
    return cid + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b"")


def fmt_payload(tag, channels, rate, bits, extensible_sub=None, cb_size=None):
    block = channels * bits // 8
    p = struct.pack("<HHIIHH", tag, channels, rate, rate * block, block, bits)
    if extensible_sub is not None:  # WAVE_FORMAT_EXTENSIBLE: cbSize 22, validBits, channel mask, GUID (sub-format first)
        p += struct.pack("<HHI", 22, bits, 4) + struct.pack("<H", extensible_sub) + GUID_TAIL
    elif cb_size is not None:
        p += struct.pack("<H", cb_size)
    return p


def data_chunk(payload, length_field=None):
    if length_field is None:
        return chunk(b"data", payload)
    return b"data" + struct.pack("<I", length_field) + payload  # a lying length: no pad byte


def riff(*chunks):
    body = b"WAVE" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def pcm16(values):
    return b"".join(struct.pack("<h", v) for v in values)


def pcm24(values):
    return b"".join(struct.pack("<i", v)[:3] for v in values)  # little-endian two's complement, low three bytes


def pcm32(values):
    return b"".join(struct.pack("<i", v) for v in values)


def f32(values):
    return b"".join(struct.pack("<f", v) for v in values)


def f64(values):
    return b"".join(struct.pack("<d", v) for v in values)


def u8(values):
    return bytes(values)


def sine16(amp, hz, rate, frames):
    """16-bit sine of peak amplitude `amp` (0..1) as ints."""
    return [int(round(amp * 32768 * math.sin(2 * math.pi * hz * n / rate))) for n in range(frames)]


def db_rms_sine(amp):
    """PRD FR-5: RMS in dBFS of a sine of peak `amp`: 20*log10(amp / sqrt(2))."""
    return 20 * math.log10(amp / math.sqrt(2))


def env_of(*runs):
    """An envelope from (hops, dB) runs at 10 ms per hop."""
    out = []
    for n, level in runs:
        out.extend([float(level)] * n)
    return out


def js_round(x):
    """JavaScript Math.round (half up), not Python's banker's rounding."""
    return math.floor(x + 0.5)


LOUD, QUIET = -20.0, -60.0


class HushCharacterizationMixin:
    """Every test of the pure Hush modules. Subclasses set ROOT (and mix in unittest.TestCase)."""

    ROOT = ADOBE_TOOLS / "hush" / "_upstream"

    def setUp(self):
        if not NODE:
            self.skipTest("node is not installed")
        if not TOOLS_PRESENT:
            self.skipTest(NO_TOOLS)
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    # ---- helpers
    def js(self, calls, load=LOAD):
        return run_js(self, self.ROOT, load, calls)

    def one(self, fn, *args, **kw):
        return self.js([call(fn, *args, **kw)])[0]

    def put(self, name, data):
        p = self.tmp / name
        p.write_bytes(data)
        return p

    def close(self, got, want, tol=1e-9, path="result"):
        """Structural compare: numbers within tol, everything else equal; dicts must have the same keys."""
        if isinstance(want, dict):
            self.assertIsInstance(got, dict, path)
            self.assertEqual(sorted(got), sorted(want), path)
            for k in want:
                self.close(got[k], want[k], tol, path + "." + k)
        elif isinstance(want, (list, tuple)):
            self.assertIsInstance(got, list, path)
            self.assertEqual(len(got), len(want), path + ": length")
            for i, (g, w) in enumerate(zip(got, want)):
                self.close(g, w, tol, "%s[%d]" % (path, i))
        elif isinstance(want, float) or (isinstance(want, int) and not isinstance(want, bool)
                                         and isinstance(got, float)):
            self.assertIsInstance(got, (int, float), path)
            self.assertAlmostEqual(got, want, delta=tol, msg=path)
        else:
            self.assertEqual(got, want, path)

    # ================================================================ 1. wav.js ================================
    def test_header_16bit_pcm_mono_written_by_stdlib_wave(self):
        p = self.tmp / "mono16.wav"
        samples = sine16(0.5, 1000, 48000, 4800)
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(pcm16(samples))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        # 44-byte canonical header; the data chunk holds 4800 frames * 2 bytes
        self.assertEqual(h, {"format": 1, "channels": 1, "rate": 48000, "bits": 16, "dataOff": 44, "dataLen": 9600})
        d = self.one("HushWav.decode", FILE(p))
        self.assertEqual(d["sampleRate"], 48000)
        self.assertEqual(d["channels"], 1)
        self.assertEqual(d["samples"], [v / 32768 for v in samples])  # int16 / 32768, exact in float32

    def test_decode_24bit_pcm_sign_extension(self):
        ints = [0, 1, -1, 4194304, -4194304, 8388607, -8388608, 123456, -123456]
        p = self.put("pcm24.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 44100, 24)), chunk(b"data", pcm24(ints))))
        d = self.one("HushWav.decode", FILE(p))
        self.assertEqual(d["sampleRate"], 44100)
        self.assertEqual(d["samples"], [v / 8388608 for v in ints])  # |v| < 2^24: exact in float32
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual((h["format"], h["bits"], h["dataLen"]), (1, 24, 27))

    def test_decode_32bit_int_pcm(self):
        ints = [0, 0x40000000, -0x40000000, 0x7FFF0000, -0x80000000]
        p = self.put("pcm32.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 32)), chunk(b"data", pcm32(ints))))
        d = self.one("HushWav.decode", FILE(p))
        self.assertEqual(d["samples"], [v / 2147483648 for v in ints])  # each is a multiple of 2^16: exact in float32

    def test_decode_8bit_unsigned_pcm(self):
        vals = [128, 255, 0, 192, 64]
        p = self.put("pcm8.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 8000, 8)), chunk(b"data", u8(vals))))
        d = self.one("HushWav.decode", FILE(p))
        self.assertEqual(d["samples"], [(v - 128) / 128 for v in vals])  # unsigned, centred on 128

    def test_decode_32bit_float_format3(self):
        vals = [0.25, -0.5, 1.0, 0.125, -1.0, 0.0]
        p = self.put("f32.wav", riff(chunk(b"fmt ", fmt_payload(3, 1, 48000, 32)), chunk(b"data", f32(vals))))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual((h["format"], h["bits"], h["dataLen"]), (3, 32, 24))
        self.assertEqual(self.one("HushWav.decode", FILE(p))["samples"], vals)

    def test_decode_64bit_float_format3(self):
        vals = [0.25, -0.75, 0.5]
        p = self.put("f64.wav", riff(chunk(b"fmt ", fmt_payload(3, 1, 48000, 64)), chunk(b"data", f64(vals))))
        self.assertEqual(self.one("HushWav.decode", FILE(p))["samples"], vals)

    def test_extensible_pcm_subformat_is_read_as_pcm(self):
        ints = [1000, -2000, 3000, -4000]
        p = self.put("ext_pcm.wav", riff(chunk(b"fmt ", fmt_payload(0xFFFE, 1, 48000, 16, extensible_sub=1)),
                                         chunk(b"data", pcm16(ints))))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual(h, {"format": 1, "channels": 1, "rate": 48000, "bits": 16, "dataOff": 12 + 8 + 40 + 8,
                             "dataLen": 8})
        self.assertEqual(self.one("HushWav.decode", FILE(p))["samples"], [v / 32768 for v in ints])

    def test_extensible_float_subformat_is_read_as_float(self):
        vals = [0.5, -0.25, 0.125]
        p = self.put("ext_f32.wav", riff(chunk(b"fmt ", fmt_payload(0xFFFE, 1, 48000, 32, extensible_sub=3)),
                                         chunk(b"data", f32(vals))))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual(h["format"], 3)
        self.assertEqual(self.one("HushWav.decode", FILE(p))["samples"], vals)

    def test_extensible_with_short_fmt_chunk_keeps_0xFFFE(self):
        # QUIRK: the sub-format is only read when the fmt chunk is >= 26 bytes; an 18-byte fmt tagged 0xFFFE keeps
        # format 65534 (the samples are then decoded as integers by width, not as floats).
        p = self.put("ext_short.wav", riff(chunk(b"fmt ", fmt_payload(0xFFFE, 1, 48000, 16, cb_size=0)),
                                           chunk(b"data", pcm16([16384, -16384]))))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual(h["format"], 0xFFFE)
        self.assertEqual(self.one("HushWav.decode", FILE(p))["samples"], [0.5, -0.5])

    def test_extensible_sub_format_needs_a_fmt_chunk_of_at_least_26_bytes(self):
        # the sub-format tag sits at fmt-payload bytes 24..25: 26 bytes is enough (truncated GUID), 24 is not
        base = fmt_payload(0xFFFE, 1, 48000, 16, extensible_sub=1)
        ok = self.put("ext26.wav", riff(chunk(b"fmt ", base[:26]), chunk(b"data", pcm16([16384]))))
        short = self.put("ext24.wav", riff(chunk(b"fmt ", base[:24]), chunk(b"data", pcm16([16384]))))
        self.assertEqual(self.one("HushWav.header", FILE(ok), {"$dataview": 0})["format"], 1)
        self.assertEqual(self.one("HushWav.header", FILE(short), {"$dataview": 0})["format"], 0xFFFE)

    def test_odd_length_chunk_padding_before_data(self):
        ints = [100, -200, 300]
        fmt = chunk(b"fmt ", fmt_payload(1, 1, 48000, 16))
        lst = chunk(b"LIST", b"INFOx")  # 5 bytes: odd, so the writer adds a pad byte
        self.assertEqual(len(lst), 8 + 5 + 1)
        p = self.put("odd.wav", riff(fmt, lst, chunk(b"data", pcm16(ints))))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual(h["dataOff"], 12 + len(fmt) + len(lst) + 8)  # the pad byte is skipped
        self.assertEqual(h["dataLen"], 6)
        self.assertEqual(self.one("HushWav.decode", FILE(p))["samples"], [v / 32768 for v in ints])
        # and an odd chunk before fmt
        p2 = self.put("odd2.wav", riff(lst, fmt, chunk(b"data", pcm16(ints))))
        h2 = self.one("HushWav.header", FILE(p2), {"$dataview": 0})
        self.assertEqual((h2["rate"], h2["dataLen"]), (48000, 6))

    def test_streamed_data_length_zero_means_rest_of_file(self):
        ints = [5, -5, 7, -7, 9]
        p = self.put("stream0.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16)),
                                         data_chunk(pcm16(ints), length_field=0)))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual(h["dataLen"], 10)
        self.assertEqual(len(self.one("HushWav.decode", FILE(p))["samples"]), 5)

    def test_streamed_data_length_ffffffff_means_rest_of_file(self):
        ints = [5, -5, 7, -7, 9, 11]
        p = self.put("streamF.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16)),
                                         data_chunk(pcm16(ints), length_field=0xFFFFFFFF)))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual(h["dataLen"], 12)
        self.assertEqual(self.one("HushWav.decode", FILE(p))["samples"], [v / 32768 for v in ints])

    def test_data_length_larger_than_file_is_clamped_to_the_file(self):
        p = self.put("long.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16)),
                                      data_chunk(pcm16([1, 2, 3]), length_field=0x7FFFFFF0)))
        self.assertEqual(self.one("HushWav.header", FILE(p), {"$dataview": 0})["dataLen"], 6)

    def test_data_length_shorter_than_file_ignores_trailing_chunks_and_partial_frame(self):
        ints = [10, 20, 30]
        data = chunk(b"data", pcm16(ints) + b"\x01")  # 7 bytes: one stray byte, not a whole 16-bit frame
        p = self.put("trail.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16)), data,
                                       chunk(b"LIST", b"INFOabcd")))
        h = self.one("HushWav.header", FILE(p), {"$dataview": 0})
        self.assertEqual(h["dataLen"], 7)
        self.assertEqual(self.one("HushWav.decode", FILE(p))["samples"], [v / 32768 for v in ints])  # floor(7/2)=3

    def test_stereo_is_mixed_down_to_the_mean(self):
        left, right = [16384, -8192, 0, 32767], [-8192, -8192, 16384, -32768]
        inter = []
        for a, b in zip(left, right):
            inter += [a, b]
        p = self.put("stereo.wav", riff(chunk(b"fmt ", fmt_payload(1, 2, 48000, 16)), chunk(b"data", pcm16(inter))))
        d = self.one("HushWav.decode", FILE(p))
        self.assertEqual(d["channels"], 2)
        # mean of the two channels, each int16/32768: (0.5 + -0.25)/2 = 0.125, (-0.25 + -0.25)/2 = -0.25, ...
        want = [((a / 32768) + (b / 32768)) / 2 for a, b in zip(left, right)]
        self.close(d["samples"], want, tol=1e-7)  # float32 storage of the mean
        self.assertEqual(d["samples"][0], 0.125)
        self.assertEqual(d["samples"][1], -0.25)
        self.assertEqual(len(d["samples"]), 4)  # frames, not samples

    def test_not_a_wav_file_errors(self):
        bad = {
            "text": b"this is not a wav file at all",
            "riff_but_not_wave": b"RIFF" + struct.pack("<I", 4) + b"AVI " + b"\0" * 16,
            "empty": b"",
            "short": b"RIFF",
        }
        calls = [call("HushWav.decode", FILE(self.put(n + ".wav", b))) for n, b in bad.items()]
        for r in self.js(calls):
            self.assertEqual(r, {"error": "Not a WAV file"})

    def test_missing_fmt_or_data_chunk_errors(self):
        no_data = self.put("nodata.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16))))
        no_fmt = self.put("nofmt.wav", riff(chunk(b"data", pcm16([1, 2]))))
        for r in self.js([call("HushWav.decode", FILE(no_data)), call("HushWav.decode", FILE(no_fmt)),
                          call("HushWav.envelope", FILE(no_data), 0.01)]):
            self.assertEqual(r, {"error": "WAV has no fmt/data chunk"})

    def test_envelope_known_sine_levels_16bit(self):
        # 1 kHz at 48 kHz: 10 ms = 480 samples = exactly 10 cycles, so each hop's RMS is amp/sqrt(2) (+ int16 rounding)
        out = []
        for amp in (0.5, 0.1, 0.9):
            p = self.put("sine%s.wav" % amp, riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16)),
                                                 chunk(b"data", pcm16(sine16(amp, 1000, 48000, 24000)))))
            out.append((amp, self.one("HushWav.envelope", FILE(p), 0.01)))
        for amp, r in out:
            self.assertEqual(r["sampleRate"], 48000)
            self.assertAlmostEqual(r["duration"], 24000 / 48000, places=12)  # frames / rate
            self.assertEqual(len(r["env"]), math.ceil(24000 / 480))  # 50 hops
            for v in r["env"]:
                self.assertAlmostEqual(v, db_rms_sine(amp), delta=0.01)
        self.assertAlmostEqual(out[0][1]["env"][0], -9.03, delta=0.01)  # 20*log10(0.5/1.41421) = -9.0309

    def test_envelope_digital_silence_is_minus_100(self):
        p = self.put("zero.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16)), chunk(b"data", pcm16([0] * 4800))))
        r = self.one("HushWav.envelope", FILE(p), 0.01)
        self.assertEqual(r["env"], [-100.0] * 10)
        self.assertEqual(r["duration"], 0.1)

    def test_envelope_floor_boundary_1e_minus_5(self):
        # the floor test is `rms > 1e-5` (float32 file so tiny levels are representable): 5e-6 -> -100, 2e-5 -> -93.98
        vals = {"below": 5e-6, "above": 2e-5}
        p = {k: self.put(k + ".wav", riff(chunk(b"fmt ", fmt_payload(3, 1, 48000, 32)),
                                          chunk(b"data", f32([v] * 480)))) for k, v in vals.items()}
        below = self.one("HushWav.envelope", FILE(p["below"]), 0.01)["env"]
        above = self.one("HushWav.envelope", FILE(p["above"]), 0.01)["env"]
        self.assertEqual(below, [-100.0])
        self.assertAlmostEqual(above[0], 20 * math.log10(2e-5), delta=0.01)  # -93.979

    def test_envelope_partial_last_hop_uses_its_own_length(self):
        # 24000 silent frames then 100 frames at 0.5: 51 hops (ceil(24100/480)); the last hop averages over its 100 frames
        ints = [0] * 24000 + [16384] * 100
        p = self.put("tail.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16)), chunk(b"data", pcm16(ints))))
        r = self.one("HushWav.envelope", FILE(p), 0.01)
        self.assertEqual(len(r["env"]), 51)
        self.assertEqual(r["env"][49], -100.0)
        self.assertAlmostEqual(r["env"][50], 20 * math.log10(0.5), delta=1e-6)  # -6.0206, not diluted by 480
        self.assertAlmostEqual(r["duration"], 24100 / 48000, places=12)

    def test_envelope_hop_length_rounds_to_whole_samples(self):
        # 44.1 kHz: hop 0.01 = 441 samples; 22050 frames -> 50 hops. A hop shorter than a sample is clamped to 1 sample.
        ints = sine16(0.5, 441, 44100, 22050)  # 441 Hz: 1 cycle = 100 samples, 441 samples is not whole cycles
        p = self.put("r44.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 44100, 16)), chunk(b"data", pcm16(ints))))
        r = self.one("HushWav.envelope", FILE(p), 0.01)
        self.assertEqual(len(r["env"]), 50)
        tiny = self.put("tiny.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 8000, 16)), chunk(b"data", pcm16([100] * 7))))
        r2 = self.one("HushWav.envelope", FILE(tiny), 0.00001)  # round(8000 * 1e-5) = 0 -> max(1, 0) = 1
        self.assertEqual(len(r2["env"]), 7)
        self.assertAlmostEqual(r2["env"][0], 20 * math.log10(100 / 32768), delta=1e-5)

    def test_envelope_24bit_float_and_stereo_follow_the_same_maths(self):
        amp = 0.25
        n = 4800
        sine = [amp * math.sin(2 * math.pi * 1000 * i / 48000) for i in range(n)]
        p24 = self.put("e24.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 24)),
                                       chunk(b"data", pcm24([int(round(x * 8388608)) for x in sine]))))
        pf = self.put("ef.wav", riff(chunk(b"fmt ", fmt_payload(3, 1, 48000, 32)), chunk(b"data", f32(sine))))
        st = []
        for x in sine:
            v = int(round(x * 32768))
            st += [v, v]  # identical channels: the mean is the same signal
        ps = self.put("es.wav", riff(chunk(b"fmt ", fmt_payload(1, 2, 48000, 16)), chunk(b"data", pcm16(st))))
        for path in (p24, pf, ps):
            r = self.one("HushWav.envelope", FILE(path), 0.01)
            self.assertEqual(len(r["env"]), 10)
            for v in r["env"]:
                self.assertAlmostEqual(v, db_rms_sine(amp), delta=0.01)

    def test_bytes_file_shorthand_is_argument_zero(self):
        p = self.put("sh.wav", riff(chunk(b"fmt ", fmt_payload(1, 1, 48000, 16)), chunk(b"data", pcm16([16384] * 480))))
        r = self.js([call("HushWav.envelope", None, 0.01, bytes_file=p)])[0]
        self.assertAlmostEqual(r["env"][0], 20 * math.log10(0.5), delta=1e-6)

    # ================================================================ detect.js: envelope of samples ==========
    def test_detect_envelope_from_samples(self):
        amp, n = 0.25, 9600  # 0.2 s of 1 kHz
        sine = [amp * math.sin(2 * math.pi * 1000 * i / 48000) for i in range(n)]
        env, env_hop, env_tiny, env_zero = self.js([
            call("HushDetect.envelope", sine, 48000, None, typed={0: "Float32Array"}),   # hop defaults to HOP (10 ms)
            call("HushDetect.envelope", sine, 48000, 0.02, typed={0: "Float32Array"}),
            call("HushDetect.envelope", [0.5] * 5, 8000, 0.00001, typed={0: "Float32Array"}),
            call("HushDetect.envelope", [0.0] * 960, 48000, 0.01, typed={0: "Float32Array"}),
        ])
        self.assertEqual(len(env), 20)
        for v in env:
            self.assertAlmostEqual(v, db_rms_sine(amp), delta=0.01)
        self.assertEqual(len(env_hop), 10)  # 20 ms hops
        self.close(env_tiny, [20 * math.log10(0.5)] * 5, tol=1e-6)  # one sample per hop (env is float32)
        self.assertEqual(env_zero, [-100.0, -100.0])
        self.assertEqual(self.one("HushDetect.HOP"), 0.01)

    # ================================================================ 2. percentile / stats ===================
    def test_percentile_index_is_floor_p_n_clamped(self):
        env = [-30, -90, -10, -50, -70, -20, -80, -40, -60, -100]  # unsorted, n = 10
        srt = sorted(env)

        def want(e, p):  # PRD FR-6: sorted ascending, index floor(p*n), clamped to n-1
            s = sorted(e)
            return s[min(len(s) - 1, math.floor(p * len(s)))]

        ps = [0, 0.1, 0.5, 0.9, 0.99, 1.0, 1.5]
        env7 = [3, 1, 2, 7, 5, 4, 6]  # n = 7: floor(0.9*7) = 6, floor(0.1*7) = 0
        got = self.js([call("HushDetect.percentile", env, p) for p in ps] +
                      [call("HushDetect.percentile", env7, 0.9), call("HushDetect.percentile", env7, 0.1),
                       call("HushDetect.percentile", [42], 0.9), call("HushDetect.percentile", [42], 0.0)])
        self.assertEqual(got[:len(ps)], [want(env, p) for p in ps])
        self.assertEqual(got[1], srt[1])  # 10th percentile of 10 values is the 2nd smallest: index floor(0.1*10) = 1
        self.assertEqual(got[3], srt[9])  # 90th: index 9 = the largest of 10
        self.assertEqual(got[5], srt[9])  # p = 1 -> index 10 clamped to 9
        self.assertEqual(got[len(ps):], [want(env7, 0.9), want(env7, 0.1), 42, 42])
        self.assertEqual(got[len(ps)], 7)  # index 6
        self.assertEqual(got[len(ps) + 1], 1)  # index 0

    def test_percentile_of_an_empty_envelope_is_minus_100(self):
        self.assertEqual(self.one("HushDetect.percentile", [], 0.1), -100)
        self.assertEqual(self.one("HushDetect.percentile", [], 0.9), -100)

    def test_stats_floor_is_10th_percentile_clamped_at_minus_70_and_speech_is_90th(self):
        # 100 hops: 10 at -85, 30 at -50, 50 at -25, 10 at -15: sorted index 10 (10th pct) is the first -50: floor -50;
        # index 90 is the first -15 of the last ten: speech -15.
        env = env_of((10, -85), (30, -50), (50, -25), (10, -15))
        # a quieter clip: 20 hops at -85 -> index 10 is -85, which the clamp lifts to -70
        env_low = env_of((20, -85), (60, -40), (20, -10))
        # exactly -70 and -69 stay as they are
        env_70 = env_of((20, -70), (80, -20))
        env_69 = env_of((20, -69.5), (80, -20))
        got = self.js([call("HushDetect.stats", e) for e in (env, env_low, env_70, env_69, [])])
        self.assertEqual(got[0], {"floor": -50, "speech": -15})
        self.assertEqual(got[1], {"floor": -70, "speech": -10})  # 90th: index 90 of 100 = -10 (last 20 are -10)
        self.assertEqual(got[2], {"floor": -70, "speech": -20})
        self.assertEqual(got[3], {"floor": -69.5, "speech": -20})
        self.assertEqual(got[4], {"floor": -70, "speech": -100})  # empty: max(-70, -100), speech -100

    # ================================================================ 3. fromIntensity ========================
    @staticmethod
    def from_intensity_prd(intensity, floor, speech):
        """PRD FR-10 written in Python (same operation order, JS Math.round)."""
        t = max(0, min(100, intensity)) / 100
        span = max(6, speech - floor)
        pad = 0.18 - 0.12 * t
        return {
            "threshold": js_round((floor + span * (0.15 + 0.30 * t)) * 10) / 10,
            "minSilence": js_round((0.9 - 0.65 * t) * 100) / 100,
            "padBefore": js_round(pad * 100) / 100,
            "padAfter": js_round(pad * 100) / 100,
        }

    def test_from_intensity_presets_and_clamp_wide_clip(self):
        st = {"floor": -60, "speech": -20}  # span 40
        levels = [0, 25, 50, 80, 100, -10, 150]
        got = self.js([call("HushDetect.fromIntensity", i, st) for i in levels])
        for i, g in zip(levels, got):
            self.close(g, self.from_intensity_prd(i, -60, -20), path="intensity %s" % i)
        # hand-derived anchors (t = i/100, span = 40):
        #   0:   threshold -60 + 40*0.15 = -54.0   minSilence 0.90         pad 0.18
        #   80:  threshold -60 + 40*(0.15+0.24) = -44.4   minSilence 0.9-0.52 = 0.38   pad 0.18-0.096 = 0.084 -> 0.08
        #   100: threshold -60 + 40*0.45 = -42.0   minSilence 0.25         pad 0.06
        self.close(got[0], {"threshold": -54.0, "minSilence": 0.9, "padBefore": 0.18, "padAfter": 0.18})
        self.close(got[3], {"threshold": -44.4, "minSilence": 0.38, "padBefore": 0.08, "padAfter": 0.08})
        self.close(got[4], {"threshold": -42.0, "minSilence": 0.25, "padBefore": 0.06, "padAfter": 0.06})
        self.close(got[5], got[0])  # -10 clamps to 0
        self.close(got[6], got[4])  # 150 clamps to 100

    def test_from_intensity_span_clamps_to_6_dB_on_a_flat_clip(self):
        st = {"floor": -40, "speech": -37}  # speech - floor = 3 < 6 -> span 6
        levels = [0, 25, 50, 80, 100]
        got = self.js([call("HushDetect.fromIntensity", i, st) for i in levels])
        for i, g in zip(levels, got):
            self.close(g, self.from_intensity_prd(i, -40, -37), path="flat intensity %s" % i)
        self.close(got[0], {"threshold": -39.1, "minSilence": 0.9, "padBefore": 0.18, "padAfter": 0.18})  # -40 + 6*0.15
        self.close(got[4], {"threshold": -37.3, "minSilence": 0.25, "padBefore": 0.06, "padAfter": 0.06})  # -40 + 6*0.45
        # the same stats with a real 6 dB span give the same numbers: the clamp is "max(6, ...)"
        same = self.one("HushDetect.fromIntensity", 50, {"floor": -40, "speech": -34})
        self.close(same, self.one("HushDetect.fromIntensity", 50, st))

    def test_from_intensity_output_is_rounded(self):
        # threshold to 0.1 dB, minSilence and pads to 0.01 s (a floor that is not a round number shows the rounding)
        st = {"floor": -57.37, "speech": -23.91}
        for i in (0, 13, 25, 37, 50, 71, 80, 100):
            g = self.one("HushDetect.fromIntensity", i, st)
            self.close(g, self.from_intensity_prd(i, -57.37, -23.91), path="i=%d" % i)
            self.assertAlmostEqual(g["threshold"] * 10, round(g["threshold"] * 10), places=6)
            self.assertAlmostEqual(g["minSilence"] * 100, round(g["minSilence"] * 100), places=6)
            self.assertAlmostEqual(g["padBefore"] * 100, round(g["padBefore"] * 100), places=6)
            self.assertEqual(g["padBefore"], g["padAfter"])

    def test_simple_presets_soft_medium_strong(self):
        self.assertEqual(self.one("HushDetect.SIMPLE"), {"soft": 25, "medium": 50, "strong": 80})  # FR-10

    # ================================================================ 4. silences =============================
    def silences(self, env, threshold=-40, min_silence=0.5, hop=None):
        return self.one("HushDetect.silences", env, threshold, min_silence, hop)

    def test_silences_basic_run_at_or_over_min_silence(self):
        self.close(self.silences(env_of((100, LOUD), (200, QUIET), (100, LOUD))), [[1.0, 3.0]])
        self.close(self.silences(env_of((100, LOUD), (51, QUIET), (100, LOUD))), [[1.0, 1.51]])
        self.assertEqual(self.silences(env_of((100, LOUD), (49, QUIET), (100, LOUD))), [])  # 0.49 s < 0.5 s: dropped

    def test_silences_threshold_is_strict(self):
        # a hop exactly at the threshold counts as speech: only below is quiet
        self.assertEqual(self.silences(env_of((10, LOUD), (100, -40.0), (10, LOUD))), [])
        self.close(self.silences(env_of((10, LOUD), (100, -40.1), (10, LOUD))), [[0.1, 1.1]])

    def test_silences_30ms_blip_inside_a_silence_is_ignored(self):
        # quiet 100 hops, loud x3 (30 ms), quiet 100 hops: one silence 1.00 .. 3.03 (the blip is inside it)
        env = env_of((100, LOUD), (100, QUIET), (3, LOUD), (100, QUIET), (100, LOUD))
        self.close(self.silences(env), [[1.0, 3.03]])
        self.close(self.silences(env_of((100, LOUD), (100, QUIET), (1, LOUD), (100, QUIET), (100, LOUD))), [[1.0, 3.01]])

    def test_silences_40ms_blip_splits_the_silence(self):
        env = env_of((100, LOUD), (100, QUIET), (4, LOUD), (100, QUIET), (100, LOUD))
        # first silence ends where the blip starts (index 200 -> 2.00); the second starts after it (204 -> 2.04, ends 304)
        self.close(self.silences(env), [[1.0, 2.0], [2.04, 3.04]])

    def test_silences_blip_that_splits_leaves_a_too_short_half_dropped(self):
        env = env_of((100, LOUD), (30, QUIET), (4, LOUD), (100, QUIET), (100, LOUD))  # 0.30 s then 1.00 s
        self.close(self.silences(env), [[1.34, 2.34]])

    def test_silences_closed_at_the_end_of_the_envelope(self):
        self.close(self.silences(env_of((100, LOUD), (100, QUIET))), [[1.0, 2.0]])
        self.close(self.silences(env_of((100, QUIET), (100, LOUD))), [[0.0, 1.0]])
        self.close(self.silences(env_of((100, QUIET))), [[0.0, 1.0]])
        # a short loud tail (2 hops, within the blip tolerance) is not part of the silence: it ends where the tail starts
        self.close(self.silences(env_of((100, QUIET), (2, LOUD))), [[0.0, 1.0]])

    def test_silences_empty_envelope(self):
        self.assertEqual(self.silences([]), [])

    def test_silences_hop_parameter_scales_times_and_the_blip_limit(self):
        # QUIRK: the blip allowance is round(0.03 / hop) hops, so it is 3 at the 10 ms hop of the panel but 2 at 20 ms
        # (0.03/0.02 = 1.5 -> 2 hops = 40 ms ignored) - the panel always uses hop = 0.01, so this never shows.
        env2 = env_of((50, QUIET), (2, LOUD), (50, QUIET))
        self.close(self.silences(env2, hop=0.02), [[0.0, 2.04]])
        env3 = env_of((50, QUIET), (3, LOUD), (50, QUIET))
        self.close(self.silences(env3, hop=0.02), [[0.0, 1.0], [1.06, 2.06]])

    # ================================================================ 5. cutsFromSilences =====================
    def cuts(self, sil, length=10.0, **opts):
        o = {"padBefore": 0.1, "padAfter": 0.2}
        o.update(opts)
        return self.one("HushDetect.cutsFromSilences", sil, o, length)

    def test_cuts_pads_apply_next_to_speech(self):
        # silence [2, 5]: padAfter (0.2) after the speech before it, padBefore (0.1) before the speech after it
        self.close(self.cuts([[2.0, 5.0]]), [{"s": 2.2, "e": 4.9, "kind": "silence"}])

    def test_cuts_no_pad_where_the_silence_touches_the_range_start_or_end(self):
        self.close(self.cuts([[0.0, 2.0]]), [{"s": 0, "e": 1.9, "kind": "silence"}])  # touches 0: no padAfter
        self.close(self.cuts([[8.0, 10.0]]), [{"s": 8.2, "e": 10.0, "kind": "silence"}])  # touches length: no padBefore
        self.close(self.cuts([[0.0, 10.0]]), [{"s": 0, "e": 10.0, "kind": "silence"}])
        # within 1 ms counts as touching, 2 ms does not
        self.close(self.cuts([[0.0005, 2.0], [8.0, 9.9995]]),
                   [{"s": 0, "e": 1.9, "kind": "silence"}, {"s": 8.2, "e": 10.0, "kind": "silence"}])
        self.close(self.cuts([[0.002, 2.0]]), [{"s": 0.202, "e": 1.9, "kind": "silence"}])

    def test_cuts_shorter_than_80ms_are_dropped(self):
        # silence of 0.37 s with pads 0.1 + 0.2 leaves 0.07 s (dropped); 0.39 s leaves 0.09 s (kept)
        self.assertEqual(self.cuts([[3.0, 3.37]]), [])
        self.close(self.cuts([[3.0, 3.39]]), [{"s": 3.2, "e": 3.29, "kind": "silence"}])
        # a pad total larger than the silence leaves a negative range: dropped
        self.assertEqual(self.cuts([[3.0, 3.2]]), [])

    def test_cuts_min_cut_override(self):
        sil = [[3.0, 3.5], [6.0, 7.0]]  # leaves 0.2 s and 0.7 s with pads 0.1/0.2
        self.close(self.cuts(sil, minCut=0.5), [{"s": 6.2, "e": 6.9, "kind": "silence"}])
        self.close(self.cuts([[3.0, 3.32]], minCut=0.01), [{"s": 3.2, "e": 3.22, "kind": "silence"}])
        # QUIRK: minCut 0 is falsy, so it falls back to the 80 ms default
        self.assertEqual(self.cuts([[3.0, 3.32]], minCut=0), [])

    def test_cuts_none_and_many(self):
        self.assertEqual(self.cuts([]), [])
        got = self.cuts([[1.0, 2.0], [4.0, 6.0]])
        self.close(got, [{"s": 1.2, "e": 1.9, "kind": "silence"}, {"s": 4.2, "e": 5.9, "kind": "silence"}])

    # ================================================================ 6. combine ==============================
    def combine(self, ranges, join_gap=0.25):
        return self.one("HushDetect.combine", ranges, join_gap)

    @staticmethod
    def sil(s, e):
        return {"s": s, "e": e, "kind": "silence"}

    @staticmethod
    def fil(s, e, label="um"):
        return {"s": s, "e": e, "kind": "filler", "label": label}

    def test_combine_overlapping_ranges_are_united(self):
        self.close(self.combine([self.sil(1, 3), self.sil(2, 5)]), [self.sil(1, 5)])
        self.close(self.combine([self.sil(1, 5), self.sil(2, 3)]), [self.sil(1, 5)])  # contained: end stays 5
        self.close(self.combine([self.sil(6, 7), self.sil(1, 2), self.sil(1.5, 3)]),  # sorted by start first
                   [self.sil(1, 3), self.sil(6, 7)])

    def test_combine_touching_ranges_merge_within_half_a_millisecond(self):
        self.close(self.combine([self.sil(1, 2), self.sil(2.0004, 3)], 0.0), [self.sil(1, 3)])
        self.close(self.combine([self.sil(1, 2), self.sil(2.001, 3)], 0.0), [self.sil(1, 2), self.sil(2.001, 3)])

    def test_combine_silence_silence_gap_within_join_gap_is_not_joined(self):
        self.close(self.combine([self.sil(1, 2), self.sil(2.2, 3)], 0.25), [self.sil(1, 2), self.sil(2.2, 3)])

    def test_combine_filler_swallows_a_gap_up_to_join_gap(self):
        # filler after a silence: gap 0.2 <= 0.25 -> one range, kind filler, label from the filler
        self.close(self.combine([self.sil(1, 2), self.fil(2.2, 2.4)]), [self.fil(1, 2.4)])
        # filler before a silence: kind stays filler (the first range), label kept
        self.close(self.combine([self.fil(1, 1.2), self.sil(1.4, 2)]), [self.fil(1, 2)])
        # gap larger than joinGap (0.3 > 0.25): left apart
        self.close(self.combine([self.sil(1, 2), self.fil(2.3, 2.5)]), [self.sil(1, 2), self.fil(2.3, 2.5)])
        # a join gap of 0 swallows nothing
        self.close(self.combine([self.sil(1, 2), self.fil(2.2, 2.4)], 0.0), [self.sil(1, 2), self.fil(2.2, 2.4)])

    def test_combine_filler_inside_a_silence_turns_the_whole_range_into_a_filler(self):
        # QUIRK (kept as upstream): kind/label of a silence that swallows a filler become filler/"um" for the union
        self.close(self.combine([self.sil(1, 5), self.fil(2, 3)]), [self.fil(1, 5)])

    def test_combine_labels_are_merged_with_a_space_and_kind_becomes_filler(self):
        self.close(self.combine([self.fil(1, 1.2, "um"), self.fil(1.25, 1.4, "uh")], 0.1), [self.fil(1, 1.4, "um uh")])
        self.close(self.combine([self.fil(1, 1.2, "um"), self.fil(1.25, 1.4, "uh"), self.fil(1.45, 1.6, "er")], 0.1),
                   [self.fil(1, 1.6, "um uh er")])
        self.close(self.combine([self.fil(1, 1.2, "um"), self.fil(1.25, 1.4, "uh")], 0.01),  # gap 0.05 > 0.01: apart
                   [self.fil(1, 1.2, "um"), self.fil(1.25, 1.4, "uh")])
        # QUIRK: merging a filler that has no label after one that has gives a trailing space ("um ")
        nolabel = {"s": 1.25, "e": 1.4, "kind": "filler"}
        self.close(self.combine([self.fil(1, 1.2, "um"), nolabel], 0.1), [self.fil(1, 1.4, "um ")])

    def test_combine_empty_and_single(self):
        self.assertEqual(self.combine([]), [])
        self.close(self.combine([self.fil(1, 2, "um")]), [self.fil(1, 2, "um")])

    # ================================================================ 7. snap =================================
    def snap(self, ranges, fps, min_frames=None):
        return self.one("HushDetect.snap", ranges, fps, min_frames)

    def test_snap_is_inward_at_common_frame_rates_and_never_outward(self):
        ranges = [self.sil(1.003, 2.497), self.fil(3.5, 4.51, "um"), self.sil(10.0123, 12.9876)]
        for fps in (24, 25, 29.97, 30, 60):
            got = self.snap(ranges, fps)
            want = []
            for r in ranges:  # PRD FR-16: start rounds up, end rounds down, 1e-6 frame tolerance
                s = math.ceil(r["s"] * fps - 1e-6) / fps
                e = math.floor(r["e"] * fps + 1e-6) / fps
                want.append(dict(r, s=s, e=e))
            self.close(got, want, path="fps %s" % fps)
            for g, r in zip(got, ranges):  # never outward
                self.assertGreaterEqual(g["s"], r["s"] - 1e-9)
                self.assertLessEqual(g["e"], r["e"] + 1e-9)
                self.assertAlmostEqual(g["s"] * fps, round(g["s"] * fps), places=6)  # on a whole frame
                self.assertAlmostEqual(g["e"] * fps, round(g["e"] * fps), places=6)
                self.assertEqual(g["kind"], r["kind"])
                self.assertEqual(g.get("label"), r.get("label"))

    def test_snap_hand_derived_values(self):
        # 25 fps: 1.003*25 = 25.075 -> start frame 26 = 1.04; 2.497*25 = 62.425 -> end frame 62 = 2.48
        self.close(self.snap([self.sil(1.003, 2.497)], 25), [self.sil(1.04, 2.48)])
        # 24 fps: 1.0 and 2.5 are whole frames (24, 60): unchanged
        self.close(self.snap([self.sil(1.0, 2.5)], 24), [self.sil(1.0, 2.5)])
        # 29.97 fps: 1.0 -> ceil(29.97 - 1e-6) = 30 -> 30/29.97; 3.0 -> floor(89.91 + 1e-6) = 89 -> 89/29.97
        self.close(self.snap([self.sil(1.0, 3.0)], 29.97), [self.sil(30 / 29.97, 89 / 29.97)])
        # 60 fps: 0.5 = frame 30; 1.0083 * 60 = 60.498 -> end frame 60 = 1.0
        self.close(self.snap([self.sil(0.5, 1.0083)], 60), [self.sil(0.5, 1.0)])

    def test_snap_tolerance_is_one_millionth_of_a_frame(self):
        fps = 25
        # within 1e-6 frame of a boundary: snaps to that boundary (start very slightly early, end very slightly late)
        self.close(self.snap([self.sil((25 + 5e-7) / fps, (50 - 5e-7) / fps)], fps), [self.sil(1.0, 2.0)])
        # a few millionths beyond: goes inward to the next whole frame
        self.close(self.snap([self.sil((25 + 3e-6) / fps, (50 - 3e-6) / fps)], fps), [self.sil(26 / fps, 49 / fps)])

    def test_snap_drops_pieces_under_two_frames_and_keeps_exactly_two(self):
        fps = 25
        self.close(self.snap([self.sil(1.0, 1.08)], fps), [self.sil(1.0, 1.08)])  # 27 - 25 = 2 frames: kept
        self.assertEqual(self.snap([self.sil(1.0, 1.04)], fps), [])  # 1 frame
        self.assertEqual(self.snap([self.sil(1.0, 1.07)], fps), [])  # 1.07*25 = 26.75 -> frame 26: 1 frame
        self.assertEqual(self.snap([self.sil(1.01, 1.03)], fps), [])  # no whole frame inside at all (start > end)
        self.assertEqual(self.snap([self.sil(1.0, 1.0)], fps), [])
        # the 2-frame minimum is the default (null) and can be raised
        self.close(self.snap([self.sil(1.0, 1.08)], fps, 3), [])
        self.close(self.snap([self.sil(1.0, 1.12)], fps, 3), [self.sil(1.0, 1.12)])
        self.close(self.snap([self.sil(1.0, 1.04)], fps, 1), [self.sil(1.0, 1.04)])

    def test_snap_drops_keep_the_order_of_the_rest(self):
        got = self.snap([self.sil(1.0, 1.04), self.fil(2.0, 2.4, "um"), self.sil(3.0, 3.02)], 25)
        self.close(got, [self.fil(2.0, 2.4, "um")])

    # ================================================================ D.total / D.fmt =========================
    def test_total(self):
        self.assertEqual(self.one("HushDetect.total", []), 0)
        self.assertEqual(self.one("HushDetect.total", [{"s": 1, "e": 2.5}, {"s": 4, "e": 4.25}]), 1.75)  # 1.5 + 0.25

    def test_fmt_minutes_and_tenths(self):
        cases = [(0, "0:00.0"), (5.04, "0:05.0"), (12.34, "0:12.3"), (59.0, "0:59.0"), (65.5, "1:05.5"),
                 (600, "10:00.0"), (3725.04, "62:05.0"), (-3, "0:00.0")]  # negative clamps to 0
        got = self.js([call("HushDetect.fmt", s) for s, _ in cases])
        self.assertEqual(got, [w for _, w in cases])

    def test_fmt_rounding_edges_are_quirks(self):
        # QUIRK: the seconds are padded before they are rounded, so 9.96 prints "0:010.0" and 59.96 prints "0:60.0"
        self.assertEqual(self.one("HushDetect.fmt", 9.96), "0:010.0")
        self.assertEqual(self.one("HushDetect.fmt", 59.96), "0:60.0")

    # ================================================================ 8. plan =================================
    SETTINGS = {"threshold": -40, "minSilence": 0.5, "padBefore": 0.1, "padAfter": 0.1}

    def synthetic_env(self):
        """10.00 s at 10 ms hops. Speech -20 dB, silence -60 dB:
             0.00-1.00 speech | 1.00-2.50 silence | 2.50-4.00 speech | 4.00-4.30 silence (too short)
             4.30-6.00 speech | 6.00-7.00 silence | 7.00-8.00 speech | 8.00-10.00 silence (runs to the end)."""
        return env_of((100, LOUD), (150, QUIET), (150, LOUD), (30, QUIET), (170, LOUD), (100, QUIET), (100, LOUD),
                      (200, QUIET))

    def test_plan_end_to_end_on_a_synthetic_envelope(self):
        env = self.synthetic_env()
        self.assertEqual(len(env), 1000)
        fillers = [
            {"s": 3.0, "e": 3.3, "kind": "filler", "label": "um", "on": True, "source": "word"},   # alone in speech
            {"s": 7.1, "e": 7.3, "kind": "filler", "label": "uh", "on": True, "source": "word"},   # 0.2 s after a silence cut
        ]
        r = self.one("HushDetect.plan", env, self.SETTINGS, fillers, 10.0, 25)
        # silences (>= 0.5 s): 1.0-2.5, 6.0-7.0, 8.0-10.0 (the 0.3 s one at 4.0 is dropped)
        self.close(r["silences"], [[1.0, 2.5], [6.0, 7.0], [8.0, 10.0]])
        # silence cuts with pads 0.1/0.1: 1.1-2.4, 6.1-6.9, 8.1-10.0 (touches the end: no end pad)
        # joinGap = 0.1 + 0.1 + 0.05 = 0.25: filler 7.1-7.3 is 0.2 after 6.1-6.9, so they join into 6.1-7.3 (filler)
        # snap at 25 fps (inward): 1.1 -> frame 28 = 1.12, 2.4 = frame 60 = 2.4; 3.0 = 3.0, 3.3 -> frame 82 = 3.28;
        #   6.1 -> frame 153 = 6.12, 7.3 -> frame 182 = 7.28; 8.1 -> frame 203 = 8.12, 10.0 = 10.0
        self.close(r["cuts"], [
            {"s": 1.12, "e": 2.4, "kind": "silence"},
            {"s": 3.0, "e": 3.28, "kind": "filler", "label": "um"},
            {"s": 6.12, "e": 7.28, "kind": "filler", "label": "uh"},
            {"s": 8.12, "e": 10.0, "kind": "silence"},
        ], tol=1e-9)
        removed = (2.4 - 1.12) + (3.28 - 3.0) + (7.28 - 6.12) + (10.0 - 8.12)  # 1.28 + 0.28 + 1.16 + 1.88 = 4.6
        self.assertAlmostEqual(removed, 4.6, places=9)
        self.assertAlmostEqual(r["removed"], removed, places=9)
        self.assertEqual(r["before"], 10.0)
        self.assertAlmostEqual(r["after"], 10.0 - removed, places=9)  # 5.4
        self.assertAlmostEqual(r["after"], 5.4, places=9)

    def test_plan_filler_join_gap_is_pads_plus_50ms(self):
        # FR-16: a filler swallows a neighbouring gap up to padBefore + padAfter + 0.05 = 0.25 s here.
        # silence 1.0-2.0 -> cut 1.1-1.9 (pads 0.1/0.1); filler 0.245 s after the cut joins it, one 0.255 s after does not
        env = env_of((100, LOUD), (100, QUIET), (300, LOUD))
        joined = [{"s": 2.145, "e": 2.4, "kind": "filler", "label": "um", "on": True, "source": "word"}]
        apart = [{"s": 2.155, "e": 2.4, "kind": "filler", "label": "um", "on": True, "source": "word"}]
        # 100 fps: one frame is 10 ms, so the inward snap moves 2.155 only to 2.16
        j = self.one("HushDetect.plan", env, self.SETTINGS, joined, 4.0, 100)
        a = self.one("HushDetect.plan", env, self.SETTINGS, apart, 4.0, 100)
        self.assertEqual([(c["kind"], c.get("label")) for c in j["cuts"]], [("filler", "um")])
        self.assertAlmostEqual(j["cuts"][0]["s"], 1.1, places=9)
        self.assertAlmostEqual(j["cuts"][0]["e"], 2.4, places=9)
        self.assertEqual([c["kind"] for c in a["cuts"]], ["silence", "filler"])
        self.assertAlmostEqual(a["cuts"][0]["e"], 1.9, places=9)
        self.assertAlmostEqual(a["cuts"][1]["s"], 2.16, places=9)  # 2.155 rounds inward to frame 216

    def test_plan_without_fillers(self):
        env = self.synthetic_env()
        none, empty = self.js([call("HushDetect.plan", env, self.SETTINGS, None, 10.0, 25),
                               call("HushDetect.plan", env, self.SETTINGS, [], 10.0, 25)])
        self.assertEqual(none, empty)
        self.close(none["cuts"], [{"s": 1.12, "e": 2.4, "kind": "silence"},
                                  {"s": 6.12, "e": 6.88, "kind": "silence"},   # 6.9 -> frame 172 = 6.88
                                  {"s": 8.12, "e": 10.0, "kind": "silence"}])
        removed = (2.4 - 1.12) + (6.88 - 6.12) + (10.0 - 8.12)  # 1.28 + 0.76 + 1.88 = 3.92
        self.assertAlmostEqual(none["removed"], 3.92, places=9)
        self.assertAlmostEqual(none["removed"], removed, places=9)
        self.assertAlmostEqual(none["after"], 6.08, places=9)

    def test_plan_drops_a_cut_that_snaps_below_two_frames(self):
        # silence 1.0-1.2 (min 0.15), pads 0.02 after / 0.09 before: cut 1.02-1.11 = 0.09 s (kept by the 80 ms rule),
        # but at 25 fps it snaps to frame 26 (1.04) .. frame 27 (1.08): 1 frame, dropped
        env = env_of((100, LOUD), (20, QUIET), (180, LOUD))
        st = {"threshold": -40, "minSilence": 0.15, "padBefore": 0.09, "padAfter": 0.02}
        r = self.one("HushDetect.plan", env, st, [], 3.0, 25)
        self.close(r["silences"], [[1.0, 1.2]])
        self.assertEqual(r["cuts"], [])
        self.assertEqual((r["removed"], r["before"], r["after"]), (0, 3.0, 3.0))

    def test_plan_does_not_look_at_the_on_flag_of_fillers(self):
        # the panel filters ticked fillers before calling plan; plan itself uses every filler it is given
        env = env_of((300, LOUD))
        f = [{"s": 1.0, "e": 1.4, "kind": "filler", "label": "like", "on": False, "source": "word"}]
        r = self.one("HushDetect.plan", env, self.SETTINGS, f, 3.0, 25)
        self.close(r["cuts"], [{"s": 1.0, "e": 1.4, "kind": "filler", "label": "like"}])
        self.assertAlmostEqual(r["removed"], 0.4, places=9)

    def test_plan_with_simple_mode_settings_derived_from_the_clip(self):
        # stats of the envelope, then FR-10 settings, then the plan: floor -60 (silence share >= 10 %), speech -20
        env = self.synthetic_env()
        st, = self.js([call("HushDetect.stats", env)])
        self.assertEqual(st, {"floor": -60, "speech": -20})
        sett = self.one("HushDetect.fromIntensity", 50, st)
        self.close(sett, self.from_intensity_prd(50, -60, -20))
        # FR-10 at t = 0.5, span 40: threshold -60 + 40 * (0.15 + 0.15) = -48.0, pad 0.18 - 0.06 = 0.12.
        # minSilence is 0.9 - 0.325 = 0.575 on paper (half-up would give 0.58) but in binary doubles 0.9 - 0.65 * 0.5 is
        # 0.57499999999999996, so Math.round(57.49999999999999) = 57 and the setting is 0.57 (QUIRK, pinned as upstream).
        self.close(sett, {"threshold": -48.0, "minSilence": 0.57, "padBefore": 0.12, "padAfter": 0.12})
        r = self.one("HushDetect.plan", env, sett, [], 10.0, 25)
        # silences >= 0.57 s: 1.0-2.5, 6.0-7.0, 8.0-10.0 (the 0.3 s one at 4.0 is dropped). Cuts with pads 0.12:
        #   1.12-2.38 -> 25 fps inward: 1.12 = frame 28, 2.38*25 = 59.5 -> frame 59 = 2.36
        #   6.12-6.88 -> frame 153 = 6.12, frame 172 = 6.88
        #   8.12-10.0 -> frame 203 = 8.12, 10.0 = frame 250
        self.close(r["silences"], [[1.0, 2.5], [6.0, 7.0], [8.0, 10.0]])
        self.close(r["cuts"], [{"s": 1.12, "e": 2.36, "kind": "silence"}, {"s": 6.12, "e": 6.88, "kind": "silence"},
                               {"s": 8.12, "e": 10.0, "kind": "silence"}])
        removed = (2.36 - 1.12) + (6.88 - 6.12) + (10.0 - 8.12)  # 1.24 + 0.76 + 1.88 = 3.88
        self.assertAlmostEqual(r["removed"], 3.88, places=9)
        self.assertAlmostEqual(r["removed"], removed, places=9)
        self.assertAlmostEqual(r["after"], 6.12, places=9)

    # ================================================================ 9. fillers.norm =========================
    def test_norm_table(self):
        cases = [
            ("UM", "um"), ("Um,", "um"), ("Hmm...", "hmm"), ("  you   know \t\n", "you know"),
            ("um\u2026", "um"),                                    # ellipsis character
            ("\"quoted\"", "quoted"), ("it's", "its"), ("(uh)", "uh"), ("[er]", "er"), ("a;b:c!d?", "abcd"),
            ("\u201cwow\u201d", "wow"), ("don\u2019t", "dont"), ("`x`", "x"), ("u-m", "um"),
            ("\u064a\u0639\u0646\u064a\u060c", "\u064a\u0639\u0646\u064a"),   # Arabic comma
            ("\u0637\u064a\u0628\u061b", "\u0637\u064a\u0628"),               # Arabic semicolon
            ("\u0625\u064a\u0647\u061f", "\u0627\u064a\u0647"),               # Arabic question mark + hamza alef
            ("\u0645\u064e\u0631\u0652\u062d\u064e\u0628\u064b\u0627", "\u0645\u0631\u062d\u0628\u0627"),  # harakat
            ("\u0647\u0670\u0630\u0627", "\u0647\u0630\u0627"),               # dagger alef U+0670
            ("\u064a\u0639\u0640\u0640\u0640\u0646\u064a", "\u064a\u0639\u0646\u064a"),  # tatweel U+0640
            ("\u0627\u0623\u0625\u0622\u0671", "\u0627\u0627\u0627\u0627\u0627"),   # all alef forms -> bare alef
            ("\u0639\u0644\u0649", "\u0639\u0644\u064a"),                     # alef maqsura -> yeh
            ("\u0623\u0635\u0644\u064b\u0627", "\u0627\u0635\u0644\u0627"),   # \u0623\u0635\u0644\u064b\u0627 -> \u0627\u0635\u0644\u0627
            ("\u0622\u0647", "\u0627\u0647"),                                 # \u0622\u0647 -> \u0627\u0647
            ("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u065f", ""),    # U+064B..U+065F range, ends included
            ("", ""), ("...", ""), ("   ", ""),
        ]
        got = self.js([call("HushFillers.norm", w) for w, _ in cases])
        for (w, want), g in zip(cases, got):
            self.assertEqual(g, want, repr(w))

    def test_norm_keeps_what_the_prd_does_not_unify(self):
        # PRD FR-13 unifies alef and yeh forms only: ta marbuta, digits and an en dash are left alone
        got = self.js([call("HushFillers.norm", w) for w in ("\u0645\u0631\u062d\u0628\u0629", "x2y", "a\u2013b")])
        self.assertEqual(got, ["\u0645\u0631\u062d\u0628\u0629", "x2y", "a\u2013b"])

    # ================================================================ 10. fillers.find ========================
    @staticmethod
    def words(*specs):
        out, t = [], 0.0
        for w in specs:
            out.append({"w": w, "s": round(t, 3), "e": round(t + 0.2, 3), "p": 0.9})
            t += 0.3
        return out

    def find(self, words, strong="", soft=""):
        return self.one("HushFillers.find", words, strong, soft)

    def hit(self, w, label, strong, source="word"):
        return {"s": w["s"], "e": w["e"], "label": label, "kind": "filler", "on": strong, "source": source}

    def test_find_strong_and_soft_words(self):
        w = self.words("So", "um,", "like", "the", "uh", "thing")
        got = self.find(w, "um, uh", "like")
        self.assertEqual(got, [self.hit(w[1], "um,", True), self.hit(w[2], "like", False), self.hit(w[4], "uh", True)])

    def test_find_two_word_phrases_span_both_words(self):
        w = self.words("well", "You", "Know.", "it", "is", "I", "mean", "fine")
        got = self.find(w, "", "you know, i mean")
        self.assertEqual(got, [
            {"s": w[1]["s"], "e": w[2]["e"], "label": "You Know.", "kind": "filler", "on": False, "source": "word"},
            {"s": w[5]["s"], "e": w[6]["e"], "label": "I mean", "kind": "filler", "on": False, "source": "word"}])
        # a strong two-word phrase is ticked
        got2 = self.find(w, "you know", "")
        self.assertEqual([(g["label"], g["on"]) for g in got2], [("You Know.", True)])

    def test_find_two_word_phrase_wins_over_a_single_word_even_a_strong_one(self):
        w = self.words("you", "know", "right")
        # "you" is a strong single word, "you know" a soft phrase: the phrase is checked first, so it is the one used
        got = self.find(w, "you", "you know")
        self.assertEqual(got, [{"s": w[0]["s"], "e": w[1]["e"], "label": "you know", "kind": "filler", "on": False,
                                "source": "word"}])
        # strong phrase beats soft phrase
        got = self.find(w, "you know", "you know")
        self.assertEqual([g["on"] for g in got], [True])
        # the second word of a phrase is consumed: "know" alone is not listed again
        got = self.find(w, "know", "you know")
        self.assertEqual([g["label"] for g in got], ["you know"])

    def test_find_phrase_at_the_end_of_the_words_falls_back_to_single_words(self):
        w = self.words("so", "you")
        self.assertEqual(self.find(w, "", "you know"), [])  # no next word: no phrase, "you" alone is not a filler
        self.assertEqual([g["label"] for g in self.find(w, "you", "")], ["you"])

    def test_find_elongated_hesitations_are_strong_even_when_not_in_the_list(self):
        hes = ["ummmm", "hmmmm", "aaah", "\u0627\u0645\u0645\u0645\u0645\u0645", "\u0622\u0622\u0622\u0647", "er", "uh",
               "UMM.", "mhm", "mm", "hm", "ahh", "\u0627\u0647\u0647\u0647\u0645\u0645", "\u0627\u0648\u0648\u0647",
               "erm", "uuuhhh"]
        non = ["hello", "ham", "the", "m", "h", "e", "a", "ahm", "\u0627\u0647", "\u0645", "\u0627\u0644\u0644\u0647"]
        for h in hes:
            got = self.find(self.words(h), "", "")
            self.assertEqual(len(got), 1, repr(h))
            self.assertTrue(got[0]["on"], repr(h))
            self.assertEqual(got[0]["label"], h)
        for n in non:
            self.assertEqual(self.find(self.words(n), "", ""), [], repr(n))

    def test_find_hesitation_patterns_are_anchored_to_whole_words(self):
        # u+h*m+ must start with u: "uhm"/"umm" match, "hum" does not (and "ah"/"mm" are fillers by design)
        got = self.find(self.words("hum", "uhm", "ahem", "mmm"), "", "")
        self.assertEqual([g["label"] for g in got], ["uhm", "mmm"])

    def test_find_custom_lists_split_on_comma_arabic_comma_and_newline(self):
        w = self.words("foo", "bar", "baz", "qux", "quux", "x")
        got = self.find(w, "foo\u060cBar\nbaz", "qux, quux")  # \u060c (U+060C), newline, comma, mixed case
        self.assertEqual([(g["label"], g["on"]) for g in got],
                         [("foo", True), ("bar", True), ("baz", True), ("qux", False), ("quux", False)])
        # ';' is not a separator: "foo;bar" is one entry (norm drops the ';' -> "foobar")
        self.assertEqual(self.find(self.words("foo", "bar", "foobar"), "foo;bar", ""),
                         [self.hit(self.words("foo", "bar", "foobar")[2], "foobar", True)])
        # list entries are normalised the way words are (punctuation, case, spaces)
        self.assertEqual([g["label"] for g in self.find(self.words("Well", "um"), " Well. ,  UM!!", "")], ["Well", "um"])
        # empty and whitespace-only entries are ignored, null lists are fine
        self.assertEqual(self.find(self.words("x"), ",,\n,  ,", None), [])

    def test_find_arabic_words_are_normalised_before_matching(self):
        # list written with plain alef / yeh; Whisper writes hamza alef, harakat and alef maqsura
        w = self.words("\u0623\u0635\u0644\u064b\u0627", "\u0639\u0644\u0649", "\u0622\u0647")
        got = self.find(w, "\u0627\u0647", "\u0627\u0635\u0644\u0627, \u0639\u0644\u064a")
        self.assertEqual([(g["label"], g["on"]) for g in got],
                         [("\u0623\u0635\u0644\u064b\u0627", False), ("\u0639\u0644\u0649", False), ("\u0622\u0647", True)])

    def test_find_skips_words_that_normalise_to_nothing(self):
        w = self.words("...", "um", "\u2026", "you", "...", "know")
        got = self.find(w, "um", "you know")
        # "..." is skipped; "you" followed by "..." does not form the phrase "you know" (the phrase uses the next
        # word as written); "um" matches; "know" alone is not listed
        self.assertEqual([g["label"] for g in got], ["um"])

    def test_find_result_shape_and_source(self):
        w = self.words("uh")
        g = self.find(w, "uh", "")[0]
        self.assertEqual(sorted(g), ["e", "kind", "label", "on", "s", "source"])
        self.assertEqual((g["kind"], g["source"], g["on"]), ("filler", "word", True))

    def test_default_lists_cover_the_prd_examples(self):
        strong = self.one("HushFillers.parseList", self.one("HushFillers.DEFAULT_STRONG"))
        soft = self.one("HushFillers.parseList", self.one("HushFillers.DEFAULT_SOFT"))
        # PRD FR-13 examples, already normalised (\u0622\u0647 -> \u0627\u0647, \u0623\u0635\u0644\u064b\u0627 -> \u0627\u0635\u0644\u0627, \u0628\u0642\u0649 -> \u0628\u0642\u064a)
        for x in ("um", "uh", "erm", "ah", "hmm", "mm", "\u0627\u0645\u0645\u0645", "\u0627\u0647", "\u0627\u0648\u0647"):
            self.assertIn(x, strong, x)
        for x in ("like", "you know", "basically", "actually", "i mean", "\u064a\u0639\u0646\u064a", "\u0637\u064a\u0628",
                  "\u0627\u0635\u0644\u0627", "\u0628\u0642\u064a"):
            self.assertIn(x, soft, x)
        self.assertFalse(set(strong) & set(soft))
        # and they work end to end through find
        w = self.words("um", "\u064a\u0639\u0646\u064a", "you", "know", "\u0627\u0645\u0645\u0645")
        got = self.find_with_defaults(w)
        self.assertEqual([(g["label"], g["on"]) for g in got],
                         [("um", True), ("\u064a\u0639\u0646\u064a", False), ("you know", False),
                          ("\u0627\u0645\u0645\u0645", True)])

    def find_with_defaults(self, words):
        # one runner request cannot feed one call's result into another, so read the constants first
        strong = self.one("HushFillers.DEFAULT_STRONG")
        soft = self.one("HushFillers.DEFAULT_SOFT")
        return self.find(words, strong, soft)

    def test_parse_list(self):
        self.assertEqual(self.one("HushFillers.parseList", "Um, UH\n\u0627\u0645\u0645\u060c  \u0622\u0647 ,,"),
                         ["um", "uh", "\u0627\u0645\u0645", "\u0627\u0647"])
        self.assertEqual(self.one("HushFillers.parseList", None), [])
        self.assertEqual(self.one("HushFillers.parseList", ""), [])

    # ================================================================ 11. untranscribed =======================
    def untranscribed(self, env, words, threshold=-40, min_len=0.15, max_len=1.2, hop=0.01):
        return self.one("HushFillers.untranscribed", env, hop, threshold, words, min_len, max_len)

    def sound(self, s, e):
        return {"s": s, "e": e, "label": "(sound)", "kind": "filler", "on": False, "source": "sound"}

    def test_untranscribed_lists_loud_runs_with_no_word_near(self):
        # 300 hops of silence (-60) with one 0.21 s loud run at hops 100..120
        env = [QUIET] * 300
        for i in range(100, 121):
            env[i] = LOUD
        got = self.untranscribed(env, [])
        self.close(got, [self.sound(1.0, 1.21)])
        self.assertEqual(got[0]["label"], "(sound)")
        self.assertIs(got[0]["on"], False)
        self.assertEqual(got[0]["source"], "sound")
        self.assertEqual(got[0]["kind"], "filler")

    def test_untranscribed_a_run_next_to_a_word_is_not_listed(self):
        # loud 0.21 s at hops 400..420; the word 4.1-4.3 s covers hops 395..445 (+-15 hops = 150 ms around it)
        env = [QUIET] * 600
        for i in range(400, 421):
            env[i] = LOUD
        self.assertEqual(self.untranscribed(env, [{"w": "x", "s": 4.1, "e": 4.3}]), [])
        # the same run with the word 0.5 s earlier is far enough: listed
        got = self.untranscribed(env, [{"w": "x", "s": 3.4, "e": 3.6}])
        self.close(got, [self.sound(4.0, 4.21)])

    def test_untranscribed_word_coverage_reaches_150ms_each_side(self):
        env = [QUIET] * 700
        for i in range(340, 361):
            env[i] = LOUD  # run 3.40-3.61 s, word ends at 3.2 s: covered up to ~3.35 s only, run stays whole
        self.close(self.untranscribed(env, [{"w": "x", "s": 3.0, "e": 3.2}]), [self.sound(3.4, 3.61)])
        # partly covered run: loud 4.6-5.3 s, word 5.0-5.2 s covers hops ~485..~535: the uncovered 4.6-~4.85 s remains
        env2 = [QUIET] * 700
        for i in range(460, 530):
            env2[i] = LOUD
        got = self.untranscribed(env2, [{"w": "x", "s": 5.0, "e": 5.2}])
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0]["s"], 4.6, delta=1e-9)
        self.assertAlmostEqual(got[0]["e"], 4.85, delta=0.0101)  # one hop of slack: floor(s / hop) of a decimal time

    def test_untranscribed_too_short_or_too_long_runs_are_not_listed(self):
        env = [QUIET] * 1000
        for lo, n in ((50, 14), (200, 16), (400, 119), (600, 121), (800, 200)):  # 0.14, 0.16, 1.19, 1.21, 2.0 s
            for i in range(lo, lo + n):
                env[i] = LOUD
        got = self.untranscribed(env, [])
        self.close(got, [self.sound(2.0, 2.16), self.sound(4.0, 5.19)])

    def test_untranscribed_threshold_is_inclusive_and_the_end_closes_a_run(self):
        env = [QUIET] * 100 + [-40.0] * 20  # exactly at the threshold counts as loud; the run reaches the end
        self.close(self.untranscribed(env, []), [self.sound(1.0, 1.2)])
        env2 = [QUIET] * 100 + [-40.1] * 20
        self.assertEqual(self.untranscribed(env2, []), [])

    def test_untranscribed_boundaries_are_exact_with_a_binary_hop(self):
        # hop 0.5 s (exact in binary, so no decimal rounding): a word at 10.0-12.0 s covers hops floor(10/0.5) - 15 = 5
        # up to ceil(12/0.5) + 15 = 39 exclusive, i.e. hops 5..38; hops 4 and 39 are the first uncovered ones.
        env = [QUIET] * 60
        for i in (4, 5, 38, 39):
            env[i] = LOUD
        word = [{"w": "x", "s": 10.0, "e": 12.0}]
        # each run is one hop = 0.5 s; minLen = maxLen = 0.5 shows both length bounds are inclusive
        got = self.untranscribed(env, word, min_len=0.5, max_len=0.5, hop=0.5)
        self.close(got, [self.sound(2.0, 2.5), self.sound(19.5, 20.0)])
        # 0.5 s is out of range when the limits are just either side of it
        self.assertEqual(self.untranscribed(env, word, min_len=0.51, max_len=1.0, hop=0.5), [])
        self.assertEqual(self.untranscribed(env, word, min_len=0.1, max_len=0.49, hop=0.5), [])

    def test_untranscribed_custom_length_limits_and_empty_input(self):
        env = [QUIET] * 300
        for i in range(100, 150):
            env[i] = LOUD  # 0.5 s
        self.assertEqual(self.untranscribed(env, [], min_len=0.6, max_len=1.2), [])
        self.assertEqual(self.untranscribed(env, [], min_len=0.1, max_len=0.4), [])
        self.close(self.untranscribed(env, [], min_len=0.1, max_len=0.6), [self.sound(1.0, 1.5)])
        self.assertEqual(self.untranscribed([], []), [])


@unittest.skipUnless(NODE, "node is not installed")
class HushCharacterizationUpstream(HushCharacterizationMixin, unittest.TestCase):
    """The owner's upstream modules (ROOT = adobe/tools/hush/_upstream)."""


@unittest.skipUnless(TOOLS_PRESENT, NO_TOOLS)
class HushUpstreamIntegrity(unittest.TestCase):
    """The characterized files are the ones the owner shipped: adobe/tools/UPSTREAM-SHA256.txt lists their hashes."""

    FILES = ["hush/_upstream/js/wav.js", "hush/_upstream/js/detect.js", "hush/_upstream/js/fillers.js"]

    def test_hush_pure_modules_match_the_sha256_listing(self):
        listing = {}
        for line in (ADOBE_TOOLS / "UPSTREAM-SHA256.txt").read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, name = line.split(None, 1)
                listing[name.strip()] = digest.lower()
        for rel in self.FILES:
            self.assertIn(rel, listing)
            self.assertEqual(hashlib.sha256((ADOBE_TOOLS / rel).read_bytes()).hexdigest(), listing[rel], rel)


@unittest.skipUnless(NODE, "node is not installed")
class HushCharacterizationPort(HushCharacterizationMixin, unittest.TestCase):
    """The port (ROOT = adobe/tools/hush/src): every test above again. The one deliberate difference is the display bug
    in HushDetect.fmt (controller ruling): the seconds are rounded to 0.1 before the minutes are split."""

    ROOT = ADOBE_TOOLS / "hush" / "src"

    def test_fmt_rounding_edges_are_quirks(self):
        # the port rounds first: 9.96 is "0:10.0" (upstream "0:010.0") and 59.96 is "1:00.0" (upstream "0:60.0")
        cases = [(9.96, "0:10.0"), (59.96, "1:00.0"), (119.96, "2:00.0"), (599.96, "10:00.0"), (3599.96, "60:00.0"),
                 (9.94, "0:09.9"), (59.94, "0:59.9")]
        got = self.js([call("HushDetect.fmt", s) for s, _ in cases])
        self.assertEqual(got, [w for _, w in cases])


if __name__ == "__main__":
    unittest.main()
