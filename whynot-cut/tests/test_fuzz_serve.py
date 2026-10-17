# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Phase 4 Task 48 (L-T10, Addendum L §L4.4): property tests for the daemon's wire parsers.

Targets: serve.messages.validate_message, contract.validate_request / validate_result, serve.ws.parse_http and the
WebSocket frame reader. Property: only our typed error (or a returned error value) comes out; nothing hangs.
Profiles and the Hypothesis install: tests/security/fuzz/_hyp.py. Run:  tools/test.sh -p test_fuzz_serve.py
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402
import asyncio
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE / "security" / "fuzz"))
_sys.path.insert(0, str(HERE.parent / "engine" / "reel"))

import _hyp  # noqa: E402
from _hyp import fuzz, given, requires_hypothesis, st  # noqa: E402

from contract import validator  # noqa: E402
from serve import messages, ws  # noqa: E402


class FakeTransport:
    def abort(self):
        pass

    def get_extra_info(self, name, default=None):
        return ("127.0.0.1", 1) if name == "peername" else default


class FakeWriter:
    def __init__(self):
        self.sent = bytearray()
        self.transport = FakeTransport()
        self._closing = False

    def write(self, data):
        self.sent += data

    async def drain(self):
        pass

    def can_write_eof(self):
        return False

    def close(self):
        self._closing = True

    def is_closing(self):
        return self._closing

    async def wait_closed(self):
        pass

    def get_extra_info(self, name, default=None):
        return None


LOOP = asyncio.new_event_loop()   # one loop for all examples: a loop per example costs more than the parser
asyncio.set_event_loop(LOOP)


def reader(data: bytes) -> asyncio.StreamReader:
    r = asyncio.StreamReader(limit=65536, loop=LOOP)
    r.feed_data(data)
    r.feed_eof()
    return r


def run(coro, seconds=10):
    return LOOP.run_until_complete(asyncio.wait_for(coro, seconds))


def head(data: bytes, timeout=2):
    return run(ws.parse_http(reader(data), peer=("127.0.0.1", 1), timeout=timeout))


def tearDownModule():
    LOOP.close()


@requires_hypothesis
class MessageValidator(unittest.TestCase):
    @fuzz()
    @given(_hyp.json_values())
    def test_validate_message_returns_none_or_a_code_and_never_raises(self, msg):
        out = messages.validate_message(msg)
        self.assertTrue(out is None or (isinstance(out, tuple) and out[0] in ("schema", "unknown_type") and isinstance(out[1], list)))

    @fuzz()
    @given(st.sampled_from(messages.TYPES), _hyp.json_values(), _hyp.hostile_text())
    def test_validate_message_with_a_real_type_and_hostile_fields(self, t, extra, s):
        for msg in ({"type": t}, {"type": t, "id": s}, {"type": t, "id": s, "data": extra}, {"type": t, "message": s, "code": s}):
            out = messages.validate_message(msg)
            self.assertTrue(out is None or out[0] in ("schema", "unknown_type"))

    @fuzz(unit_examples=40, space=_hyp.deep_json_space(1200))
    @given(_hyp.deep_json(1200))
    def test_deeply_nested_message_is_an_error_not_a_crash(self, msg):
        for m in (msg, {"type": "hello", "client": msg}):
            out = _hyp.only_typed(messages.validate_message, (RecursionError,), m, seconds=10)
            # a RecursionError would be a finding: validate_message must answer for any nesting
            self.assertNotIsInstance(out, RecursionError, "deep nesting escapes validate_message")

    @fuzz()
    @given(_hyp.json_values())
    def test_message_id_never_raises(self, msg):
        self.assertTrue(messages.message_id(msg) is None or isinstance(messages.message_id(msg), str))


@requires_hypothesis
class ContractValidator(unittest.TestCase):
    @fuzz()
    @given(_hyp.json_values())
    def test_validate_request_returns_a_list_of_strings(self, req):
        out = validator.validate_request(req)
        self.assertIsInstance(out, list)
        self.assertTrue(all(isinstance(e, str) for e in out))

    @fuzz()
    @given(_hyp.json_values())
    def test_validate_result_returns_a_list_of_strings(self, res):
        out = validator.validate_result(res)
        self.assertIsInstance(out, list)

    @fuzz()
    @given(_hyp.hostile_text(), _hyp.json_values())
    def test_request_envelope_with_an_action_and_hostile_data(self, action, data):
        for req in ({"action": action}, {"action": action, "data": data}, {"version": 1, "action": "ping", "data": data}):
            self.assertIsInstance(validator.validate_request(req), list)
            self.assertIsInstance(validator.validate_result({"ok": True, "action": action, "readback": data}), list)

    @fuzz(unit_examples=40, space=_hyp.deep_json_space(1200))
    @given(_hyp.deep_json(1200))
    def test_deep_nesting_in_a_request_is_an_error_not_a_crash(self, deep):
        for req in (deep, {"action": "ping", "data": deep}):
            out = _hyp.only_typed(validator.validate_request, (RecursionError,), req, seconds=10)
            self.assertNotIsInstance(out, RecursionError, "deep nesting escapes validate_request")


