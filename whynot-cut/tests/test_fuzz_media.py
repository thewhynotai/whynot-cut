# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 48 (L-T10, spec L-G55): caps on time and memory for hostile media and documents.

Targets: lib.media.probe (PyAV), the Pillow users lib.client_db.image_palette / image_info and lib.media_util.open_rgb,
lib.discover.read_document / _pdf_text (pypdf) / _docx_text (zip + ElementTree).
Not crash-hunting inside ffmpeg: the property is "returns a value or an ordinary error, within the time cap, under the
memory cap". Every input is synthetic bytes written into a temp folder under the sandbox temp dir.

Memory measurement: tracemalloc sees Python allocations only. PyAV (libav), Pillow's C decoder and zlib buffers escape it,
so on Windows a sampler thread also polls the process working set (ctypes GetProcessMemoryInfo) every 10 ms and the
rise over the baseline is asserted too. It is a sampled peak, so it can miss a spike shorter than 10 ms; the caps carry margin.

KNOWN_OPEN: findings the owner has not fixed yet. The strict test of each id is an expected failure while the id is listed
(`xfail_open`): when the owner fixes the engine it shows up as an UNEXPECTED SUCCESS, which means: delete the id here and set
the finding to fixed in tests/security/fuzz/regressions.json.
Run:  tools/test.sh -p test_fuzz_media.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import os
import shutil
import struct
import threading
import time
import tracemalloc
import unittest
import warnings
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE / "security" / "fuzz"))
_sys.path.insert(0, str(HERE.parent / "engine" / "reel"))

import _hyp  # noqa: E402
from _hyp import fuzz, given, requires_hypothesis, st  # noqa: E402

MB = 1024 * 1024
TIME_CAP_S = 20
MEDIA_CAP_MB = 400
DOC_CAP_MB = 600

# short id -> description of an open finding (see module docstring)
KNOWN_OPEN = {
    "png_1x_2x_palette": "client_db.image_palette(): a 12000x12000 grey PNG (144 MP, 144 MB expanded, file ~140 KB) is only "
                         "warned about by Pillow (DecompressionBombWarning, between 1x and 2x of MAX_IMAGE_PIXELS), then "
                         "decoded and convert('RGB') triples it: ~690 MB process rise (client_db.py:53-54)",
    "png_1x_2x_open_rgb": "media_util.open_rgb(): same PNG, ~650 MB process rise (media_util.py:202-203)",
    "docx_bomb": "discover._docx_text(): word/document.xml of 200 MB of spaces in a <1 MB .docx is fully inflated "
                 "(z.read) and parsed: ~660 MB Python peak, no size cap (discover.py:201-203); read_document hits the same path",
}


def xfail_open(id_):
    """The strict test of an open finding: an expected failure while `id_` is in KNOWN_OPEN, an ordinary test after."""
    return _hyp.xfail_while_open(id_, KNOWN_OPEN)


