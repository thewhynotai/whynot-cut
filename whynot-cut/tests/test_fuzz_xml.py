# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 48 (L-T10, Addendum L §L4.4, L-G26 / L-G28): the Premiere project reader in lib/verify.py.

verify.py is the engine's only reader of a Premiere project (`.prproj` = gzip + XML; premiere_xml.py only writes).
Fixtures: billion laughs, quadratic blow-up, external entities (file and http), a gzip bomb, deep nesting, hostile
random bytes. The property: it fails fast, never resolves an external entity, never reads more than a cap, never
writes anything, and returns a signature string (or None for an unreadable file) instead of crashing.

KNOWN_OPEN lists what the fuzzer found that the owner (executor, lib/verify.py) has not fixed yet. The strict test of each
entry is an expected failure while its id is listed (`xfail_open`): when the owner applies
lane3/hooks/L-T10/verify-caps.patch the test shows up as an UNEXPECTED SUCCESS, which means: delete the id here and set the
finding to fixed in tests/security/fuzz/regressions.json.
Run:  tools/test.sh -p test_fuzz_xml.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import gzip
import time
import tracemalloc
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE / "security" / "fuzz"))
_sys.path.insert(0, str(HERE.parent / "engine" / "reel"))

import _hyp  # noqa: E402
from _hyp import fuzz, given, requires_hypothesis, st  # noqa: E402

from lib import verify  # noqa: E402

KNOWN_OPEN = {
    "xml-deep-recursion": "verify._content_signature: RecursionError on an XML nested ~5000 deep (_canonical is recursive)",
    "gzip-bomb-uncapped": "verify.prproj_signature / _prproj_xml decompress a gzip with no size cap (3.2x the output in memory)",
}
CAP_NAME = "MAX_XML_BYTES"          # the constant lane3/hooks/L-T10/verify-caps.patch adds
PATCHED = hasattr(verify, CAP_NAME)


def xfail_open(id_):
    """The strict test of an open finding: an expected failure while `id_` is in KNOWN_OPEN, an ordinary test after."""
    return _hyp.xfail_while_open(id_, KNOWN_OPEN)


class CapAndKnownOpenAgree(unittest.TestCase):
    def test_once_the_cap_patch_is_in_the_known_open_dict_must_be_empty(self):
        if PATCHED and KNOWN_OPEN:
            self.fail("verify-caps.patch is applied (%s exists) but KNOWN_OPEN still lists %s: delete the ids here and set their "
                      "status to fixed in tests/security/fuzz/regressions.json" % (CAP_NAME, sorted(KNOWN_OPEN)))


PREFIXES = (verify.SIGNATURE_PREFIX, verify.RAW_PREFIX, verify.BYTES_PREFIX)


def tmpdir():
    return _hyp.scratch_dir()


def laughs(levels=9, fan=10):
    ents = '<!ENTITY a0 "lol">' + "".join('<!ENTITY a%d "%s">' % (i, ("&a%d;" % (i - 1)) * fan) for i in range(1, levels + 1))
    return '<?xml version="1.0"?><!DOCTYPE x [%s]><x>&a%d;</x>' % (ents, levels)


def quadratic(n=30000):
    return '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "%s">]><x>%s</x>' % ("a" * 5000, "&a;" * n)


def as_read(text: str) -> str:
    """Text the way the engine gets it: _prproj_xml decodes file bytes with errors="replace", so no lone surrogate."""
    return text.encode("utf-8", "surrogatepass").decode("utf-8", "replace")


def prproj(path: Path, xml: bytes) -> Path:
    with gzip.open(path, "wb", compresslevel=6) as f:
        f.write(xml)
    return path


class BombFixtures(unittest.TestCase):
    def test_billion_laughs_fails_fast_and_signs_raw(self):
        t = time.time()
        out = _hyp.within(10, verify._content_signature, laughs())
        self.assertLess(time.time() - t, 5)
        self.assertTrue(out.startswith(PREFIXES), out)

    def test_quadratic_blowup_fails_fast(self):
        t = time.time()
        out = _hyp.within(10, verify._content_signature, quadratic())
        self.assertLess(time.time() - t, 5)
        self.assertTrue(out.startswith(PREFIXES), out)

    def test_billion_laughs_inside_a_prproj_file_fails_fast(self):
        p = prproj(tmpdir() / "laughs.prproj", laughs().encode())
        t = time.time()
        out = _hyp.within(10, verify.prproj_signature, p)
        self.assertLess(time.time() - t, 5)
        self.assertTrue(out.startswith(PREFIXES), out)

    def test_external_file_entity_is_not_resolved(self):
        d = tmpdir()
        secret = d / "secret.txt"
        sigs = []
        for content in ("AAAA-first-contents", "BBBB-other-contents"):
            secret.write_text(content, encoding="utf-8")
            xml = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "%s">]><x>&e;</x>' % secret.as_uri())
            sigs.append(verify._content_signature(xml))
        self.assertEqual(sigs[0], sigs[1], "the signature changed with the contents of an external file: it was read")

    def test_external_http_entity_is_not_fetched(self):
        import socket
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(0.5)
        port = srv.getsockname()[1]
        try:
            xml = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "http://127.0.0.1:%d/x">]><x>&e;</x>' % port)
            verify._content_signature(xml)
            with self.assertRaises(socket.timeout):
                srv.accept()     # nobody connected
        finally:
            srv.close()

    def test_parameter_entity_and_external_dtd_are_not_loaded(self):
        xml = ('<?xml version="1.0"?><!DOCTYPE x SYSTEM "http://127.0.0.1:9/evil.dtd"><x>1</x>')
        out = _hyp.within(10, verify._content_signature, xml)
        self.assertTrue(out.startswith(PREFIXES))

    def test_read_only_never_writes(self):
        d = tmpdir()
        p = prproj(d / "a.prproj", laughs().encode())
        before = sorted(x.name for x in d.iterdir())
        verify.prproj_signature(p)
        self.assertEqual(sorted(x.name for x in d.iterdir()), before)