@requires_hypothesis
class HttpHead(unittest.TestCase):
    @fuzz()
    @given(st.binary(max_size=20000))
    def test_random_bytes_only_give_http_error(self, data):
        out = _hyp.only_typed(head, (ws.HttpError,), data)
        self.assertTrue(isinstance(out, (ws.HttpError, ws.Request)))
        if isinstance(out, ws.HttpError):
            self.assertIn(out.status, (400, 408, 431, 414, 505, 501))

    @fuzz()
    @given(st.sampled_from(["GET", "POST", "get", "G\0T", "", "X" * 40]), _hyp.hostile_text(),
           st.sampled_from(["HTTP/1.1", "HTTP/1.0", "HTTP/2", "http/1.1", ""]),
           st.lists(st.tuples(_hyp.hostile_text(), _hyp.hostile_text()), max_size=8))
    def test_structured_head_with_hostile_parts(self, method, target, version, headers):
        raw = ("%s %s %s\r\n" % (method, target.replace("\r", "").replace("\n", ""), version)).encode("utf-8", "surrogatepass")
        for k, v in headers:
            raw += (k + ": " + v + "\r\n").encode("utf-8", "surrogatepass")
        raw += b"\r\n"
        out = _hyp.only_typed(head, (ws.HttpError,), raw)
        self.assertTrue(isinstance(out, (ws.HttpError, ws.Request)))

    def test_head_that_never_ends_times_out_as_408_fast(self):
        async def go():
            r = asyncio.StreamReader(loop=LOOP)
            r.feed_data(b"GET / HTTP/1.1\r\nHost: x")
            try:
                await ws.parse_http(r, peer=("127.0.0.1", 1), timeout=0.3)
            except ws.HttpError as e:
                return e.status
        self.assertEqual(run(go(), 5), 408)

    def test_oversized_head_is_refused(self):
        big = b"GET / HTTP/1.1\r\nHost: x\r\n" + b"X-A: " + b"a" * 100000 + b"\r\n\r\n"
        with self.assertRaises(ws.HttpError):
            head(big)


