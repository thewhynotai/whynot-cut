"""3.0 T6.2: serve/security.py - the token file (user-only), Host/Origin checks, token compare, rate limit, redacting
audit log of the local engine daemon `reel serve`.
Run:  tools/test.sh -p test_serve_security.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home before anything else (see tests/_isolation.py)
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
sys_path = str(SK / "engine" / "reel")
if sys_path not in _sys.path:
    _sys.path.insert(0, sys_path)

from serve import security  # noqa: E402

WIN = os.name == "nt"


def _icacls(path):
    r = subprocess.run(["icacls", str(path)], capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout


def _aces(path):
    """The ACE lines of `icacls <path>` as text, without the path prefix and the summary line."""
    rc, out = _icacls(path)
    assert rc == 0, out
    lines = []
    for raw in out.splitlines():
        line = raw.strip()
        if not line or line.startswith("Successfully processed"):
            continue
        if line.startswith(str(path)):
            line = line[len(str(path)):].strip()
        lines.append(line)
    return lines


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="wnc-sec-"))
        self.addCleanup(shutil.rmtree, self.home, True)


class EngineJson(_Tmp):
    def test_path(self):
        self.assertEqual(security.engine_json_path(self.home), self.home / "bridge" / "engine.json")

    def test_roundtrip_and_fields(self):
        tok = security.make_token()
        p = security.write_engine_json(self.home, port=51234, token=tok, pid=4242, version="3.0.0")
        self.assertEqual(Path(p), security.engine_json_path(self.home))
        d = security.read_engine_json(self.home)
        self.assertEqual((d["port"], d["token"], d["pid"], d["version"]), (51234, tok, 4242, "3.0.0"))
        self.assertEqual(d["protocol"], 4)

    def test_extra_fields_kept(self):
        security.write_engine_json(self.home, port=1, token="c" * 64, pid=1, version="v", started_at="2026-10-12T00:00:00Z")
        self.assertEqual(security.read_engine_json(self.home)["started_at"], "2026-10-12T00:00:00Z")

    def test_read_missing_or_corrupt_is_none(self):
        self.assertIsNone(security.read_engine_json(self.home))
        p = security.engine_json_path(self.home)
        p.parent.mkdir(parents=True)
        p.write_text("{not json", encoding="utf-8")
        self.assertIsNone(security.read_engine_json(self.home))
        p.write_text("[1,2]", encoding="utf-8")
        self.assertIsNone(security.read_engine_json(self.home))

    def test_atomic_no_temp_left_and_overwrite(self):
        security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v")
        security.write_engine_json(self.home, port=2, token="b" * 64, pid=2, version="v")
        self.assertEqual(security.read_engine_json(self.home)["port"], 2)
        self.assertEqual([x.name for x in (self.home / "bridge").iterdir()], ["engine.json"])

    def test_failed_write_keeps_old_file_and_cleans_temp(self):
        security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v")
        real = security.restrict_to_user

        def boom(path):
            raise OSError("acl failed")
        security.restrict_to_user = boom
        try:
            with self.assertRaises(OSError):
                security.write_engine_json(self.home, port=2, token="b" * 64, pid=2, version="v")
        finally:
            security.restrict_to_user = real
        self.assertEqual(security.read_engine_json(self.home)["port"], 1)   # fail closed: the old file is untouched
        self.assertEqual([x.name for x in (self.home / "bridge").iterdir()], ["engine.json"])

    def test_token_shape_enforced(self):
        """Only a 64-lower-hex token is ever written (T4 hardening): a short, upper-case or non-hex one is refused."""
        for bad in ("", "a" * 63, "a" * 65, "A" * 64, "g" * 64, " " + "a" * 63, None, 123):
            with self.subTest(token=bad), self.assertRaises(ValueError):
                security.write_engine_json(self.home, port=1, token=bad, pid=1, version="v")
        self.assertFalse(security.engine_json_path(self.home).exists())

    def test_extra_cannot_override_reserved_keys(self):
        """`protocol` is the only reserved key **extra could reach (the others are named parameters): it is refused."""
        with self.assertRaises(ValueError):
            security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v", protocol=3)
        for key in ("port", "token", "pid", "version"):
            with self.subTest(key=key), self.assertRaises(TypeError):
                security.write_engine_json(self.home, **{"port": 1, "token": "a" * 64, "pid": 1, "version": "v"},
                                           **{key: 2})
        self.assertFalse(security.engine_json_path(self.home).exists())

    def test_temp_file_is_empty_when_first_restricted(self):
        """The ACL goes on before the token is written: the first restrict_to_user call sees an empty temp file."""
        real = security.restrict_to_user
        seen = []

        def spy(path):
            seen.append((Path(path).name, Path(path).stat().st_size))
            real(path)
        security.restrict_to_user = spy
        try:
            security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v")
        finally:
            security.restrict_to_user = real
        self.assertTrue(seen[0][0].endswith(".tmp"), seen)
        self.assertEqual(seen[0][1], 0)
        self.assertEqual(seen[-1][0], "engine.json")

    def test_second_restrict_failure_removes_the_file(self):
        """If the final file cannot be restricted after the replace, it is removed (never left with a wide ACL)."""
        real = security.restrict_to_user
        calls = []

        def second_fails(path):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("acl failed")
            real(path)
        security.restrict_to_user = second_fails
        try:
            with self.assertRaises(OSError):
                security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v")
        finally:
            security.restrict_to_user = real
        self.assertEqual(list((self.home / "bridge").iterdir()), [])

    def test_icacls_output_is_not_decoded(self):
        """icacls output is never decoded (only the return code matters): no text=True, so a non-UTF-8 console
        code page cannot raise."""
        import inspect
        src = inspect.getsource(security.restrict_to_user)
        self.assertNotIn("text=True", src)

    def test_remove_only_if_pid_matches(self):
        security.write_engine_json(self.home, port=1, token="a" * 64, pid=77, version="v")
        self.assertFalse(security.remove_engine_json(self.home, 78))
        self.assertTrue(security.engine_json_path(self.home).exists())
        self.assertTrue(security.remove_engine_json(self.home, 77))
        self.assertFalse(security.engine_json_path(self.home).exists())
        self.assertFalse(security.remove_engine_json(self.home, 77))   # already gone

    def test_remove_corrupt_file_is_left(self):
        p = security.engine_json_path(self.home)
        p.parent.mkdir(parents=True)
        p.write_text("garbage", encoding="utf-8")
        self.assertFalse(security.remove_engine_json(self.home, 1))
        self.assertTrue(p.exists())

    @unittest.skipUnless(WIN, "Windows ACL")
    @unittest.skipUnless(shutil.which("icacls"), "icacls not available")
    def test_windows_acl_user_only(self):
        p = security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v")
        aces = _aces(p)
        user = os.environ.get("USERNAME") or ""
        self.assertEqual(len(aces), 1, aces)                     # exactly one entry
        self.assertTrue(aces[0].lower().startswith(("%s\\%s:" % (os.environ.get("USERDOMAIN", ""), user)).lower())
                        or aces[0].lower().split(":")[0].endswith("\\" + user.lower()), aces)
        self.assertNotIn("(I)", aces[0])                         # inheritance removed
        self.assertNotRegex(aces[0], r"(?i)everyone|users|system|administrators|authenticated")

    @unittest.skipUnless(WIN, "Windows ACL")
    @unittest.skipUnless(shutil.which("icacls"), "icacls not available")
    def test_windows_acl_check_discriminates(self):
        """The ACL parser above would notice an ordinary file: an unrestricted temp file inherits several ACEs."""
        f = self.home / "plain.txt"
        f.write_text("x", encoding="utf-8")
        aces = _aces(f)
        self.assertTrue(len(aces) > 1 or "(I)" in aces[0], aces)

    @unittest.skipUnless(WIN, "Windows ACL")
    @unittest.skipUnless(shutil.which("icacls"), "icacls not available")
    def test_windows_acl_survives_rewrite(self):
        security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v")
        p = security.write_engine_json(self.home, port=2, token="b" * 64, pid=2, version="v")
        aces = _aces(p)
        self.assertEqual(len(aces), 1, aces)
        self.assertNotIn("(I)", aces[0])

    @unittest.skipIf(WIN, "POSIX mode bits")
    def test_posix_mode_0600(self):
        p = security.write_engine_json(self.home, port=1, token="a" * 64, pid=1, version="v")
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)


class Token(unittest.TestCase):
    def test_make_token_is_256_bit_hex_and_random(self):
        a, b = security.make_token(), security.make_token()
        self.assertRegex(a, r"^[0-9a-f]{64}$")
        self.assertNotEqual(a, b)

    def test_token_ok(self):
        t = security.make_token()
        self.assertTrue(security.token_ok(t, t))
        self.assertFalse(security.token_ok(t[:-1] + ("0" if t[-1] != "0" else "1"), t))
        self.assertFalse(security.token_ok(t[:-1], t))
        self.assertFalse(security.token_ok(t + "0", t))
        self.assertFalse(security.token_ok("", t))
        self.assertFalse(security.token_ok(None, t))
        self.assertFalse(security.token_ok(t, ""))
        self.assertFalse(security.token_ok(t, None))
        self.assertFalse(security.token_ok(123, t))
        self.assertFalse(security.token_ok("\u00e9" * 64, t))   # non-ASCII must not raise
        self.assertFalse(security.token_ok("", ""))             # an empty expected token never authenticates

    def test_token_ok_requires_64_lower_hex_on_both_sides(self):
        t = "a" * 64
        self.assertTrue(security.token_ok(t, t))
        for bad in ("A" * 64, "a" * 63, "x" * 64, "a" * 64 + chr(10), " " + "a" * 63):
            with self.subTest(bad=bad):
                self.assertFalse(security.token_ok(bad, bad))       # equal but the wrong shape: never authenticates
                self.assertFalse(security.token_ok(bad, t))
                self.assertFalse(security.token_ok(t, bad))

    def test_uses_compare_digest(self):
        import inspect
        self.assertIn("compare_digest", inspect.getsource(security.token_ok))


class HostOrigin(unittest.TestCase):
    PORT = 51234

    def test_host_table(self):
        P = self.PORT
        ok = [f"127.0.0.1:{P}", f"localhost:{P}", f"LOCALHOST:{P}"]
        bad = [None, "", "127.0.0.1", "localhost", f"127.0.0.1:{P + 1}", f"localhost:{P + 1}", f"[::1]:{P}", "[::1]",
               f"0.0.0.0:{P}", f"127.0.0.2:{P}", f"evil.com:{P}", f"127.0.0.1.evil.com:{P}", f"localhost.evil.com:{P}",
               f"evil.com:{P}@127.0.0.1:{P}", f"127.0.0.1:{P} ", f" 127.0.0.1:{P}", f"127.0.0.1:{P}:{P}",
               f"127.0.0.1:0{P}", f"127.0.0.1:{P}.0", f"127.0.0.1:{P}, evil.com", f"::1:{P}", f"127.0.0.1:"]
        for h in ok:
            self.assertTrue(security.check_host({"Host": h}, P), h)
        for h in bad:
            hd = {} if h is None else {"Host": h}
            self.assertFalse(security.check_host(hd, P), repr(h))

    def test_host_header_name_case_insensitive(self):
        self.assertTrue(security.check_host({"host": "127.0.0.1:%d" % self.PORT}, self.PORT))
        self.assertTrue(security.check_host({"HOST": "127.0.0.1:%d" % self.PORT}, self.PORT))

    def test_host_with_email_message_headers(self):
        from email.message import Message
        m = Message()
        m["Host"] = "127.0.0.1:%d" % self.PORT
        self.assertTrue(security.check_host(m, self.PORT))
        self.assertFalse(security.check_host(Message(), self.PORT))

    def test_origin_absent_allowed(self):
        self.assertTrue(security.check_origin({}))
        self.assertTrue(security.check_origin({"Host": "127.0.0.1:1"}))

    def test_origin_table(self):
        rejected = ["null", "NULL", "", " ", "http://localhost:3000", "https://evil.com", "HTTP://127.0.0.1:51234",
                    "file:///C:/x.html", "chrome-extension://abcdef", "moz-extension://abc",
                    "safari-web-extension://abc", "ws://127.0.0.1:1", "wss://example.com", "ftp://x", "data:text/html,x",
                    "javascript:alert(1)", "about:blank", "uxp:/x", "plugin", "uxpx://a", "xplugin:a",
                    "uxp://ok bad", "uxp://ok\r\nX-Evil: 1", "foo"]
        for o in rejected:
            self.assertFalse(security.check_origin({"Origin": o}), repr(o))
        for o in ["uxp://com.whynot.cut", "UXP://host/panel", "plugin:com.whynot.cut", "plugin://x", "file://"]:
            self.assertTrue(security.check_origin({"Origin": o}), o)
        self.assertTrue(security.check_origin({"origin": "uxp://a"}))     # header name case

    def test_allowed_prefixes_constant_is_listed_as_unmeasured(self):
        self.assertEqual(security.ALLOWED_ORIGIN_PREFIXES, ("uxp://", "plugin:"))
        src = Path(security.__file__).read_text(encoding="utf-8")
        i = src.index("ALLOWED_ORIGIN_PREFIXES =")
        self.assertIn("unmeasured", src[max(0, i - 600):i + 100].lower())

    # --- the measured UXP Origin (spike 0.1.3 / 0.1.4 on Premiere 26.5.2 sent exactly "file://") -----------------
    def test_exact_allowlist_is_only_the_measured_file_origin(self):
        self.assertEqual(tuple(security.ALLOWED_ORIGINS_EXACT), ("file://",))
        src = Path(security.__file__).read_text(encoding="utf-8")
        i = src.index("ALLOWED_ORIGINS_EXACT =")
        near = src[max(0, i - 900):i + 100]
        for cite in ("0.1.4", "26.5.2", "serve-audit.log", '"reason":"file://"'):
            self.assertIn(cite, near)

    def test_uxp_file_origin_is_allowed(self):
        self.assertTrue(security.check_origin({"Origin": "file://"}))
        self.assertIsNone(security.origin_rejection({"Origin": "file://"}))
        self.assertIsNone(security.origin_rejection({"origin": "file://"}))           # header name case
        from email.message import Message
        m = Message()
        m["Origin"] = "file://"
        self.assertTrue(security.check_origin(m))

    def test_every_other_file_form_is_refused(self):
        cases = {
            "file:///x": "origin-browser-scheme", "file:///": "origin-browser-scheme",
            "file:///C:/Users/x/panel.html": "origin-browser-scheme", "file://host": "origin-browser-scheme",
            "file://localhost": "origin-browser-scheme", "file://localhost/": "origin-browser-scheme",
            "file://./": "origin-browser-scheme", "file:": "origin-browser-scheme", "file:/": "origin-browser-scheme",
            "file:///file://": "origin-browser-scheme", "file://file://": "origin-browser-scheme",
            "FILE://": "origin-browser-scheme", "File://": "origin-browser-scheme", "fILE://": "origin-browser-scheme",
            "file://%20": "origin-browser-scheme", "file://?": "origin-browser-scheme",
            "file://#": "origin-browser-scheme",
            "file:// ": "origin-malformed", " file://": "origin-malformed", "file://\t": "origin-malformed",
            "file://\r\n": "origin-malformed", "file://\x00": "origin-malformed", "file:// x": "origin-malformed",
            "file://\u00a0": "origin-malformed", "\ufefffile://": "origin-not-allowed",
            "null": "origin-null", "NULL": "origin-null", "Null": "origin-null",
        }
        for o, why in cases.items():
            self.assertFalse(security.check_origin({"Origin": o}), repr(o))
            self.assertEqual(security.origin_rejection({"Origin": o}), why, repr(o))

    def test_exact_file_origin_repeated_is_refused(self):
        self.assertEqual(security.origin_rejection({"Origin": "file://", "origin": "file://"}), "origin-repeated")

    def test_exact_allowlist_cannot_open_null_or_a_browser_page(self):
        """Even if someone widened the exact list, "null" and file pages with a path stay refused: the exact list is
        an exact compare, never a prefix, and only after the malformed check."""
        old = security.ALLOWED_ORIGINS_EXACT
        security.ALLOWED_ORIGINS_EXACT = ("file://",)
        try:
            for o in ("file:///x", "file://x", "FILE://", "file:// ", "null"):
                self.assertFalse(security.check_origin({"Origin": o}), repr(o))
        finally:
            security.ALLOWED_ORIGINS_EXACT = old

    def test_prefix_allowlist_cannot_open_browser_schemes(self):
        old = security.ALLOWED_ORIGIN_PREFIXES
        security.ALLOWED_ORIGIN_PREFIXES = old + ("http://", "file:", "null")
        try:
            for o in ("http://localhost:1", "file:///x", "null"):
                self.assertFalse(security.check_origin({"Origin": o}), o)
        finally:
            security.ALLOWED_ORIGIN_PREFIXES = old

    def test_origin_rejection_reason(self):
        self.assertIsNone(security.origin_rejection({}))
        self.assertEqual(security.origin_rejection({"Origin": "null"}), "origin-null")
        self.assertEqual(security.origin_rejection({"Origin": "https://a.b"}), "origin-browser-scheme")
        self.assertEqual(security.origin_rejection({"Origin": "zzz://a"}), "origin-not-allowed")


class Limiter(unittest.TestCase):
    def test_burst_then_refill(self):
        now = [100.0]
        rl = security.RateLimiter(2.0, 3, clock=lambda: now[0])
        self.assertEqual([rl.allow() for _ in range(4)], [True, True, True, False])
        now[0] += 0.5                                    # +1 token
        self.assertTrue(rl.allow())
        self.assertFalse(rl.allow())
        now[0] += 100                                    # capped at burst
        self.assertEqual([rl.allow() for _ in range(4)], [True, True, True, False])

    def test_clock_going_backwards_does_not_mint_tokens(self):
        now = [10.0]
        rl = security.RateLimiter(1.0, 1, clock=lambda: now[0])
        self.assertTrue(rl.allow())
        now[0] = 5.0
        self.assertFalse(rl.allow())

    def test_cost_and_validation(self):
        rl = security.RateLimiter(1.0, 5, clock=lambda: 0.0)
        self.assertFalse(rl.allow(6))
        self.assertTrue(rl.allow(5))
        self.assertFalse(rl.allow())
        for bad in ((0, 1), (-1, 1), (1, 0), (1, -2)):
            with self.assertRaises(ValueError):
                security.RateLimiter(*bad)

    def test_real_clock_default(self):
        rl = security.RateLimiter(1000.0, 2)
        self.assertTrue(rl.allow())

    def test_thread_safe_never_exceeds_burst(self):
        rl = security.RateLimiter(0.001, 50, clock=lambda: 0.0)
        got = []

        def run():
            got.extend(rl.allow() for _ in range(40))
        ts = [threading.Thread(target=run) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(got), 50)


class Audit(_Tmp):
    def _log(self, **kw):
        return security.AuditLog(self.home / "logs" / "serve-audit.log", **kw)

    def test_path_helper(self):
        self.assertEqual(security.audit_log_path(self.home), self.home / "logs" / "serve-audit.log")

    def test_json_lines_shape(self):
        a = self._log()
        a.log("connect", peer="127.0.0.1:5555", outcome="ok")
        a.log("command", peer="127.0.0.1:5555", session="s1", action="ping", outcome="rejected", reason="rate")
        rows = [json.loads(x) for x in a.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertRegex(rows[0]["at"], r"^\d{4}-\d\d-\d\dT")
        self.assertEqual((rows[0]["event"], rows[0]["peer"], rows[0]["outcome"]), ("connect", "127.0.0.1:5555", "ok"))
        for k in ("session", "action", "reason"):
            self.assertNotIn(k, rows[0])
        self.assertEqual((rows[1]["session"], rows[1]["action"], rows[1]["reason"]), ("s1", "ping", "rate"))

    def test_origin_is_loggable(self):
        a = self._log()
        a.log("handshake", peer="p", outcome="rejected", reason="origin-not-allowed: zzz://a")
        self.assertIn("zzz://a", a.path.read_text(encoding="utf-8"))

    def test_token_never_in_file_through_every_path(self):
        tok = security.make_token()
        a = self._log(token=tok)
        a.log("handshake", peer="127.0.0.1:%s" % tok, outcome="rejected", reason="bad token %s" % tok)
        a.log("command", peer="p", session=tok, action="x?token=%s" % tok, outcome="ok")
        a.log("command", peer="p", action="Authorization: Bearer " + tok.upper(), outcome="ok")
        a.log("command", peer="p", action="a" + tok + "b" * 400, outcome="ok")
        a.log("command", peer="p", action=tok[:30] + "|" + tok[30:], outcome="ok")   # split: only the exact value is promised
        a.log("origin", peer="p", outcome="x", reason=tok + tok)
        a.log(tok, peer="p", outcome=tok)
        a.log("odd", peer=("tuple", tok), action={"k": tok}, outcome=ValueError(tok))
        text = a.path.read_text(encoding="utf-8")
        self.assertNotIn(tok, text)
        self.assertNotIn(tok.upper(), text)
        self.assertNotRegex(text, r"[0-9a-fA-F]{64}")
        for line in text.splitlines():
            json.loads(line)                                  # still valid JSON after redaction

    def test_unknown_token_value_is_still_redacted_as_64_hex(self):
        a = self._log()                                       # no token registered
        t = security.make_token()
        a.log("x", peer="p", outcome="ok", reason="leaked " + t)
        self.assertNotIn(t, a.path.read_text(encoding="utf-8"))

    def test_non_hex_token_exact_value_redacted_and_set_token_later(self):
        a = self._log()
        a.set_token("S3cret-Value/with+odd\"chars")
        a.log("x", peer="p", outcome="ok", reason='v=S3cret-Value/with+odd"chars!')
        text = a.path.read_text(encoding="utf-8")
        self.assertNotIn("S3cret-Value", text)
        self.assertNotIn("odd", text.split('"reason"')[1])

    def test_redact_function(self):
        t = security.make_token()
        r = security.redact("a " + t + " b", token=t)
        self.assertNotIn(t, r)
        self.assertIn("a ", r)
        self.assertEqual(security.redact("plain", token=None), "plain")
        self.assertEqual(security.redact(None, token=t), "")
        self.assertEqual(security.redact("f" * 200, token=None).count("f"), 0)
        self.assertEqual(security.redact("f" * 63, token=None), "f" * 63)    # shorter than a token: kept

    def test_long_fields_truncated(self):
        a = self._log()
        a.log("x", peer="p", outcome="ok", reason="r" * 10000)
        row = json.loads(a.path.read_text(encoding="utf-8"))
        self.assertLess(len(row["reason"]), 2000)

    def test_newlines_cannot_forge_lines(self):
        a = self._log()
        a.log("x", peer="p", outcome="ok", reason='a\n{"event":"forged"}')
        lines = a.path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["event"], "x")

    def test_rotation(self):
        a = self._log(max_bytes=600, keep=3)
        for i in range(60):
            a.log("e%d" % i, peer="p", outcome="ok", reason="y" * 40)
        names = sorted(x.name for x in a.path.parent.iterdir())
        self.assertEqual(names, ["serve-audit.log", "serve-audit.log.1", "serve-audit.log.2", "serve-audit.log.3"])
        for n in names:
            self.assertLessEqual((a.path.parent / n).stat().st_size, 600 + 300)
        newest = [json.loads(x) for x in a.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(newest[-1]["event"], "e59")
        older = [json.loads(x)["event"] for x in (a.path.parent / "serve-audit.log.1").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(older and int(older[-1][1:]) < int(newest[0]["event"][1:]))

    def test_rotation_keeps_token_out_of_rotated_files(self):
        tok = security.make_token()
        a = self._log(token=tok, max_bytes=500, keep=2)
        for i in range(40):
            a.log("e", peer="p", outcome="ok", reason="t=%s" % tok)
        for f in a.path.parent.iterdir():
            self.assertNotIn(tok, f.read_text(encoding="utf-8"))

    def test_oversize_single_line_still_written(self):
        a = self._log(max_bytes=100, keep=1)
        a.log("x", peer="p", outcome="ok", reason="z" * 500)
        self.assertEqual(json.loads(a.path.read_text(encoding="utf-8").splitlines()[-1])["event"], "x")

    def test_concurrency(self):
        tok = security.make_token()
        a = self._log(token=tok, max_bytes=2000, keep=50)

        def run(n):
            for i in range(50):
                a.log("t%d" % n, peer="p%d" % n, session=str(i), outcome="ok", reason=tok)
        ts = [threading.Thread(target=run, args=(n,)) for n in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        total = 0
        for f in sorted(a.path.parent.iterdir()):
            for line in f.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)                         # no torn / interleaved line
                self.assertNotIn(tok, line)
                total += 1
        self.assertEqual(total, 400)

    def test_bad_args_rejected(self):
        for kw in ({"max_bytes": 0}, {"keep": 0}):
            with self.assertRaises(ValueError):
                self._log(**kw)

    def test_log_never_raises_on_a_field_that_cannot_be_turned_into_text(self):
        class Evil:
            def __str__(self):
                raise RuntimeError("no text for you")
        a = security.AuditLog(self.home / "logs" / "a.log")
        self.assertTrue(a.log("x", peer=Evil(), action=Evil(), outcome="ok", reason=Evil()))
        row = json.loads((self.home / "logs" / "a.log").read_text(encoding="utf-8"))
        self.assertEqual((row["peer"], row["action"], row["reason"]), (security.REDACTED,) * 3)

    def test_log_never_raises_on_io_failure(self):
        """The audit log must not take the daemon down: an unwritable path is swallowed (and reported by return value)."""
        blocker = self.home / "logs"
        blocker.write_text("i am a file, not a directory", encoding="utf-8")
        a = security.AuditLog(blocker / "serve-audit.log")
        self.assertFalse(a.log("x", peer="p", outcome="ok"))


if __name__ == "__main__":
    unittest.main()