# --------------------------------------------------------------------------- measurement
def _rss_bytes():
    """Current working set of this process in bytes, or None when it cannot be read."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return int(c.WorkingSetSize)
        return None
    try:
        import psutil
        return int(psutil.Process().memory_info().rss)
    except Exception:  # noqa: BLE001
        return None


class Result:
    def __init__(self):
        self.value = None
        self.exc = None
        self.secs = 0.0
        self.py_mb = 0.0
        self.rss_mb = None
        self.hang = False
        self.warns = []
        self.typed = ()

    def describe(self):
        return "secs=%.2f py_peak=%.0fMB rss_rise=%s exc=%r hang=%s warns=%s" % (
            self.secs, self.py_mb, "n/a" if self.rss_mb is None else "%.0fMB" % self.rss_mb, self.exc, self.hang,
            [w for w in self.warns])


def typed_errors(name):
    """The exception classes a target is documented to raise for a bad file (anything else is a finding). Pillow documents
    UnidentifiedImageError (an OSError), OSError for truncated data, ValueError, DecompressionBombError and, from its PNG reader,
    SyntaxError ("broken PNG file"); zipfile documents BadZipFile / LargeZipFile and lets zlib.error, EOFError and
    NotImplementedError of a corrupt member through, and a missing member is a KeyError; pypdf raises PyPdfError subclasses.
    media.probe and read_document answer with a value (an `errors` list / an "[unreadable ...]" text) and raise nothing."""
    import zipfile
    from xml.etree import ElementTree as ET
    from PIL import Image
    from pypdf.errors import PyPdfError
    pil = (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError)
    table = {"probe": (), "read_document": (), "image_palette": pil, "image_info": pil, "open_rgb": pil,
             "_pdf_text": (PyPdfError, OSError, ValueError, EOFError),
             "_docx_text": (zipfile.BadZipFile, zipfile.LargeZipFile, KeyError, ET.ParseError, zlib.error, EOFError, OSError,
                            ValueError, NotImplementedError)}
    if name not in table:
        raise KeyError("test_fuzz_media: no typed-error policy for %r: add it to typed_errors()" % name)
    return table[name]


def measure(fn, *args, seconds=TIME_CAP_S, typed=None, **kw):
    """Run fn under the time cap, record wall time, Python peak (tracemalloc), sampled process peak rise, warnings. `typed` =
    the exceptions that are an ordinary answer for this target (default: typed_errors(fn.__name__))."""
    r = Result()
    r.typed = typed_errors(getattr(fn, "__name__", "")) if typed is None else typed
    base = _rss_bytes()
    peak = [base or 0]
    stop = threading.Event()

    def sample():
        while not stop.is_set():
            v = _rss_bytes()
            if v and v > peak[0]:
                peak[0] = v
            stop.wait(0.01)

    th = threading.Thread(target=sample, daemon=True)
    tracemalloc.start()
    th.start()
    t0 = time.monotonic()
    try:
        with warnings.catch_warnings(record=True) as wl:
            warnings.simplefilter("always")
            try:
                r.value = _hyp.within(seconds, fn, *args, **kw)
            except _hyp.Hang:
                r.hang = True
            except BaseException as e:  # noqa: BLE001
                r.exc = e
        r.warns = sorted({w.category.__name__ for w in wl})
    finally:
        r.secs = time.monotonic() - t0
        r.py_mb = tracemalloc.get_traced_memory()[1] / MB
        tracemalloc.stop()
        stop.set()
        th.join(1)
    if base is not None:
        r.rss_mb = max(0, peak[0] - base) / MB
    return r


def _ordinary(exc, typed):
    """No error, or one of the target's documented error types (never resource exhaustion or runaway recursion, even when a
    typed class such as RuntimeError / OSError would cover it)."""
    if exc is None:
        return True
    if isinstance(exc, (MemoryError, RecursionError)):
        return False
    return isinstance(exc, tuple(typed))


def breaks_cap(r, cap_mb, seconds=TIME_CAP_S):
    """The first cap that does not hold, as text, or '' when all hold."""
    if r.hang:
        return "no result within %ds" % seconds
    if not _ordinary(r.exc, r.typed):
        return "unhandled %r" % (r.exc,)
    if r.secs > seconds:
        return "took %.1fs" % r.secs
    if r.py_mb > cap_mb:
        return "python peak %.0f MB" % r.py_mb
    if r.rss_mb is not None and r.rss_mb > cap_mb:
        return "process peak rise %.0f MB" % r.rss_mb
    return ""


# --------------------------------------------------------------------------- synthetic hostile files
def box(kind, payload=b"", size=None):
    return struct.pack(">I4s", (8 + len(payload)) if size is None else size, kind) + payload


FTYP = box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2mp41")


def nested_boxes(depth, kinds=(b"moov", b"trak", b"mdia", b"minf")):
    data = b""
    for i in range(depth):
        data = box(kinds[i % len(kinds)], data)
    return data


def mp4_cases():
    big = struct.pack(">I", 0xFFFFFFF0)
    return {
        "zero_byte": b"",
        "ftyp_only": FTYP,
        "ftyp_truncated": FTYP[:13],
        "moov_claims_4GiB": FTYP + big + b"moov" + b"\0" * 64,
        "moov_size_0": FTYP + box(b"moov", b"\0" * 64, size=0),
        "moov_size_1_large_max": FTYP + struct.pack(">I4sQ", 1, b"moov", 2 ** 64 - 1) + b"\0" * 64,
        "moov_size_1_large_0": FTYP + struct.pack(">I4sQ", 1, b"moov", 0) + b"\0" * 64,
        "moov_size_2": FTYP + box(b"moov", b"\0" * 64, size=2),
        "mdat_claims_4GiB": FTYP + big + b"mdat" + b"\0" * 64,
        "nested_1000": FTYP + nested_boxes(1000),
        "nested_1000_trunc": (FTYP + nested_boxes(1000))[:-9],
        "stts_huge_entry_count": FTYP + box(b"moov", box(b"trak", box(b"mdia", box(
            b"minf", box(b"stbl", box(b"stts", struct.pack(">IIII", 0, 0x7FFFFFFF, 1, 1))))))),
    }


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(path, w, h, rows_of_idat=1, bomb=False):
    """Grey 8-bit PNG whose IHDR claims w x h. bomb=False: IDAT holds a few rows only (a lie, a few hundred bytes).
    bomb=True: IDAT is the real zlib stream of all-zero rows (w+1 bytes each), expanding to w*h bytes."""
    comp = zlib.compressobj(1)
    out = bytearray()
    row = b"\0" * (w + 1)
    n = h if bomb else rows_of_idat
    chunk_rows = max(1, (8 * MB) // (w + 1))
    done = 0
    while done < n:
        k = min(chunk_rows, n - done)
        out += comp.compress(row * k)
        done += k
    out += comp.flush()
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)))
        f.write(png_chunk(b"IDAT", bytes(out)) + png_chunk(b"IEND", b""))


def zlib_zeros(total, level=1):
    comp = zlib.compressobj(level)
    out = bytearray()
    block = b"\0" * MB
    left = total
    while left > 0:
        n = min(left, MB)
        out += comp.compress(block[:n])
        left -= n
    return bytes(out + comp.flush())


def pdf_from_objects(objs, trailer_extra=b"", xref=b""):
    """objs: {num: bytes of body}. Offsets in the xref are deliberately not computed unless xref is given."""
    body = bytearray(b"%PDF-1.4\n")
    for n, o in objs.items():
        body += b"%d 0 obj\n" % n + o + b"\nendobj\n"
    body += xref + b"trailer\n<< /Root 1 0 R " + trailer_extra + b">>\nstartxref\n0\n%%EOF\n"
    return bytes(body)


def pdf_cases(tmp):
    cases = {
        "random_bytes_pdf_header": b"%PDF-1.7\n" + bytes((i * 131 + 7) % 256 for i in range(20000)),
        "pages_self_loop": pdf_from_objects({
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [2 0 R] /Count 1 >>"}),
        "pages_two_node_loop": pdf_from_objects({
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 /Parent 3 0 R >>",
            3: b"<< /Type /Pages /Kids [2 0 R] /Count 1 /Parent 2 0 R >>"}),
        "xref_claims_1e9_objects": pdf_from_objects(
            {1: b"<< /Type /Catalog /Pages 2 0 R >>", 2: b"<< /Type /Pages /Kids [] /Count 0 >>"},
            xref=b"xref\n0 1000000000\n0000000000 65535 f \n"),
        "trailer_size_1e9": pdf_from_objects(
            {1: b"<< /Type /Catalog /Pages 2 0 R >>", 2: b"<< /Type /Pages /Kids [] /Count 0 >>"},
            trailer_extra=b"/Size 1000000000 "),
        "count_huge_kids_empty": pdf_from_objects({
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [] /Count 2000000000 >>"}),
    }
    stream = zlib_zeros(200 * MB)
    cases["flate_zip_bomb_200MB"] = pdf_from_objects({
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Contents 4 0 R >>",
        4: b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream"})
    return cases


def write_docx(path, xml_prefix, filler_byte, filler_len, xml_suffix, member="word/document.xml"):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        with z.open(member, "w", force_zip64=True) as f:
            f.write(xml_prefix)
            block = filler_byte * MB
            left = filler_len
            while left > 0:
                n = min(left, MB)
                f.write(block[:n])
                left -= n
            f.write(xml_suffix)


W_NS = b'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
DOCX_HEAD = b"<w:document " + W_NS + b"><w:body><w:p><w:r><w:t>"
DOCX_TAIL = b"</w:t></w:r></w:p></w:body></w:document>"


class TempCase(unittest.TestCase):
    """One scratch folder per class, inside the sandbox temp dir; removed at the end (real files only, no links)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = _hyp.scratch_dir("wnc-fuzzmedia-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def assertCaps(self, r, cap_mb, what):
        why = breaks_cap(r, cap_mb)
        self.assertEqual("", why, "%s: %s (%s)" % (what, why, r.describe()))


class TypedErrorPolicy(unittest.TestCase):
    """`breaks_cap` / `_ordinary` can fail: an untyped exception from a target is reported, a typed one is not."""

    def _run(self, exc, name):
        def target(p):
            raise exc
        target.__name__ = name
        return measure(target, Path("x"))

    def test_an_untyped_error_is_a_finding(self):
        for exc, name in ((KeyError("k"), "image_palette"), (KeyError("k"), "open_rgb"), (TypeError("t"), "image_info"),
                          (AttributeError("a"), "_pdf_text"), (IndexError("i"), "_docx_text"), (ValueError("v"), "probe"),
                          (ZeroDivisionError("z"), "read_document")):
            why = breaks_cap(self._run(exc, name), MEDIA_CAP_MB)
            self.assertTrue(why.startswith("unhandled"), (name, exc, why))

    def test_a_documented_error_is_not_a_finding(self):
        from PIL import Image, UnidentifiedImageError
        for exc, name in ((UnidentifiedImageError("u"), "image_palette"), (Image.DecompressionBombError("b"), "open_rgb"),
                          (OSError("o"), "image_info"), (zipfile.BadZipFile("z"), "_docx_text"), (KeyError("m"), "_docx_text"),
                          (ValueError("v"), "_pdf_text")):
            self.assertEqual("", breaks_cap(self._run(exc, name), MEDIA_CAP_MB), (name, exc))

    def test_resource_exhaustion_is_never_ordinary_even_when_the_class_is_allowed(self):
        self.assertFalse(_ordinary(RecursionError(), (RuntimeError,)))
        self.assertFalse(_ordinary(MemoryError(), (Exception,)))
        self.assertTrue(_ordinary(None, ()))

    def test_every_target_has_a_policy_and_an_unknown_one_is_refused(self):
        for name in ("probe", "read_document", "image_palette", "image_info", "open_rgb", "_pdf_text", "_docx_text"):
            self.assertIsInstance(typed_errors(name), tuple)
        with self.assertRaises(KeyError):
            typed_errors("not_a_target")


# --------------------------------------------------------------------------- 1. media headers into probe()
class ProbeHostile(TempCase):
    def run_probe(self, name, data, ext=".mp4"):
        from lib import media
        p = self.tmp / (name + ext)
        p.write_bytes(data)
        return measure(media.probe, p)

    def test_box_cases(self):
        for name, data in mp4_cases().items():
            for ext in (".mp4", ".mov"):
                r = self.run_probe(name, data, ext)
                self.assertCaps(r, MEDIA_CAP_MB, "probe(%s%s)" % (name, ext))
                if r.exc is None:
                    self.assertIsInstance(r.value, dict, name)
                    self.assertIn("errors", r.value)

    def test_random_bytes_each_container_extension(self):
        import random
        rnd = random.Random(48)
        for ext in (".mp4", ".mov", ".mkv", ".wav"):
            data = bytes(rnd.getrandbits(8) for _ in range(65536))
            r = self.run_probe("random", data, ext)
            self.assertCaps(r, MEDIA_CAP_MB, "probe(random%s)" % ext)
            if r.exc is None:
                self.assertIsInstance(r.value, dict)

    def test_riff_wav_claims_4GiB(self):
        data = b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 2, 48000, 192000, 4, 16) \
            + b"data" + struct.pack("<I", 0xFFFFFFFF) + b"\0" * 1024
        r = self.run_probe("wav_claims_4GiB", data, ".wav")
        self.assertCaps(r, MEDIA_CAP_MB, "probe(wav 4GiB data)")