@requires_hypothesis
class FrameReader(unittest.TestCase):
    def _recv(self, data: bytes, idle=0.4, max_message=4096):
        async def go():
            sock = ws.WebSocket(reader(data), FakeWriter(), max_message=max_message, idle_timeout=idle)
            return await sock.recv()
        return run(go(), 10)

    @fuzz()
    @given(st.binary(max_size=3000))
    def test_random_bytes_into_recv_give_text_or_none_and_never_raise(self, data):
        out = _hyp.only_typed(self._recv, (), data, seconds=10)
        self.assertTrue(out is None or isinstance(out, str))

    @fuzz()
    @given(st.integers(0, 255), st.integers(0, 255), st.binary(max_size=300))
    def test_hostile_frame_heads(self, b0, b1, rest):
        out = self._recv(bytes([b0, b1]) + rest)
        self.assertTrue(out is None or isinstance(out, str))

    @fuzz()
    @given(st.sampled_from([0, 1, 2, 8, 9, 10]), st.booleans(), st.sampled_from([0, 1, 125, 126, 127]),
           st.sampled_from([0, 125, 126, 65535, 65536, 2 ** 31, 2 ** 63 - 1, 2 ** 63, 2 ** 64 - 1]), st.binary(max_size=200))
    def test_length_encodings_never_allocate_past_max_message(self, opcode, fin, len7, ext, body):
        import struct
        head = bytes([(0x80 if fin else 0) | opcode, 0x80 | len7])
        if len7 == 126:
            head += struct.pack(">H", ext & 0xFFFF)
        elif len7 == 127:
            head += struct.pack(">Q", ext)
        import tracemalloc
        tracemalloc.start()
        try:
            out = self._recv(head + b"\0\0\0\0" + body, max_message=4096)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertTrue(out is None or isinstance(out, str))
        self.assertLess(peak, 4 * 2 ** 20, "a claimed length of %d bytes made the frame reader allocate %.1f MB" % (ext, peak / 2 ** 20))

    @fuzz(space=5)
    @given(st.just(1), st.sampled_from([4097, 65535, 65536, 2 ** 31, 2 ** 63 - 1]))
    def test_a_claimed_length_past_the_cap_is_refused_before_a_byte_of_the_body_is_read(self, opcode, claimed):
        """Closes the hole the old test had: its body was tiny, so the reader failed on EOF whether or not the cap existed. Here the
        body really is there (cap + 2 bytes); with the cap the frame is refused with close code 1009 and the body stays unread."""
        import struct
        if claimed < 126:
            raise AssertionError("not a past-the-cap claim")
        if claimed <= 0xFFFF:
            head = bytes([0x80 | opcode, 0x80 | 126]) + struct.pack(">H", claimed)
        else:
            head = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack(">Q", claimed)
        body = b"x" * 4098
        r = reader(head + b"\0\0\0\0" + body)
        asked = []
        real = r.readexactly

        async def spy(n):
            asked.append(n)
            return await real(n)
        r.readexactly = spy

        async def go():
            w = FakeWriter()
            sock = ws.WebSocket(r, w, max_message=4096, idle_timeout=0.4)
            return await sock.recv(), bytes(w.sent)
        out, sent = run(go(), 10)
        self.assertIsNone(out)
        self.assertIn(struct.pack("!H", 1009), sent, "no close 1009 for a claimed length of %d" % claimed)
        self.assertLessEqual(max(asked), 8, "the reader asked for %d bytes of a frame past the cap (claimed %d)" % (max(asked), claimed))

    @fuzz()
    @given(st.text(max_size=200), st.binary(min_size=4, max_size=4))
    def test_a_masked_text_frame_round_trips_or_is_refused(self, text, mask):
        payload = text.encode("utf-8", "surrogatepass")
        if len(payload) > 125:
            return
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        out = self._recv(bytes([0x81, 0x80 | len(payload)]) + mask + masked)
        try:
            payload.decode("utf-8")
            self.assertEqual(out, text)
        except UnicodeDecodeError:
            self.assertIsNone(out)  # invalid UTF-8 closes with 1007

    def test_a_silent_peer_is_dropped_by_the_idle_timeout_fast(self):
        async def go():
            r = asyncio.StreamReader(loop=LOOP)
            sock = ws.WebSocket(r, FakeWriter(), idle_timeout=0.4)
            return await sock.recv()
        self.assertIsNone(run(go(), 5))



# Schemas whose valid-only generator cannot reach VALID_SHARE_MIN, each with the reason (empty today: every schema reaches it).
UNREACHABLE = {}


def _part(action, part):
    """The strategies for one `$defs/<part>` of an action file: (hostile mix, valid only). The ref is resolved against the file
    root: the root itself has only `$defs` and no type, so it would fall back to plain hostile JSON."""
    root = validator.load(action)
    ref = {"$ref": "#/$defs/" + part}
    return _hyp.from_schema(ref, root), _hyp.from_schema(ref, root, hostile=False)


