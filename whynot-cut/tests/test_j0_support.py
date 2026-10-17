# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum J test support: the no-live-network guard and shared helpers for every `test_j*.py` file.

The guard is a process audit hook (sys.addaudithook) that is active only while a J test runs (NetGuardCase.setUp
turns it on, tearDown off). While it is on, `socket.connect` to anything but loopback and `getaddrinfo` for anything
but a loopback name raise before a packet leaves the machine: brand_web tests never reach the internet (J10 "No live
network"). Other test files are unaffected. Run:
    <engine python> -m unittest discover -s whynot-cut/tests -p test_j0_support.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import ipaddress
import socket
import sys
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "brand_web"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1", "", None}
_STATE = {"active": 0, "installed": False}


class LiveNetworkBlocked(RuntimeError):
    pass


def _is_loopback(host) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _hook(event, args):
    if not _STATE["active"]:
        return
    if event == "socket.connect":
        addr = args[1]
        host = addr[0] if isinstance(addr, tuple) else addr
        if isinstance(host, (bytes, str)) and not _is_loopback(host if isinstance(host, str) else host.decode()):
            raise LiveNetworkBlocked(f"J tests never use the live network (connect to {host!r})")
    elif event in ("socket.sendto", "socket.sendmsg"):
        addr = args[-1]
        host = addr[0] if isinstance(addr, tuple) and addr else None
        if host is not None and not _is_loopback(host):
            raise LiveNetworkBlocked(f"J tests never use the live network (send to {host!r})")
    elif event in ("socket.gethostbyname", "socket.gethostbyaddr"):
        host = args[0]
        if not _is_loopback(host if isinstance(host, str) else str(host)):
            raise LiveNetworkBlocked(f"J tests never use the live network ({event} {host!r})")
    elif event == "socket.getaddrinfo":
        host = args[0]
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        if not _is_loopback(host):
            raise LiveNetworkBlocked(f"J tests never use the live network (DNS lookup of {host!r})")


if not _STATE["installed"]:
    sys.addaudithook(_hook)
    _STATE["installed"] = True


class NetGuardCase(unittest.TestCase):
    """Base class for every J test: the live-network guard is on for the whole test."""

    def setUp(self):
        super().setUp()
        _STATE["active"] += 1
        self.addCleanup(self._guard_off)

    @staticmethod
    def _guard_off():
        _STATE["active"] -= 1


class FakeClock:
    """A clock and a sleeper that only move when slept: pacing tests read `sleeps`."""

    def __init__(self, t: float = 0.0):
        self.t = t
        self.sleeps = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float):
        self.sleeps.append(round(s, 3))
        self.t += s


class TestNetGuard(NetGuardCase):
    def test_connect_to_internet_address_raises_before_sending(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with self.assertRaises(LiveNetworkBlocked):
                s.connect(("93.184.216.34", 80))
        finally:
            s.close()

    def test_dns_lookup_of_a_public_name_raises(self):
        with self.assertRaises(LiveNetworkBlocked):
            socket.getaddrinfo("example.com", 443)

    def test_loopback_is_allowed(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            c.connect(srv.getsockname())
        finally:
            c.close()
            srv.close()

    def test_gethostbyname_and_udp_send_raise(self):
        with self.assertRaises(LiveNetworkBlocked):
            socket.gethostbyname("example.com")
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            with self.assertRaises(LiveNetworkBlocked):
                u.sendto(b"x", ("8.8.8.8", 53))
        finally:
            u.close()

    def test_every_j_test_class_runs_under_the_guard(self):
        """Structure test (J10 "No live network"): a test class in a test_j*.py file that is not a NetGuardCase would
        run without the guard."""
        import ast
        bad = []
        for f in sorted(Path(__file__).resolve().parent.glob("test_j[0-9]*.py")):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            guarded = {"NetGuardCase"}
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                names = {b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "") for b in node.bases}
                if names & guarded:
                    guarded.add(node.name)
                elif any(n.endswith("TestCase") for n in names) and node.name != "NetGuardCase":
                    bad.append(f"{f.name}:{node.name}")
        self.assertEqual(bad, [])

    def test_guard_is_off_outside_j_tests(self):
        _STATE["active"] -= 1
        try:
            _hook("socket.getaddrinfo", ("example.com", 443, 0, 0, 0))   # no raise while off
        finally:
            _STATE["active"] += 1


if __name__ == "__main__":
    unittest.main()