class GzipBomb(unittest.TestCase):
    N_MB = 60

    def _bomb(self):
        p = tmpdir() / "bomb.prproj"
        with gzip.open(p, "wb", compresslevel=9) as f:
            f.write(b"<?xml version='1.0'?><r>")
            for _ in range(self.N_MB):
                f.write(b" " * 1_000_000)
            f.write(b"</r>")
        self.assertLess(p.stat().st_size, 200_000)
        return p

    def _peak_mb(self, fn, *a):
        tracemalloc.start()
        try:
            fn(*a)
            return tracemalloc.get_traced_memory()[1] / 2 ** 20
        finally:
            tracemalloc.stop()

    @xfail_open("gzip-bomb-uncapped")
    @_hyp.requires_ram(1500)
    def test_gzip_bomb_is_capped(self):
        if not PATCHED:
            # unpatched reader: it inflates the whole 60 MB bomb in memory (L-G26), which is what fails here
            peak = self._peak_mb(verify.prproj_signature, self._bomb())
            self.assertLess(peak, self.N_MB * 2, "the reader inflated the whole bomb: peak %.0f MB for a %d MB member" % (peak, self.N_MB))
        old = getattr(verify, CAP_NAME)
        setattr(verify, CAP_NAME, 8 * 2 ** 20)
        try:
            p = self._bomb()
            peak = self._peak_mb(verify.prproj_signature, p)
            self.assertLess(peak, 40, "peak %.0f MB for an 8 MB cap" % peak)
            self.assertTrue(verify.prproj_signature(p).startswith(verify.BYTES_PREFIX))
            self.assertIsNone(verify._prproj_xml(p))
        finally:
            setattr(verify, CAP_NAME, old)


class DeepNesting(unittest.TestCase):
    DEEP = "<a>" * 5000 + "</a>" * 5000

    @xfail_open("xml-deep-recursion")
    def test_deep_xml_gets_a_signature(self):
        self.assertTrue(verify._content_signature(self.DEEP).startswith(PREFIXES))


@requires_hypothesis
class SignatureProperty(unittest.TestCase):
    @fuzz()
    @given(st.binary(max_size=3000))
    def test_random_bytes_file_gets_bytes_signature_or_none(self, data):
        p = tmpdir() / "x.prproj"
        p.write_bytes(data)
        out = _hyp.within(10, verify.prproj_signature, p)
        self.assertTrue(out is None or out.startswith(PREFIXES))

    @fuzz()
    @given(st.binary(max_size=3000))
    def test_random_gzip_content_gets_a_signature(self, data):
        p = prproj(tmpdir() / "x.prproj", data)
        out = _hyp.within(10, verify.prproj_signature, p)
        self.assertTrue(out is not None and out.startswith(PREFIXES))

    @fuzz()
    @given(_hyp.hostile_text())
    def test_hostile_text_as_xml(self, text):
        out = _hyp.within(10, verify._content_signature, as_read(text))
        self.assertTrue(out.startswith(PREFIXES))

    @fuzz()
    @given(st.lists(st.tuples(st.sampled_from(["a", "Node", "Properties", "NextID", "MZ.EditLine", "ID", "ClipLoop", "ns:b", "é", ""]),
                              _hyp.hostile_text(), st.integers(0, 3)), max_size=30))
    def test_structured_shallow_xml_with_hostile_text_and_premiere_names(self, parts):
        from xml.sax.saxutils import escape
        xml = "<r>"
        stack = []
        for tag, text, op in parts:
            safe = escape(text).replace("\0", "").replace("\x0b", "")
            if op == 0 and tag:
                xml += "<%s>%s" % (tag, safe)
                stack.append(tag)
            elif op == 1 and stack:
                xml += "</%s>" % stack.pop()
            else:
                xml += safe
        xml += "".join("</%s>" % t for t in reversed(stack)) + "</r>"
        out = _hyp.within(10, verify._content_signature, as_read(xml))
        self.assertTrue(out.startswith(PREFIXES))

    @fuzz()
    @given(st.binary(max_size=500), st.sampled_from([None, "", "c2:abc", "raw:abc", "bytes:abc", "deadbeef", "c2:"]))
    def test_signature_matches_never_raises(self, data, recorded):
        p = tmpdir() / "m.prproj"
        p.write_bytes(data)
        self.assertIsInstance(verify.signature_matches(p, recorded), bool)


if __name__ == "__main__":
    unittest.main()