@requires_hypothesis
class SchemaShaped(unittest.TestCase):
    """Documents built from each schema's own shape: they reach the schema's real branches (review of L-T10)."""
    ACTIONS = validator._actions()
    ACTION_KEYS = {a: _hyp.schema_keys(validator.load(a)) for a in ACTIONS}
    ACTION_LITS = {a: _hyp.schema_literals(validator.load(a)) for a in ACTIONS}
    ACTION_ENUMS = {a: _hyp.schema_prop_enums(validator.load(a)) for a in ACTIONS}
    DATA = {a: _part(a, "data") for a in ACTIONS}
    READBACK = {a: _part(a, "readback") for a in ACTIONS if "readback" in validator.load(a).get("$defs", {})}
    FAILURE = {a: _part(a, "readback_failure") for a in ACTIONS if "readback_failure" in validator.load(a).get("$defs", {})}

    def _keyed(self, a):
        return _hyp.doc_from_keys(self.ACTION_KEYS[a], literals=self.ACTION_LITS[a], prop_enums=self.ACTION_ENUMS[a])

    @fuzz()
    @given(st.data())
    def test_every_real_action_with_schema_shaped_data(self, data):
        action = data.draw(st.sampled_from(self.ACTIONS))
        hostile, valid = self.DATA[action]
        doc = data.draw(st.one_of(hostile, valid, valid, self._keyed(action)))
        envelope = {"protocol": 4, "id": "a1", "action": action, "data": doc, "expires_at": "2030-01-01T00:00:00Z"}
        for req in ({"action": action, "data": doc}, {"version": 1, "action": action, "data": doc, "id": "a1"}, envelope):
            out = validator.validate_request(req)
            self.assertTrue(isinstance(out, list) and all(isinstance(e, str) for e in out))
        if not validator.validate(doc, "%s#/$defs/data" % action):
            # valid data in a valid envelope is accepted: the request check must not be stricter than the data schema
            self.assertEqual([], validator.validate_request(envelope), action)

    @fuzz()
    @given(st.data())
    def test_every_real_action_with_schema_shaped_results(self, data):
        action = data.draw(st.sampled_from(sorted(self.READBACK)))
        hostile, valid = self.READBACK[action]
        rb = data.draw(st.one_of(hostile, valid, valid, self._keyed(action)))
        for res in ({"ok": True, "action": action, "readback": rb}, {"ok": False, "action": action, "readback": rb, "error": "x"}):
            self.assertIsInstance(validator.validate_result(res), list)
        if action in self.FAILURE:
            fh, fv = self.FAILURE[action]
            fb = data.draw(st.one_of(fh, fv))
            self.assertIsInstance(validator.validate_result({"ok": False, "action": action, "readback": fb, "error": "x"}), list)
        if not validator.validate(rb, "%s#/$defs/readback" % action):
            ok = validator.validate_result({"ok": True, "action": action, "readback": rb})
            self.assertEqual([], ok, action)

    @fuzz()
    @given(st.data())
    def test_every_session_message_type_with_schema_shaped_fields(self, data):
        t = data.draw(st.sampled_from(messages.TYPES))
        root = validator.load("session")
        ref = {"$ref": "#/$defs/" + t}
        keys = _hyp.schema_keys(root["$defs"][t])
        keyed = _hyp.doc_from_keys(keys, literals=_hyp.schema_literals(root["$defs"][t]), prop_enums=_hyp.schema_prop_enums(root["$defs"][t]))
        valid = _hyp.from_schema(ref, root, hostile=False)
        doc = data.draw(st.one_of(_hyp.from_schema(ref, root).filter(lambda d: isinstance(d, dict)), valid, valid, keyed))
        out = messages.validate_message(dict(doc, type=t))
        self.assertTrue(out is None or (out[0] in ("schema", "unknown_type") and isinstance(out[1], list)))
        out2 = messages.validate_message(doc)  # without the type key it must be refused, never crash
        self.assertTrue(out2 is None or out2[0] in ("schema", "unknown_type"))
        if not validator.validate(doc, "session#/$defs/" + t):
            self.assertIsNone(messages.validate_message(doc), t)

    def test_the_action_list_is_not_empty_and_every_action_has_a_data_schema(self):
        self.assertGreater(len(self.ACTIONS), 20)
        for a in self.ACTIONS:
            self.assertIn("data", validator.load(a).get("$defs", {}), a)

    def _assert_share(self, name, strategy, errors_of):
        ok, drawn, first = _hyp.valid_share(strategy, errors_of)
        self.assertGreater(drawn, 0, name)
        share = ok / drawn
        if name in UNREACHABLE:
            self.assertLess(share, _hyp.VALID_SHARE_MIN, "%s is listed as unreachable but reaches %.0f%%: delete it from UNREACHABLE" % (name, share * 100))
        else:
            self.assertGreaterEqual(share, _hyp.VALID_SHARE_MIN, "%s: only %d of %d generated documents validate (first error: %s)" % (name, ok, drawn, first))

    def test_valid_only_generator_reaches_valid_documents_for_every_action_data_schema(self):
        for a in self.ACTIONS:
            self._assert_share("%s.data" % a, self.DATA[a][1], lambda d, a=a: validator.validate(d, "%s#/$defs/data" % a))

    def test_valid_only_generator_reaches_valid_documents_for_every_readback_schema(self):
        for a, (_, valid) in self.READBACK.items():
            self._assert_share("%s.readback" % a, valid, lambda d, a=a: validator.validate(d, "%s#/$defs/readback" % a))
        for a, (_, valid) in self.FAILURE.items():
            self._assert_share("%s.readback_failure" % a, valid, lambda d, a=a: validator.validate(d, "%s#/$defs/readback_failure" % a))

    def test_valid_only_generator_reaches_valid_documents_for_every_session_message(self):
        root = validator.load("session")
        for t in root["$defs"]:
            self._assert_share("session.%s" % t, _hyp.from_schema({"$ref": "#/$defs/" + t}, root, hostile=False),
                               lambda d, t=t: validator.validate(d, "session#/$defs/" + t))

    def test_unreachable_allowlist_is_documented(self):
        for name, reason in UNREACHABLE.items():
            self.assertTrue(len(reason) > 20, name)


if __name__ == "__main__":
    unittest.main()