# --------------------------------------------------------------------------- 2. huge-dimension PNGs into Pillow users
class PillowHostile(TempCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.files = {}
        for name, (w, h, bomb) in {"lie_60000": (60000, 60000, False), "lie_200000": (200000, 200000, False),
                                   "bomb_144M_px": (12000, 12000, True),          # ~144 MB expanded: above 89 MP, below 2x
                                   "bomb_200M_px": (20000, 10000, True)}.items():   # ~200 MB expanded: above 2x
            p = cls.tmp / (name + ".png")
            write_png(p, w, h, bomb=bomb)
            cls.files[name] = p

    def users(self):
        from lib import client_db, media_util
        def image_info(p):
            return client_db.image_info(p, self.tmp / "deriv")
        return {"client_db.image_palette": client_db.image_palette, "client_db.image_info": image_info,
                "media_util.open_rgb": media_util.open_rgb}

    def test_file_sizes_are_small(self):
        for name, p in self.files.items():
            self.assertLess(p.stat().st_size, MB, name)

    def test_lying_ihdr_is_stopped(self):
        for fn_name, fn in self.users().items():
            for name in ("lie_60000", "lie_200000"):
                r = measure(fn, self.files[name])
                self.assertCaps(r, DOC_CAP_MB, "%s(%s)" % (fn_name, name))

    def test_bomb_over_2x_limit_is_stopped(self):
        for fn_name, fn in self.users().items():
            r = measure(fn, self.files["bomb_200M_px"])
            self.assertCaps(r, DOC_CAP_MB, "%s(bomb_200M_px)" % fn_name)

    # Between 1x and 2x of Pillow's limit it only WARNS (DecompressionBombWarning) and then decodes: our code adds no guard.
    def _bomb_1x_2x(self, key):
        r = measure(self.users()[key], self.files["bomb_144M_px"])
        self.assertIn("DecompressionBombWarning", r.warns)       # the observable: Pillow's default warning, nothing of ours
        return r

    @_hyp.requires_ram(3500)
    def test_bomb_1x_2x_image_info(self):
        self.assertCaps(self._bomb_1x_2x("client_db.image_info"), DOC_CAP_MB, "image_info(bomb_144M_px)")

    @xfail_open("png_1x_2x_palette")
    @_hyp.requires_ram(3500)
    def test_bomb_1x_2x_image_palette(self):
        self.assertCaps(self._bomb_1x_2x("client_db.image_palette"), DOC_CAP_MB, "image_palette(bomb_144M_px)")

    @xfail_open("png_1x_2x_open_rgb")
    @_hyp.requires_ram(3500)
    def test_bomb_1x_2x_open_rgb(self):
        self.assertCaps(self._bomb_1x_2x("media_util.open_rgb"), DOC_CAP_MB, "open_rgb(bomb_144M_px)")

    def test_our_code_never_switches_off_or_raises_pillows_pixel_limit(self):
        """Guard: nothing in the engine sets Image.MAX_IMAGE_PIXELS (to None or higher) or filters the bomb warning away.
        (Pillow's own default alone is not enough between 1x and 2x: see the png_1x_2x findings.)"""
        import re
        from PIL import Image
        hits = []
        for p in (HERE.parent / "engine").rglob("*.py"):
            text = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"Image\.MAX_IMAGE_PIXELS\s*=", text) or re.search(r"simplefilter\(\s*[\"']ignore[\"'].*DecompressionBomb", text):
                hits.append(str(p))
        self.assertEqual([], hits, "the engine changes Pillow's pixel limit or hides its warning: %s" % hits)
        self.assertEqual(89478485, Image.MAX_IMAGE_PIXELS)


# --------------------------------------------------------------------------- 3. malformed PDFs into pypdf
class PdfHostile(TempCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.files = {}
        for name, data in pdf_cases(cls.tmp).items():
            p = cls.tmp / (name + ".pdf")
            p.write_bytes(data)
            cls.files[name] = p

    @_hyp.requires_ram(3500)
    def test_pdf_text_and_read_document(self):
        from lib import discover
        for name, p in self.files.items():
            for fn_name, fn in (("_pdf_text", discover._pdf_text), ("read_document", discover.read_document)):
                r = measure(fn, p)
                self.assertCaps(r, DOC_CAP_MB, "%s(%s)" % (fn_name, name))
                if fn_name == "read_document" and r.exc is None:
                    self.assertIsInstance(r.value, str)


# --------------------------------------------------------------------------- 4. zip bombs as .docx
class DocxHostile(TempCase):
    def bomb(self):
        p = self.tmp / "bomb.docx"
        if not p.exists():
            write_docx(p, DOCX_HEAD, b" ", 200 * MB, DOCX_TAIL)
        self.assertLess(p.stat().st_size, MB)
        return p

    @xfail_open("docx_bomb")
    @_hyp.requires_ram(3500)
    def test_zip_bomb_200MB_of_spaces(self):
        from lib import discover
        p = self.bomb()
        for fn_name, fn in (("_docx_text", discover._docx_text), ("read_document", discover.read_document)):
            self.assertCaps(measure(fn, p), DOC_CAP_MB, "%s(200MB spaces docx)" % fn_name)

    def test_corrupt_and_missing_member(self):
        from lib import discover
        good = self.tmp / "good.docx"
        write_docx(good, DOCX_HEAD, b"a", 10, DOCX_TAIL)
        raw = good.read_bytes()
        cases = {"truncated_zip": raw[:len(raw) // 2], "garbage_zip_header": b"PK\x03\x04" + b"\xff" * 300,
                 "empty": b"", "central_dir_only": raw[-22:], "flipped_bytes": bytes(b ^ 0x5A for b in raw)}
        for name, data in cases.items():
            p = self.tmp / (name + ".docx")
            p.write_bytes(data)
            for fn_name, fn in (("_docx_text", discover._docx_text), ("read_document", discover.read_document)):
                r = measure(fn, p)
                self.assertCaps(r, DOC_CAP_MB, "%s(%s)" % (fn_name, name))
            self.assertTrue(discover.read_document(p).startswith("[unreadable .docx"), name)
        nomember = self.tmp / "nomember.docx"
        with zipfile.ZipFile(nomember, "w") as z:
            z.writestr("word/other.xml", "<a/>")
        r = measure(discover._docx_text, nomember)
        self.assertCaps(r, DOC_CAP_MB, "_docx_text(missing member)")
        self.assertIsInstance(r.exc, KeyError)
        self.assertTrue(discover.read_document(nomember).startswith("[unreadable .docx"))

    def test_xml_entity_expansion(self):
        """Billion-laughs inside document.xml: ElementTree (expat) must not blow up memory."""
        from lib import discover
        ents = '<!ENTITY a0 "aaaaaaaaaa">' + "".join(
            '<!ENTITY a%d "%s">' % (i, "&a%d;" % (i - 1) * 10) for i in range(1, 8))
        xml = ('<?xml version="1.0"?><!DOCTYPE w:document [' + ents + ']>').encode() \
            + b"<w:document " + W_NS + b"><w:body><w:p><w:r><w:t>&a7;</w:t></w:r></w:p></w:body></w:document>"
        p = self.tmp / "laughs.docx"
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", xml)
        r = measure(discover._docx_text, p)
        self.assertCaps(r, DOC_CAP_MB, "_docx_text(billion laughs)")


# --------------------------------------------------------------------------- Hypothesis: random bytes per extension
@requires_hypothesis
class RandomBytesPerExtension(TempCase):
    counter = 0

    def write(self, ext, data):
        type(self).counter += 1
        p = self.tmp / ("r%d%s" % (type(self).counter, ext))
        p.write_bytes(data)
        return p

    def check(self, r, what):
        self.assertTrue(not r.hang, "%s: no result within %ds" % (what, TIME_CAP_S))
        self.assertTrue(_ordinary(r.exc, r.typed), "%s: unhandled %r (allowed: %s)" % (what, r.exc, [c.__name__ for c in r.typed]))
        self.assertLess(r.secs, TIME_CAP_S, what)

    @fuzz(unit_examples=30)
    @given(st.binary(max_size=4096), st.sampled_from([".mp4", ".mov", ".wav"]))
    def test_probe_random_bytes(self, data, ext):
        from lib import media
        r = measure(media.probe, self.write(ext, data))
        self.check(r, "probe(%s)" % ext)
        if r.exc is None:
            self.assertIsInstance(r.value, dict)

    @fuzz(unit_examples=30)
    @given(st.binary(max_size=4096), st.sampled_from([".mp4", ".mov"]))
    def test_probe_with_valid_ftyp_prefix(self, data, ext):
        from lib import media
        r = measure(media.probe, self.write(ext, FTYP + data))
        self.check(r, "probe(ftyp+random%s)" % ext)

    @fuzz(unit_examples=30)
    @given(st.binary(max_size=4096), st.sampled_from([".png", ".jpg"]))
    def test_pillow_users_random_bytes(self, data, ext):
        from lib import client_db, media_util
        p = self.write(ext, data)
        for name, fn in (("image_palette", client_db.image_palette), ("open_rgb", media_util.open_rgb)):
            self.check(measure(fn, p), "%s(%s)" % (name, ext))

    @fuzz(unit_examples=25)
    @given(st.binary(max_size=4096), st.sampled_from([".png", ".jpg"]))
    def test_pillow_users_png_jpeg_signature_prefix(self, data, ext):
        from lib import client_db
        sig = b"\x89PNG\r\n\x1a\n" if ext == ".png" else b"\xff\xd8\xff\xe0"
        self.check(measure(client_db.image_palette, self.write(ext, sig + data)), "image_palette(sig+random%s)" % ext)

    @fuzz(unit_examples=30)
    @given(st.binary(max_size=4096), st.sampled_from([".pdf", ".docx", ".srt"]))
    def test_read_document_random_bytes(self, data, ext):
        from lib import discover
        r = measure(discover.read_document, self.write(ext, data))
        self.check(r, "read_document(%s)" % ext)
        if r.exc is None:
            self.assertIsInstance(r.value, str)

    @fuzz(unit_examples=30)
    @given(st.binary(max_size=4096))
    def test_pdf_text_pdf_header_random_bytes(self, data):
        from lib import discover
        self.check(measure(discover._pdf_text, self.write(".pdf", b"%PDF-1.7\n" + data)), "_pdf_text(header+random)")


if __name__ == "__main__":
    unittest.main()
