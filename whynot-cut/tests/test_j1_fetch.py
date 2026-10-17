# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Addendum J, J-T1 (Phase 4 Task 31): the website fetcher core, `lib/brand_web/fetch.py` (+ robots.py, netcheck.py).

One test per J2 rule (J2.1 URLs and robots, J2.2 network, proxy and caps, J2.3 TLS through the OS trust store, J2.5 no
telemetry). Every test runs offline on the fixture transport or on connection doubles; the loopback TLS test is the
only socket. Case list: the J track notes (side-session notes, J-TRACK-NOTES.md). Run:
    <engine python> -m unittest discover -s whynot-cut/tests -p test_j1_fetch.py -v
"""
import sys as _sys
_sys.dont_write_bytecode = True
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import gzip
import http.server
import importlib.util
import io
import json
import os
import re
import ssl
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from test_j0_support import ENGINE, FIXTURES, FakeClock, NetGuardCase  # noqa: E402

from lib.brand_web import fetch, netcheck, robots  # noqa: E402

PUB = "93.184.216.34"
CDN = "151.101.1.1"
DNS = {"clinic.test": [PUB], "www.clinic.test": [PUB], "cdn.test": [CDN], "cdn2.test": ["151.101.2.2"],
       "other.test": ["151.101.3.3"], "sites.test": ["151.101.4.4"], "evil.test": ["10.0.0.1"],
       "mixed.test": [PUB, "10.0.0.1"], "blog.clinic.test": [PUB]}


def page(body="<html><body>hi</body></html>", status=200, **headers):
    h = {"content-type": "text/html; charset=utf-8"}
    h.update({k.replace("_", "-"): v for k, v in headers.items()})
    return {"status": status, "headers": h, "body": body}


def moved(to, status=301):
    return {"status": status, "headers": {"location": to}}


def make(routes, start="https://clinic.test/", dns=None, **kw):
    """A fetcher on the fixture transport with a fake clock; returns (fetcher, transport, clock)."""
    t = fetch.FixtureTransport({"dns": dns or DNS, "routes": routes})
    clock = FakeClock()
    kw.setdefault("clock", clock)
    kw.setdefault("sleep", clock.sleep)
    f = fetch.Fetcher(start, transport=t, resolver=t.resolve, **kw)
    return f, t, clock


def sent(t, kind_filter=None):
    """URLs the transport was asked for, robots.txt requests left out unless asked."""
    return [r["url"] for r in t.requests if kind_filter or not r["url"].endswith("/robots.txt")]


# ---------------------------------------------------------------------------------------------- J2.1 URL rules
class TestStartUrl(NetGuardCase):
    def test_bare_host_gets_https(self):
        self.assertEqual(fetch.normalize_start("clinic.test"), ("https://clinic.test/", False))

    def test_typed_http_is_kept_and_flagged(self):
        self.assertEqual(fetch.normalize_start("http://clinic.test/"), ("http://clinic.test/", True))

    def test_whitespace_and_case_of_scheme_and_host(self):
        self.assertEqual(fetch.normalize_start("  HTTPS://Clinic.TEST  ")[0], "https://clinic.test/")

    def test_other_schemes_and_hostless_refused(self):
        for bad in ("ftp://clinic.test/", "file:///etc/passwd", "data:text/html,hi", "javascript:alert(1)",
                    "mailto:a@clinic.test", "https://", "https:///path", ""):
            with self.subTest(bad=bad), self.assertRaises(fetch.FetchStop) as cm:
                fetch.normalize_start(bad)
            self.assertEqual(cm.exception.code, "bad_url")

    def test_credentials_in_url_refused(self):
        with self.assertRaises(fetch.FetchStop) as cm:
            fetch.normalize_start("https://user:pw@clinic.test/")
        self.assertEqual(cm.exception.code, "bad_url")

    def test_idn_host_becomes_punycode(self):
        url, _ = fetch.normalize_start("https://مثال.مصر/")
        self.assertEqual(url, "https://" + "مثال.مصر".encode("idna").decode() + "/")

    def test_invalid_idn_refused_not_crash(self):
        with self.assertRaises(fetch.FetchStop) as cm:
            fetch.normalize_start("https://" + "a" * 64 + ".test/")
        self.assertEqual(cm.exception.code, "bad_url")

    def test_fragment_dropped(self):
        self.assertEqual(fetch.normalize_start("clinic.test/#top")[0], "https://clinic.test/")


class TestScope(NetGuardCase):
    def test_twin_hosts_are_the_start_site(self):
        s = fetch.Scope("https://clinic.test/")
        self.assertTrue(s.page_ok("https://www.clinic.test/about")[0])
        s2 = fetch.Scope("https://www.clinic.test/")
        self.assertTrue(s2.page_ok("https://clinic.test/about")[0])

    def test_lookalike_and_sub_domains_are_other_sites(self):
        s = fetch.Scope("https://clinic.test/")
        for u in ("https://blog.clinic.test/", "https://clinic.test.evil.net/", "https://xclinic.test/",
                  "https://clinic.testx/", "https://www.www.clinic.test/"):
            with self.subTest(u=u):
                ok, why = s.page_ok(u)
                self.assertFalse(ok)
                self.assertEqual(why, "offsite")

    def test_path_scope_on_segment_boundary(self):
        s = fetch.Scope("https://sites.test/view/x")
        self.assertTrue(s.page_ok("https://sites.test/view/x")[0])
        self.assertTrue(s.page_ok("https://sites.test/view/x/about")[0])
        self.assertEqual(s.page_ok("https://sites.test/view/xyz"), (False, "out_of_scope"))
        self.assertEqual(s.page_ok("https://sites.test/view/other"), (False, "out_of_scope"))
        self.assertEqual(s.page_ok("https://sites.test/"), (False, "out_of_scope"))

    def test_hreflang_alternate_on_same_host_allowed_outside_path(self):
        s = fetch.Scope("https://sites.test/view/x")
        self.assertTrue(s.page_ok("https://sites.test/view/x-en", alternate=True)[0])
        self.assertEqual(s.page_ok("https://other.test/view/x", alternate=True), (False, "offsite"))

    def test_ports(self):
        s = fetch.Scope("https://clinic.test:8443/")
        self.assertTrue(s.page_ok("https://clinic.test:8443/a")[0])
        self.assertTrue(s.page_ok("https://www.clinic.test:8443/a")[0])
        self.assertEqual(s.page_ok("https://clinic.test:9000/a"), (False, "port"))
        self.assertEqual(s.page_ok("https://clinic.test/a"), (False, "port"))
        self.assertEqual(s.resource_ok("https://cdn.test:8443/a.css"), (False, "port"))
        self.assertTrue(s.resource_ok("https://cdn.test:443/a.css")[0])
        self.assertTrue(s.resource_ok("https://cdn.test/a.css")[0])
        s2 = fetch.Scope("https://clinic.test/")
        self.assertEqual(s2.page_ok("https://clinic.test:8443/"), (False, "port"))

    def test_downgrade_refused_upgrade_allowed(self):
        s = fetch.Scope("https://clinic.test/")
        self.assertEqual(s.page_ok("http://clinic.test/a"), (False, "downgrade"))
        self.assertEqual(s.resource_ok("http://cdn.test/a.css"), (False, "downgrade"))
        h = fetch.Scope("http://clinic.test/")
        self.assertTrue(h.page_ok("https://clinic.test/a")[0])
        self.assertTrue(h.page_ok("http://clinic.test/a")[0])

    def test_other_schemes_refused_for_resources(self):
        s = fetch.Scope("https://clinic.test/")
        for u in ("file:///c:/x.png", "data:image/png;base64,AAAA", "ftp://cdn.test/a.css", "javascript:x"):
            with self.subTest(u=u):
                self.assertEqual(s.resource_ok(u), (False, "scheme"))

    def test_same_host_only_refuses_other_hosts_for_resources(self):
        s = fetch.Scope("https://clinic.test/", same_host_only=True)
        self.assertEqual(s.resource_ok("https://cdn.test/a.css"), (False, "same_host_only"))
        self.assertTrue(s.resource_ok("https://www.clinic.test/a.css")[0])


# --------------------------------------------------------------------------------------------- J2.2 addresses
class TestNetcheck(NetGuardCase):
    BAD = ["127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
           "224.0.0.1", "255.255.255.255", "192.0.2.10", "::1", "::", "fe80::1", "fc00::1", "::ffff:10.0.0.1",
           "::ffff:127.0.0.1", "2002:a00:1::", "64:ff9b::a00:1", "::10.0.0.1", "ff02::1",
           # Teredo: server 65.54.227.120, client 10.0.0.1 (obfuscated as ~ip in the last 32 bits)
           "2001:0:4136:e378:8000:63bf:f5ff:fffe"]
    GOOD = [PUB, CDN, "8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8", "2002:808:808::"]

    def test_private_and_special_addresses_refused(self):
        for ip in self.BAD:
            with self.subTest(ip=ip):
                self.assertFalse(netcheck.ip_ok(ip))

    def test_global_addresses_allowed(self):
        for ip in self.GOOD:
            with self.subTest(ip=ip):
                self.assertTrue(netcheck.ip_ok(ip))

    def test_garbage_is_not_ok(self):
        self.assertFalse(netcheck.ip_ok("not-an-ip"))
        self.assertFalse(netcheck.ip_ok(""))

    def test_odd_numeric_hosts_are_bad(self):
        for h in ("2130706433", "0x7f000001", "0177.0.0.1", "127.1", "0x7f.0.0.1", "1.2.3"):
            with self.subTest(h=h):
                self.assertEqual(netcheck.classify_host(h)[0], "bad")
        self.assertEqual(netcheck.classify_host("127.0.0.1"), ("ip", "127.0.0.1"))
        self.assertEqual(netcheck.classify_host("[::1]"), ("ip", "::1"))
        self.assertEqual(netcheck.classify_host("clinic.test"), ("name", "clinic.test"))
        self.assertEqual(netcheck.classify_host("1clinic.test"), ("name", "1clinic.test"))


class TestAddressRules(NetGuardCase):
    def test_literal_private_start_refused_without_request(self):
        for start in ("https://127.0.0.1/", "https://[::1]/", "https://[::ffff:10.0.0.1]/", "http://169.254.169.254/",
                      "https://[2002:a00:1::]/"):
            with self.subTest(start=start):
                f, t, _ = make({}, start=start)
                with self.assertRaises(fetch.FetchStop) as cm:
                    f.fetch_home()
                self.assertEqual(cm.exception.code, "private_address")
                self.assertEqual(t.requests, [])

    def test_odd_numeric_start_refused_before_any_request(self):
        for start in ("http://2130706433/", "https://0x7f000001/", "https://127.1/"):
            with self.subTest(start=start), self.assertRaises(fetch.FetchStop) as cm:
                make({}, start=start)          # refused when the start URL is read: no fetcher, so no request
            self.assertEqual(cm.exception.code, "bad_url")

    def test_name_resolving_to_any_private_address_refused(self):
        f, t, _ = make({}, start="https://mixed.test/")
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "private_address")
        self.assertEqual(t.requests, [])

    def test_connection_goes_to_the_checked_ip(self):
        f, t, _ = make({"https://clinic.test/": page()})
        f.fetch_home()
        self.assertEqual({r["ip"] for r in t.requests}, {PUB})

    def test_redirect_to_private_host_refused(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://cdn.test/a.png": moved("https://evil.test/a.png"),
                        "https://cdn.test/b.png": moved("https://10.0.0.1/b.png"),
                        "https://cdn.test/c.png": moved("https://[::ffff:192.168.0.1]/c.png")})
        f.fetch_home()
        for u in ("https://cdn.test/a.png", "https://cdn.test/b.png", "https://cdn.test/c.png"):
            with self.subTest(u=u):
                r = f.fetch(u, "logo")
                self.assertEqual((r.outcome, r.reason), ("refused", "private_address"))
        self.assertFalse(any("evil.test" in u or "10.0.0.1" in u or "192.168" in u for u in sent(t, True)))

    def test_sub_resource_on_private_host_refused(self):
        f, t, _ = make({"https://clinic.test/": page()})
        f.fetch_home()
        r = f.fetch("https://evil.test/x.css", "css")
        self.assertEqual((r.outcome, r.reason), ("refused", "private_address"))

    def test_unresolvable_home_is_network(self):
        f, t, _ = make({}, start="https://nowhere.test/")
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "network")

    def test_unresolvable_resource_is_refused_unreachable(self):
        f, t, _ = make({"https://clinic.test/": page()})
        f.fetch_home()
        r = f.fetch("https://nowhere.test/a.css", "css")
        self.assertEqual((r.outcome, r.reason), ("error", "unreachable"))


# ------------------------------------------------------------------------------------------------- robots.txt
class TestRobotsParser(NetGuardCase):
    def test_longest_match_wins(self):
        r = robots.parse("User-agent: *\nDisallow: /a\nAllow: /a/b\n")
        self.assertTrue(r.allowed("/a/b/c"))
        self.assertFalse(r.allowed("/a/c"))
        self.assertTrue(r.allowed("/b"))

    def test_tie_goes_to_allow(self):
        r = robots.parse("User-agent: *\nDisallow: /page\nAllow: /page\n")
        self.assertTrue(r.allowed("/page"))
        r2 = robots.parse("User-agent: *\nDisallow: /*.php\nAllow: /a.php\n")   # both 6 octets
        self.assertTrue(r2.allowed("/a.php"))

    def test_wildcard_and_end_anchor(self):
        r = robots.parse("User-agent: *\nDisallow: /*.pdf$\nDisallow: /private*/x\n")
        self.assertFalse(r.allowed("/doc/a.pdf"))
        self.assertTrue(r.allowed("/doc/a.pdf?y=1"))
        self.assertTrue(r.allowed("/doc/a.pdfx"))
        self.assertFalse(r.allowed("/private-area/x"))
        self.assertTrue(r.allowed("/private-area/y"))

    def test_our_group_beats_star_and_groups_merge(self):
        txt = ("User-agent: *\nDisallow: /\n\n"
               "User-agent: whynotcut\nDisallow: /a\n\n"
               "User-agent: Other\nUser-agent: WhyNotCut\nDisallow: /b\n")
        r = robots.parse(txt)
        self.assertTrue(r.allowed("/c"))
        self.assertFalse(r.allowed("/a"))
        self.assertFalse(r.allowed("/b"))

    def test_star_group_used_when_ours_absent(self):
        r = robots.parse("User-agent: Googlebot\nDisallow: /\n\nUser-agent: *\nDisallow: /x\n")
        self.assertFalse(r.allowed("/x"))
        self.assertTrue(r.allowed("/y"))

    def test_no_matching_group_allows_all(self):
        self.assertTrue(robots.parse("User-agent: Googlebot\nDisallow: /\n").allowed("/"))

    def test_empty_disallow_is_no_rule(self):
        self.assertTrue(robots.parse("User-agent: *\nDisallow:\n").allowed("/anything"))

    def test_bom_crlf_comments_tabs(self):
        r = robots.parse("\ufeffUser-Agent:\t*  # all\r\nDisallow:\t/x # no\r\n\r\n")
        self.assertFalse(r.allowed("/x"))
        self.assertTrue(r.allowed("/y"))

    def test_rules_before_any_user_agent_ignored(self):
        self.assertTrue(robots.parse("Disallow: /\nUser-agent: *\nAllow: /\n").allowed("/a"))

    def test_arabic_path_matches_encoded_and_raw(self):
        r = robots.parse("User-agent: *\nDisallow: /عن\n")
        self.assertFalse(r.allowed("/%D8%B9%D9%86/team"))
        r2 = robots.parse("User-agent: *\nDisallow: /%d8%b9%d9%86\n")
        self.assertFalse(r2.allowed("/%D8%B9%D9%86"))

    def test_robots_txt_itself_always_allowed(self):
        self.assertTrue(robots.parse("User-agent: *\nDisallow: /\n").allowed("/robots.txt"))

    def test_crawl_delay(self):
        self.assertEqual(robots.parse("User-agent: *\nCrawl-delay: 3\n").crawl_delay, 3.0)
        self.assertEqual(robots.parse("User-agent: *\nCrawl-delay: 2.5\n").crawl_delay, 2.5)
        self.assertIsNone(robots.parse("User-agent: *\nCrawl-delay: soon\n").crawl_delay)
        self.assertIsNone(robots.parse("User-agent: *\nCrawl-delay: -4\n").crawl_delay)

    def test_query_is_part_of_the_match(self):
        r = robots.parse("User-agent: *\nDisallow: /*?s=\n")
        self.assertFalse(r.allowed("/search?s=x"))
        self.assertTrue(r.allowed("/search"))


class TestRobotsFetch(NetGuardCase):
    def _home(self, robots_route, extra=None):
        routes = {"https://clinic.test/": page(), "https://clinic.test/about": page()}
        if robots_route is not None:
            routes["https://clinic.test/robots.txt"] = robots_route
        routes.update(extra or {})
        return make(routes)

    def test_4xx_allows_everything(self):
        for st in (404, 401, 403, 410):
            with self.subTest(st=st):
                f, t, _ = self._home({"status": st, "headers": {}, "body": "User-agent: *\nDisallow: /\n"})
                self.assertEqual(f.fetch_home().outcome, "ok")

    def test_missing_robots_allows(self):
        f, t, _ = self._home(None)
        self.assertEqual(f.fetch_home().outcome, "ok")

    def test_5xx_denies_the_host_network_message(self):
        f, t, _ = self._home({"status": 503, "headers": {}, "body": ""})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "network")
        self.assertEqual(sent(t), [])

    def test_unreachable_robots_denies(self):
        f, t, _ = self._home({"raise": "reset"})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "network")

    def test_home_disallowed_stops_with_the_site_message(self):
        f, t, _ = self._home(page("User-agent: *\nDisallow: /\n", content_type="text/plain"))
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "refused_by_site")
        self.assertIn("الموقع طالب إن البرامج ما تقراهوش", cm.exception.message_ar)
        self.assertEqual(sent(t), [])

    def test_other_disallowed_page_skipped_and_logged(self):
        f, t, _ = self._home(page("User-agent: *\nDisallow: /about\n", content_type="text/plain"))
        f.fetch_home()
        r = f.fetch("https://clinic.test/about", "page")
        self.assertEqual((r.outcome, r.reason), ("refused", "robots"))
        self.assertNotIn("https://clinic.test/about", sent(t))

    def test_robots_redirect_within_site_followed(self):
        f, t, _ = self._home(moved("https://www.clinic.test/robots.txt"),
                             {"https://www.clinic.test/robots.txt": page("User-agent: *\nDisallow: /about\n")})
        f.fetch_home()
        self.assertEqual(f.fetch("https://clinic.test/about", "page").reason, "robots")

    def test_robots_redirect_to_other_host_is_unreachable(self):
        f, t, _ = self._home(moved("https://other.test/robots.txt"),
                             {"https://other.test/robots.txt": page("User-agent: *\nAllow: /\n")})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "network")
        self.assertNotIn("https://other.test/robots.txt", sent(t, True))

    def test_only_first_500_kib_read(self):
        body = "User-agent: *\n" + ("# filler line\n" * 40000) + "Disallow: /\n"
        self.assertGreater(len(body.encode()), 500 * 1024)
        f, t, _ = self._home(page(body, content_type="text/plain"))
        self.assertEqual(f.fetch_home().outcome, "ok")

    def test_crawl_delay_paces_the_host(self):
        f, t, clock = self._home(page("User-agent: *\nCrawl-delay: 3\n"))
        f.fetch_home()
        f.fetch("https://clinic.test/about", "page")
        self.assertEqual(clock.sleeps, [3.0, 3.0])

    def test_crawl_delay_capped_at_10(self):
        f, t, clock = self._home(page("User-agent: *\nCrawl-delay: 60\n"))
        f.fetch_home()
        self.assertEqual(clock.sleeps, [10.0])

    def test_robots_applies_to_sub_resource_hosts(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://cdn.test/robots.txt": page("User-agent: *\nDisallow: /private/\n"),
                        "https://cdn.test/private/a.css": page("a{}", content_type="text/css")})
        f.fetch_home()
        r = f.fetch("https://cdn.test/private/a.css", "css")
        self.assertEqual((r.outcome, r.reason), ("refused", "robots"))
        self.assertNotIn("https://cdn.test/private/a.css", sent(t))

    def test_robots_fetched_once_per_host(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/a": page(), "https://clinic.test/b": page()})
        f.fetch_home()
        f.fetch("https://clinic.test/a", "page")
        f.fetch("https://clinic.test/b", "page")
        self.assertEqual([u for u in sent(t, True) if u.endswith("robots.txt")], ["https://clinic.test/robots.txt"])

    def test_certificate_failure_on_robots_stops_the_host_as_certificate(self):
        f, t, _ = self._home({"raise": "certificate"})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "certificate")
        self.assertIn("جهازك ما قدرش يتأكد من شهادة أمان الموقع", cm.exception.message_ar)

    def test_pinned_font_source_skips_robots(self):
        url = "https://raw.githubusercontent.com/google/fonts/abc123/ofl/x/X.ttf"
        f, t, _ = make({"https://clinic.test/": page(), url: {"status": 200, "headers": {}, "body": "FONT"},
                        "https://raw.githubusercontent.com/robots.txt": page("User-agent: *\nDisallow: /\n")},
                       dns=dict(DNS, **{"raw.githubusercontent.com": ["185.199.108.133"]}))
        f.fetch_home()
        r = f.fetch(url, "font", pinned=True)
        self.assertEqual(r.outcome, "ok")
        self.assertNotIn("https://raw.githubusercontent.com/robots.txt", sent(t, True))

    def test_pinned_flag_is_ignored_for_other_hosts(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://cdn.test/robots.txt": page("User-agent: *\nDisallow: /\n"),
                        "https://cdn.test/x.ttf": {"status": 200, "headers": {}, "body": "FONT"}})
        f.fetch_home()
        self.assertEqual(f.fetch("https://cdn.test/x.ttf", "font", pinned=True).reason, "robots")


# -------------------------------------------------------------------------------------------- scope in a run
class TestRunScope(NetGuardCase):
    def test_off_site_page_not_fetched_and_listed(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://other.test/": page()})
        f.fetch_home()
        r = f.fetch("https://other.test/", "page")
        self.assertEqual((r.outcome, r.reason), ("refused", "offsite"))
        self.assertNotIn("https://other.test/", sent(t, True))
        self.assertIn("https://other.test/", f.external_links)

    def test_home_redirect_off_site_asks(self):
        f, t, _ = make({"https://clinic.test/": moved("https://other.test/home")})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "offsite_redirect")
        self.assertEqual(cm.exception.url, "https://other.test/home")
        self.assertIn("الموقع بيحوّل على", cm.exception.message_ar)
        self.assertNotIn("https://other.test/home", sent(t, True))

    def test_home_redirect_to_twin_or_upgrade_followed(self):
        f, t, _ = make({"https://clinic.test/": moved("https://www.clinic.test/"),
                        "https://www.clinic.test/": page()})
        r = f.fetch_home()
        self.assertEqual((r.outcome, r.final_url), ("ok", "https://www.clinic.test/"))
        f2, t2, _ = make({"http://clinic.test/": moved("https://clinic.test/"), "https://clinic.test/": page()},
                         start="http://clinic.test/")
        self.assertEqual(f2.fetch_home().final_url, "https://clinic.test/")

    def test_page_redirect_off_site_refused(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/book": moved("https://other.test/b")})
        f.fetch_home()
        r = f.fetch("https://clinic.test/book", "page")
        self.assertEqual((r.outcome, r.reason), ("refused", "offsite_redirect"))
        self.assertNotIn("https://other.test/b", sent(t, True))

    def test_redirect_downgrade_and_other_schemes_refused(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://clinic.test/a": moved("http://clinic.test/a"),
                        "https://cdn.test/b.css": moved("file:///etc/passwd"),
                        "https://cdn.test/c.css": moved("data:text/css,a{}"),
                        "https://cdn.test/d.css": moved("ftp://cdn.test/d.css")})
        f.fetch_home()
        self.assertEqual(f.fetch("https://clinic.test/a", "page").reason, "downgrade")
        for u in ("https://cdn.test/b.css", "https://cdn.test/c.css", "https://cdn.test/d.css"):
            with self.subTest(u=u):
                self.assertEqual(f.fetch(u, "css").reason, "scheme")

    def test_home_redirect_downgrade_stops(self):
        f, t, _ = make({"https://clinic.test/": moved("http://clinic.test/")})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "downgrade")

    def test_redirect_loop_stopped(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/a": moved("/b"),
                        "https://clinic.test/b": moved("/a")})
        f.fetch_home()
        r = f.fetch("https://clinic.test/a", "page")
        self.assertEqual((r.outcome, r.reason), ("refused", "redirects"))
        self.assertLessEqual(len([u for u in sent(t) if u.endswith(("/a", "/b"))]), 6)

    def test_six_hop_chain_stopped_five_followed(self):
        routes = {"https://clinic.test/": page()}
        for i in range(6):
            routes[f"https://clinic.test/r{i}"] = moved(f"/r{i + 1}")
        routes["https://clinic.test/r6"] = page()
        f, t, _ = make(routes)
        f.fetch_home()
        self.assertEqual(f.fetch("https://clinic.test/r0", "page").reason, "redirects")
        routes2 = dict(routes)
        routes2["https://clinic.test/r5"] = page()
        f2, _, _ = make(routes2)
        f2.fetch_home()
        self.assertEqual(f2.fetch("https://clinic.test/r0", "page").outcome, "ok")

    def test_sub_resource_redirect_to_other_cdn_followed_with_its_robots(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://cdn.test/a.css": moved("https://cdn2.test/a.css"),
                        "https://cdn2.test/a.css": page("a{}", content_type="text/css")})
        f.fetch_home()
        self.assertEqual(f.fetch("https://cdn.test/a.css", "css").outcome, "ok")
        self.assertIn("https://cdn2.test/robots.txt", sent(t, True))

    def test_sub_resource_fetched_once_never_crawled(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://cdn.test/a.css": page("a{}", content_type="text/css")})
        f.fetch_home()
        r1 = f.fetch("https://cdn.test/a.css", "css")
        r2 = f.fetch("https://cdn.test/a.css#x", "css")
        self.assertEqual(r1.sha256, r2.sha256)
        self.assertEqual(sent(t).count("https://cdn.test/a.css"), 1)

    def test_depth_limit(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://cdn.test/a.css": page("a{}", content_type="text/css")})
        f.fetch_home()
        self.assertEqual(f.fetch("https://cdn.test/a.css", "css", depth=2).outcome, "ok")
        f2, t2, _ = make({"https://clinic.test/": page()})
        f2.fetch_home()
        self.assertEqual(f2.fetch("https://cdn.test/a.css", "css", depth=3).reason, "depth")

    def test_page_kind_only_for_start_site(self):
        f, t, _ = make({"https://clinic.test/": page()})
        f.fetch_home()
        self.assertEqual(f.fetch("https://cdn.test/x.html", "page").reason, "offsite")

    def test_hosts_read_recorded(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://cdn.test/a.css": page("a{}", content_type="text/css")})
        f.fetch_home()
        f.fetch("https://cdn.test/a.css", "css")
        self.assertEqual(sorted(f.hosts_read), ["cdn.test", "clinic.test"])

    def test_arabic_path_requested_percent_encoded(self):
        enc = "https://clinic.test/%D8%B9%D9%86-%D8%A7%D9%84%D8%B9%D9%8A%D8%A7%D8%AF%D8%A9"
        f, t, _ = make({"https://clinic.test/": page(), enc: page()})
        f.fetch_home()
        r = f.fetch("https://clinic.test/عن-العيادة", "page")
        self.assertEqual(r.outcome, "ok")
        self.assertIn(enc, sent(t))

    def test_unknown_kind_is_a_programming_error(self):
        f, t, _ = make({"https://clinic.test/": page()})
        with self.assertRaises(ValueError):
            f.fetch("https://clinic.test/", "script")


# ----------------------------------------------------------------------------------------------------- caps
class TestCaps(NetGuardCase):
    def test_cap_table_matches_the_spec(self):
        c = fetch.CAPS
        self.assertEqual((c["pages_default"], c["pages_max"]), (6, 10))
        self.assertEqual(c["page_bytes"], 3_000_000)
        self.assertEqual((c["css_bytes"], c["css_count"]), (2_000_000, 30))
        self.assertEqual((c["image_bytes"], c["image_pixels"], c["logo_count"], c["photo_count"]),
                         (15_000_000, 50_000_000, 30, 20))
        self.assertEqual(c["font_bytes"], 8_000_000)
        self.assertEqual(c["robots_bytes"], 500 * 1024)
        self.assertEqual((c["run_bytes"], c["run_seconds"]), (150_000_000, 180))
        self.assertEqual((c["connect_timeout"], c["read_timeout"]), (10, 20))
        self.assertEqual((c["host_gap"], c["crawl_delay_max"], c["redirects"], c["depth"]), (1.0, 10.0, 5, 2))

    def test_max_pages_default_and_hard_limit(self):
        self.assertEqual(make({})[0].max_pages, 6)
        self.assertEqual(make({}, max_pages=50)[0].max_pages, 10)
        self.assertEqual(make({}, max_pages=0)[0].max_pages, 1)

    def test_page_count_cap(self):
        routes = {"https://clinic.test/": page()}
        routes.update({f"https://clinic.test/p{i}": page() for i in range(3)})
        f, t, _ = make(routes, max_pages=2)
        f.fetch_home()
        self.assertEqual(f.fetch("https://clinic.test/p0", "page").outcome, "ok")
        r = f.fetch("https://clinic.test/p1", "page")
        self.assertEqual((r.outcome, r.reason), ("cap", "pages"))
        self.assertNotIn("https://clinic.test/p1", sent(t))

    def test_refusal_before_any_request_costs_no_page_budget(self):
        routes = {"https://clinic.test/": page(), "https://clinic.test/a": page(),
                  "https://clinic.test/robots.txt": page("User-agent: *\nDisallow: /private\n")}
        f, t, _ = make(routes, max_pages=2)
        f.fetch_home()
        self.assertEqual(f.fetch("https://clinic.test/private/x", "page").reason, "robots")
        self.assertEqual(f.fetch("https://evil.test/", "page").reason, "offsite")
        self.assertEqual(f.fetch("https://clinic.test/a", "page").outcome, "ok")

    def test_size_caps_by_kind(self):
        routes = {"https://clinic.test/": page(),
                  "https://clinic.test/big": page("x" * 101),
                  "https://cdn.test/big.css": page("x" * 101, content_type="text/css"),
                  "https://cdn.test/big.png": {"status": 200, "headers": {}, "body": "x" * 101},
                  "https://cdn.test/big2.png": {"status": 200, "headers": {}, "body": "x" * 101},
                  "https://cdn.test/big.ttf": {"status": 200, "headers": {}, "body": "x" * 101}}
        f, t, _ = make(routes, caps={"page_bytes": 100, "css_bytes": 100, "image_bytes": 100, "font_bytes": 100})
        f.fetch_home()
        for url, kind, cap in (("https://clinic.test/big", "page", "page_bytes"),
                               ("https://cdn.test/big.css", "css", "css_bytes"),
                               ("https://cdn.test/big.png", "logo", "image_bytes"),
                               ("https://cdn.test/big2.png", "photo", "image_bytes"),
                               ("https://cdn.test/big.ttf", "font", "font_bytes")):
            with self.subTest(kind=kind):
                r = f.fetch(url, kind)
                self.assertEqual((r.outcome, r.reason, r.body), ("cap", cap, None))

    def test_content_length_over_cap_refused_before_reading(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://cdn.test/a.png": {"status": 200, "headers": {"content-length": "999999999"},
                                                   "body": "tiny"}})
        f.fetch_home()
        r = f.fetch("https://cdn.test/a.png", "logo")
        self.assertEqual((r.outcome, r.reason), ("cap", "image_bytes"))
        self.assertEqual(t.read_bytes.get("https://cdn.test/a.png", 0), 0)

    def test_count_caps_by_kind(self):
        routes = {"https://clinic.test/": page()}
        for i in range(3):
            routes[f"https://cdn.test/{i}.css"] = page("a{}", content_type="text/css")
            routes[f"https://cdn.test/{i}.png"] = {"status": 200, "headers": {}, "body": "P"}
        f, t, _ = make(routes, caps={"css_count": 2, "logo_count": 2, "photo_count": 1})
        f.fetch_home()
        self.assertEqual([f.fetch(f"https://cdn.test/{i}.css", "css").outcome for i in range(3)], ["ok", "ok", "cap"])
        self.assertEqual(f.fetch("https://cdn.test/2.css", "css").reason, "css_count")
        self.assertEqual([f.fetch(f"https://cdn.test/{i}.png", "logo").outcome for i in range(3)], ["ok", "ok", "cap"])
        f2, _, _ = make(routes, caps={"photo_count": 1})
        f2.fetch_home()
        self.assertEqual([f2.fetch(f"https://cdn.test/{i}.png", "photo").reason for i in range(2)], ["", "photo_count"])

    def test_run_bytes_cap_stops_the_run(self):
        routes = {"https://clinic.test/": page("x" * 60), "https://clinic.test/a": page("y" * 60),
                  "https://clinic.test/b": page("z" * 10)}
        f, t, _ = make(routes, caps={"run_bytes": 100})
        f.fetch_home()
        r = f.fetch("https://clinic.test/a", "page")
        self.assertEqual((r.outcome, r.reason), ("cap", "run_bytes"))
        self.assertEqual(f.stopped, "run_bytes")
        r2 = f.fetch("https://clinic.test/b", "page")
        self.assertEqual((r2.outcome, r2.reason), ("stopped", "run_bytes"))
        self.assertNotIn("https://clinic.test/b", sent(t))

    def test_run_seconds_cap_before_request(self):
        f, t, clock = make({"https://clinic.test/": page(), "https://clinic.test/a": page()})
        f.fetch_home()
        clock.t += 181
        r = f.fetch("https://clinic.test/a", "page")
        self.assertEqual((r.outcome, r.reason), ("stopped", "run_seconds"))
        self.assertEqual(f.stopped, "run_seconds")

    def test_run_seconds_cap_during_a_trickling_read(self):
        clock = FakeClock()

        class Trickle(io.RawIOBase):
            def read(self, n=-1):
                clock.t += 50
                return b"x"
        base = fetch.FixtureTransport({"dns": DNS, "routes": {"https://clinic.test/": page()}})

        class T:
            requests = base.requests

            def resolve(self, host, port):
                return base.resolve(host, port)

            def send(self, method, url, headers, ip, connect_timeout, read_timeout, deadline=None):
                if url.endswith("/slow"):
                    return fetch.RawResponse(200, {"content-type": "text/html"}, Trickle(), lambda: None)
                return base.send(method, url, headers, ip, connect_timeout, read_timeout)
        tr = T()
        f = fetch.Fetcher("https://clinic.test/", transport=tr, resolver=tr.resolve, clock=clock, sleep=clock.sleep)
        f.fetch_home()
        r = f.fetch("https://clinic.test/slow", "page")
        self.assertEqual((r.outcome, r.reason), ("cap", "run_seconds"))
        self.assertEqual(f.stopped, "run_seconds")

    def test_gzip_bomb_stops_at_decoded_cap(self):
        bomb = gzip.compress(b"\0" * 10_000_000, mtime=0)
        self.assertLess(len(bomb), 50_000)
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://clinic.test/bomb": {"status": 200, "body_bytes": bomb,
                                                     "headers": {"content-type": "text/html",
                                                                 "content-encoding": "gzip"}}})
        f.fetch_home()
        real = fetch.zlib.decompressobj
        sizes = []

        class Spy:
            def __init__(self, *a):
                self._d = real(*a)

            def decompress(self, data, max_length=0):
                if max_length <= 0:
                    raise AssertionError("unbounded decompress call")
                out = self._d.decompress(data, max_length)
                sizes.append(len(out))
                return out

            def __getattr__(self, k):
                return getattr(self._d, k)
        with mock.patch.object(fetch.zlib, "decompressobj", Spy):
            r = f.fetch("https://clinic.test/bomb", "page")
        self.assertEqual((r.outcome, r.reason), ("cap", "page_bytes"))
        self.assertTrue(sizes)
        self.assertLessEqual(sum(sizes), fetch.CAPS["page_bytes"] + 1)

    def test_gzip_body_decoded(self):
        body = gzip.compress("<html>مرحبا</html>".encode(), mtime=0)
        f, t, _ = make({"https://clinic.test/": {"status": 200, "body_bytes": body,
                                                 "headers": {"content-type": "text/html", "content-encoding": "gzip"}}})
        r = f.fetch_home()
        self.assertEqual(r.body.decode(), "<html>مرحبا</html>")

    def test_corrupt_truncated_or_unasked_encoding_dropped(self):
        good = gzip.compress(b"<html>" + b"a" * 5000 + b"</html>", mtime=0)
        routes = {"https://clinic.test/": page(),
                  "https://clinic.test/c": {"status": 200, "body_bytes": b"\x1f\x8bgarbage",
                                            "headers": {"content-encoding": "gzip"}},
                  "https://clinic.test/t": {"status": 200, "body_bytes": good[: len(good) // 2],
                                            "headers": {"content-encoding": "gzip"}},
                  "https://clinic.test/br": {"status": 200, "body": "x", "headers": {"content-encoding": "br"}},
                  "https://clinic.test/df": {"status": 200, "body": "x", "headers": {"content-encoding": "deflate"}}}
        f, t, _ = make(routes)
        f.fetch_home()
        for p in ("c", "t", "br", "df"):
            with self.subTest(p=p):
                r = f.fetch(f"https://clinic.test/{p}", "page")
                self.assertEqual((r.outcome, r.reason, r.body), ("error", "bad_encoding", None))

    def test_http_error_status_is_an_error_result(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/gone": page(status=404)})
        f.fetch_home()
        r = f.fetch("https://clinic.test/gone", "page")
        self.assertEqual((r.outcome, r.reason, r.status), ("error", "http_status", 404))

    def test_home_http_error_stops_as_network(self):
        f, t, _ = make({"https://clinic.test/": page(status=500)})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "network")


# ---------------------------------------------------------------------------------------------- pacing, order
class TestPacingAndOrder(NetGuardCase):
    def test_one_second_between_requests_to_one_host(self):
        f, t, clock = make({"https://clinic.test/": page(), "https://clinic.test/a": page(),
                            "https://cdn.test/a.css": page("a{}", content_type="text/css")})
        f.fetch_home()                        # robots (t=0), home (+1)
        f.fetch("https://cdn.test/a.css", "css")   # other host: its robots and the file, not paced against clinic
        f.fetch("https://clinic.test/a", "page")
        self.assertEqual(clock.sleeps, [1.0, 1.0])

    def test_zero_gap_sleeper_for_fixture_runs(self):
        calls = []
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/a": page()}, sleep=calls.append,
                       min_gap=0)
        f.fetch_home()
        f.fetch("https://clinic.test/a", "page")
        self.assertEqual(calls, [])

    def test_queue_runs_in_kind_order(self):
        routes = {"https://clinic.test/": page(), "https://clinic.test/a": page(),
                  "https://cdn.test/a.css": page("a{}", content_type="text/css"),
                  "https://cdn.test/l.png": {"status": 200, "headers": {}, "body": "L"},
                  "https://cdn.test/f.ttf": {"status": 200, "headers": {}, "body": "F"},
                  "https://cdn.test/p.jpg": {"status": 200, "headers": {}, "body": "P"}}
        f, t, _ = make(routes)
        f.fetch_home()
        out = f.run_queue([("https://cdn.test/p.jpg", "photo"), ("https://cdn.test/f.ttf", "font"),
                           ("https://cdn.test/l.png", "logo"), ("https://cdn.test/a.css", "css"),
                           ("https://clinic.test/a", "page")])
        self.assertEqual([r.kind for r in out], ["page", "css", "logo", "font", "photo"])
        self.assertEqual([u.rsplit("/", 1)[1] for u in sent(t)][1:], ["a", "a.css", "l.png", "f.ttf", "p.jpg"])

    def test_queue_drops_the_later_kinds_when_a_run_cap_hits(self):
        routes = {"https://clinic.test/": page("h"), "https://cdn.test/a.css": page("c" * 50, content_type="text/css"),
                  "https://cdn.test/l.png": {"status": 200, "headers": {}, "body": "L" * 60},
                  "https://cdn.test/p.jpg": {"status": 200, "headers": {}, "body": "P"}}
        f, t, _ = make(routes, caps={"run_bytes": 100})
        f.fetch_home()
        out = f.run_queue([("https://cdn.test/p.jpg", "photo"), ("https://cdn.test/l.png", "logo"),
                           ("https://cdn.test/a.css", "css")])
        self.assertEqual([(r.kind, r.outcome) for r in out], [("css", "ok"), ("logo", "cap"), ("photo", "stopped")])


# ------------------------------------------------------------------------------------------- requests, privacy
class TestRequests(NetGuardCase):
    def test_user_agent_and_headers(self):
        f, t, _ = make({"https://clinic.test/": page()})
        f.fetch_home()
        self.assertRegex(fetch.USER_AGENT, r"^WhyNotCut/\d+\.\d+(\.\d+)? \(brand intake; \+https://thewhynot\.ai\)$")
        for r in t.requests:
            self.assertEqual(r["method"], "GET")
            self.assertEqual(r["headers"]["User-Agent"], fetch.USER_AGENT)
            self.assertEqual(r["headers"]["Accept-Encoding"], "gzip")
            self.assertNotIn("Cookie", r["headers"])
            self.assertNotIn("Authorization", r["headers"])
            self.assertNotIn("Referer", r["headers"])

    def test_no_cookie_sent_after_set_cookie(self):
        f, t, _ = make({"https://clinic.test/": page(set_cookie="sid=1; Path=/"), "https://clinic.test/a": page()})
        f.fetch_home()
        f.fetch("https://clinic.test/a", "page")
        self.assertTrue(all("Cookie" not in r["headers"] for r in t.requests))

    def test_no_query_string_added(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/a?x=1": page()})
        f.fetch_home()
        f.fetch("https://clinic.test/a?x=1", "page")
        self.assertEqual(sent(t), ["https://clinic.test/", "https://clinic.test/a?x=1"])


class TestLog(NetGuardCase):
    def test_every_request_and_refusal_logged_as_json_lines(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "fetch-log.jsonl"
            f, t, _ = make({"https://clinic.test/": page("hello")}, log_path=log)
            f.fetch_home()
            f.fetch("https://evil.test/x.css", "css")
            f.fetch("https://other.test/", "page")
            lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        keys = {"url", "host", "kind", "status", "bytes", "sha256", "robots", "ms", "outcome", "reason"}
        for ln in lines:
            self.assertTrue(keys <= set(ln), ln)
        home = [ln for ln in lines if ln["url"] == "https://clinic.test/"][0]
        self.assertEqual((home["status"], home["bytes"], home["robots"], home["outcome"]), (200, 5, "allowed", "ok"))
        self.assertEqual(len(home["sha256"]), 64)
        self.assertIn(("https://evil.test/x.css", "private_address"), [(ln["url"], ln["reason"]) for ln in lines])
        self.assertIn(("https://other.test/", "offsite"), [(ln["url"], ln["reason"]) for ln in lines])
        robots_line = [ln for ln in lines if ln["url"].endswith("/robots.txt")][0]
        self.assertEqual(robots_line["kind"], "robots")


# ----------------------------------------------------------------------------------- transport switch (J10)
class TestTransportSwitch(NetGuardCase):
    def _dir(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        Path(d.name, "routes.json").write_text(json.dumps({"dns": {}, "routes": {}}), encoding="utf-8")
        return d.name

    def test_fixture_transport_only_inside_the_test_sandbox(self):
        d = self._dir()
        t, resolver, sleep = fetch.transport_from_env({"WHYNOT_BRAND_TRANSPORT": "fixture:" + d})
        self.assertIsInstance(t, fetch.RealTransport)
        t2, resolver2, sleep2 = fetch.transport_from_env({"WHYNOT_BRAND_TRANSPORT": "fixture:" + d,
                                                          "WHYNOT_TEST_SANDBOX": "x"})
        self.assertIsInstance(t2, fetch.FixtureTransport)
        self.assertEqual(sleep2(5), None)

    def test_no_switch_gives_the_real_transport(self):
        t, resolver, sleep = fetch.transport_from_env({"WHYNOT_TEST_SANDBOX": "x"})
        self.assertIsInstance(t, fetch.RealTransport)


# ------------------------------------------------------------------------------------- proxy (doubles, J2.2)
class FakeResp:
    status = 200

    def __init__(self, body=b"<html></html>", status=200):
        self._b = io.BytesIO(body)
        self.status = status

    def getheaders(self):
        return [("Content-Type", "text/html")]

    def read(self, n=-1):
        return self._b.read(n)

    def close(self):
        pass


def fake_conn_class(fail=None, status=200):
    made = []

    class Sock:
        def __init__(self):
            self.timeouts = []

        def settimeout(self, t):
            self.timeouts.append(t)

        def shutdown(self, how):
            pass

    class Conn:
        def __init__(self, host, port=None, **kw):
            self.host, self.port, self.kw = host, port, kw
            self.tunnel, self.target, self.headers = None, None, []
            self.sock = Sock()
            made.append(self)

        def set_tunnel(self, host, port=None, headers=None):
            self.tunnel = (host, port)

        def putrequest(self, method, target, skip_host=False, skip_accept_encoding=False):
            self.method, self.target = method, target
            self.skip = (skip_host, skip_accept_encoding)

        def putheader(self, k, v):
            self.headers.append((k, v))

        def endheaders(self):
            if fail:
                raise OSError(fail)

        def getresponse(self):
            return FakeResp(status=status)

        def close(self):
            pass
    return Conn, made


class TestProxy(NetGuardCase):
    def _transport(self, proxies=None, bypass=lambda h: False, pac=None, fail=None, status=200):
        Conn, made = fake_conn_class(fail, status)
        proxy = fetch.ProxyConfig(proxies or {}, bypass, pac)
        tr = fetch.RealTransport(proxy=proxy, tls=lambda: "CTX", http_conn=Conn, https_conn=Conn)
        return tr, made

    def test_https_through_proxy_connects_to_the_checked_ip(self):
        tr, made = self._transport({"https": "http://proxy.corp:3128"})
        tr.send("GET", "https://clinic.test/a", {"User-Agent": "x"}, PUB, 10, 20)
        c = made[0]
        self.assertEqual((c.host, c.port), ("proxy.corp", 3128))
        self.assertEqual(c.tunnel, (PUB, 443))
        self.assertEqual(c.kw["sni"], "clinic.test")
        self.assertEqual(c.kw["context"], "CTX")
        self.assertIn(("Host", "clinic.test"), c.headers)
        self.assertEqual(c.target, "/a")

    def test_https_direct_connects_to_the_ip_with_sni_name(self):
        tr, made = self._transport()
        tr.send("GET", "https://clinic.test:8443/a?q=1", {}, PUB, 10, 20)
        c = made[0]
        self.assertEqual((c.host, c.port, c.tunnel), (PUB, 8443, None))
        self.assertEqual(c.kw["sni"], "clinic.test")
        self.assertIn(("Host", "clinic.test:8443"), c.headers)
        self.assertEqual(c.target, "/a?q=1")

    def test_ipv6_checked_ip_tunnel(self):
        tr, made = self._transport({"https": "http://proxy.corp:3128"})
        tr.send("GET", "https://clinic.test/", {}, "2606:4700:4700::1111", 10, 20)
        self.assertEqual(made[0].tunnel, ("2606:4700:4700::1111", 443))

    def test_http_through_proxy_is_tunnelled_to_the_checked_ip(self):
        tr, made = self._transport({"http": "http://proxy.corp:8080"})
        tr.send("GET", "http://clinic.test/a", {}, PUB, 10, 20)
        c = made[0]
        self.assertEqual((c.host, c.port, c.tunnel, c.target), ("proxy.corp", 8080, (PUB, 80), "/a"))
        self.assertIn(("Host", "clinic.test"), c.headers)

    def test_http_direct_goes_to_ip(self):
        tr, made = self._transport()
        tr.send("GET", "http://clinic.test/a", {}, PUB, 10, 20)
        self.assertEqual((made[0].host, made[0].port, made[0].target), (PUB, 80, "/a"))

    def test_bypass_list_goes_direct(self):
        tr, made = self._transport({"https": "http://proxy.corp:3128"}, bypass=lambda h: h == "clinic.test")
        tr.send("GET", "https://clinic.test/", {}, PUB, 10, 20)
        self.assertEqual((made[0].host, made[0].tunnel), (PUB, None))

    def test_proxy_on_private_address_allowed(self):
        tr, made = self._transport({"https": "http://10.0.0.2:3128"})
        tr.send("GET", "https://clinic.test/", {}, PUB, 10, 20)
        self.assertEqual(made[0].host, "10.0.0.2")

    def test_407_raises_proxy_login(self):
        tr, made = self._transport({"https": "http://proxy.corp:3128"},
                                   fail="Tunnel connection failed: 407 Proxy Authentication Required")
        with self.assertRaises(fetch.ProxyLoginNeeded):
            tr.send("GET", "https://clinic.test/", {}, PUB, 10, 20)
        tr2, _ = self._transport({"http": "http://proxy.corp:8080"},
                                 fail="Tunnel connection failed: 407 Proxy Authentication Required")
        with self.assertRaises(fetch.ProxyLoginNeeded):
            tr2.send("GET", "http://clinic.test/", {}, PUB, 10, 20)

    def test_direct_407_is_just_an_http_status(self):
        tr, _ = self._transport(status=407)
        r = tr.send("GET", "https://cdn.test/a.png", {}, PUB, 10, 20)
        self.assertEqual(r.status, 407)
        r.close()

    def test_407_stops_the_run_with_the_one_line_message(self):
        t = fetch.FixtureTransport({"dns": DNS, "routes": {"https://clinic.test/robots.txt": {"raise": "proxy_login"}}})
        f = fetch.Fetcher("https://clinic.test/", transport=t, resolver=t.resolve, sleep=lambda s: None)
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "proxy_login")
        self.assertIn("البروكسي محتاج تسجيل دخول", cm.exception.message_ar)

    def test_pac_means_no_proxy_and_is_reported(self):
        p = fetch.ProxyConfig({"https": "http://proxy.corp:3128"}, lambda h: False, "http://wpad/proxy.pac")
        self.assertIsNone(p.for_url("https", "clinic.test"))
        self.assertTrue(p.pac_ignored)

    def test_unsupported_proxy_scheme_ignored(self):
        p = fetch.ProxyConfig({"https": "socks5://127.0.0.1:1080"}, lambda h: False, None)
        self.assertIsNone(p.for_url("https", "clinic.test"))
        self.assertEqual(p.unsupported, "socks5")

    def test_proxy_without_scheme_and_default_port(self):
        p = fetch.ProxyConfig({"https": "proxy.corp:3128", "http": "http://proxy2.corp"}, lambda h: False, None)
        self.assertEqual(p.for_url("https", "clinic.test"), ("proxy.corp", 3128))
        self.assertEqual(p.for_url("http", "clinic.test"), ("proxy2.corp", 80))

    def test_system_reads_windows_pac(self):
        p = fetch.ProxyConfig.system(platform="win32", getproxies=lambda: {}, bypass=lambda h: False,
                                     win_reg=lambda: {"AutoConfigURL": "http://wpad/x.pac", "ProxyEnable": 0})
        self.assertEqual(p.pac, "http://wpad/x.pac")

    def test_system_reads_macos_pac(self):
        out = "<dictionary> {\n  ProxyAutoConfigEnable : 1\n  ProxyAutoConfigURLString : http://pac.corp/p.pac\n}\n"
        p = fetch.ProxyConfig.system(platform="darwin", getproxies=lambda: {}, bypass=lambda h: False,
                                     scutil=lambda: out)
        self.assertEqual(p.pac, "http://pac.corp/p.pac")
        p2 = fetch.ProxyConfig.system(platform="darwin", getproxies=lambda: {}, bypass=lambda h: False,
                                      scutil=lambda: "<dictionary> {\n  ProxyAutoConfigEnable : 0\n}\n")
        self.assertIsNone(p2.pac)

    def test_system_pac_reader_failure_is_no_pac(self):
        def boom():
            raise OSError("no registry")
        p = fetch.ProxyConfig.system(platform="win32", getproxies=lambda: {}, bypass=lambda h: False, win_reg=boom)
        self.assertIsNone(p.pac)


# ------------------------------------------------------------------------------------------ TLS (J2.3)
class TestTls(NetGuardCase):
    def _fake_truststore(self):
        mod = types.ModuleType("truststore")
        ctx = mock.MagicMock(name="ctx")
        mod.SSLContext = mock.MagicMock(return_value=ctx)
        return mod, ctx

    def test_context_from_truststore_on_windows_and_macos(self):
        for plat_name in ("win32", "darwin"):
            with self.subTest(platform=plat_name):
                mod, ctx = self._fake_truststore()
                with mock.patch.dict(sys.modules, {"truststore": mod}), mock.patch.object(sys, "platform", plat_name):
                    got = fetch.tls_context()
                mod.SSLContext.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
                self.assertIs(got, ctx)
                self.assertEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_truststore_missing_means_setup_needed_never_certifi(self):
        with mock.patch.dict(sys.modules, {"truststore": None}):
            with self.assertRaises(fetch.FetchStop) as cm:
                fetch.tls_context()
        self.assertEqual(cm.exception.code, "setup_needed")
        self.assertIn("reel setup", cm.exception.message_en)

    def test_pinned_https_connection_wraps_with_the_host_name(self):
        ctx = mock.MagicMock()
        c = fetch._PinnedHTTPSConnection(PUB, 443, sni="clinic.test", context=ctx, timeout=10)
        sock = mock.MagicMock()
        c._create_connection = mock.MagicMock(return_value=sock)
        c.connect()
        c._create_connection.assert_called_once()
        self.assertEqual(c._create_connection.call_args[0][0], (PUB, 443))
        ctx.wrap_socket.assert_called_once_with(sock, server_hostname="clinic.test")

    def test_certificate_error_maps_to_certificate(self):
        Conn, made = fake_conn_class(fail=None)

        class Bad(Conn):
            def endheaders(self):
                raise ssl.SSLCertVerificationError(1, "certificate verify failed: self-signed")
        tr = fetch.RealTransport(proxy=fetch.ProxyConfig({}, lambda h: False, None), tls=lambda: "CTX",
                                 http_conn=Bad, https_conn=Bad)
        with self.assertRaises(fetch.CertificateFailed):
            tr.send("GET", "https://clinic.test/", {}, PUB, 10, 20)

    def test_source_never_turns_verification_off(self):
        pat = re.compile(r"CERT_NONE|CERT_OPTIONAL|verify_mode|check_hostname\s*=\s*False|verify\s*=\s*False|"
                         r"inject_into_ssl|_create_unverified_context|create_default_context|certifi")
        files = sorted((ENGINE / "lib" / "brand_web").rglob("*.py"))
        self.assertTrue(files)
        for p in files:
            with self.subTest(p=p.name):
                self.assertIsNone(pat.search(p.read_text(encoding="utf-8")))

    @unittest.skipUnless(importlib.util.find_spec("truststore"), "truststore not in this runtime yet (Task 12 lock)")
    def test_loopback_self_signed_https_refused_with_the_j23_message(self):
        sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sctx.load_cert_chain(str(FIXTURES / "tls" / "localhost-cert.pem"), str(FIXTURES / "tls" / "localhost-key.pem"))

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"hi")

            def log_message(self, *a):
                pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        srv.socket = sctx.wrap_socket(srv.socket, server_side=True, do_handshake_on_connect=False)
        srv.handle_error = lambda *a: None          # the client refusing the handshake is the expected outcome
        th = threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.05), daemon=True)
        th.start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        tr = fetch.RealTransport(proxy=fetch.ProxyConfig({}, lambda h: False, None))
        f = fetch.Fetcher(f"https://localhost:{port}/", transport=tr, resolver=lambda h, p: ["127.0.0.1"],
                          ip_ok=lambda ip: ip == "127.0.0.1", sleep=lambda s: None)
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "certificate")
        self.assertIn("جهازك ما قدرش يتأكد من شهادة أمان الموقع", cm.exception.message_ar)
        self.assertIn("couldn't verify the site's security certificate", cm.exception.message_en)


class TestDoctorLine(NetGuardCase):
    def test_available_and_missing(self):
        with mock.patch.object(fetch.importlib.util, "find_spec", return_value=object()):
            st = fetch.doctor_status()
        self.assertTrue(st["ok"])
        self.assertIn("system certificates available", st["line_en"])
        with mock.patch.object(fetch.importlib.util, "find_spec", return_value=None):
            st = fetch.doctor_status()
        self.assertFalse(st["ok"])
        self.assertIn("missing", st["line_en"])
        self.assertEqual(st["fix"], "reel setup")
        self.assertRegex(st["line_ar"], "[؀-ۿ]")


class TestMessages(NetGuardCase):
    def test_every_stop_code_has_arabic_and_english(self):
        for code in ("bad_url", "private_address", "refused_by_site", "offsite_redirect", "certificate", "network",
                     "proxy_login", "setup_needed", "downgrade", "run_bytes", "run_seconds", "proxy_refused"):
            with self.subTest(code=code):
                e = fetch.FetchStop(code, url="https://x.test/")
                self.assertTrue(e.message_ar and e.message_en)
                self.assertRegex(e.message_ar, "[\u0600-\u06FF]")


# ------------------------------------------------------------------------------- review round 1 (J-T1)
def _slow_server(test, payload_bytes, gap, fast_prefix=b""):
    """A loopback server that answers each request with `fast_prefix` at once, then `payload_bytes` one byte every
    `gap` seconds."""
    import socket as _s
    import time as _t
    srv = _s.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    srv.settimeout(0.2)
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                c, _a = srv.accept()
            except OSError:
                continue
            try:
                c.recv(4096)
                if fast_prefix:
                    c.sendall(fast_prefix)
                for ch in payload_bytes:
                    if stop.is_set():
                        break
                    c.sendall(bytes([ch]))
                    _t.sleep(gap)
            except OSError:
                pass
            finally:
                c.close()
    th = threading.Thread(target=serve, daemon=True)
    th.start()
    test.addCleanup(th.join, 2)
    test.addCleanup(srv.close)
    test.addCleanup(stop.set)
    return srv.getsockname()[1]


class TestReviewRound1(NetGuardCase):
    def _loopback_fetcher(self, port, **caps):
        tr = fetch.RealTransport(proxy=fetch.ProxyConfig.none())
        return fetch.Fetcher(f"http://localhost:{port}/", transport=tr, resolver=lambda h, p: ["127.0.0.1"],
                             ip_ok=lambda ip: ip == "127.0.0.1", sleep=lambda s: None, min_gap=0, caps=caps)

    def test_r1_slow_body_cannot_outlast_the_run_cap(self):
        import time as _t
        port = _slow_server(self, b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + b"x" * 2000, 0.02)
        f = self._loopback_fetcher(port, run_seconds=2, read_timeout=1)      # the whole body would take 40 s
        t0 = _t.monotonic()
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "run_seconds")
        self.assertLess(_t.monotonic() - t0, 4.0)

    def test_r1_slow_headers_cannot_outlast_the_run_cap(self):
        import time as _t
        port = _slow_server(self, b"HTTP/1.1 200 OK\r\nX-Slow: " + b"y" * 300, 0.02)
        f = self._loopback_fetcher(port, run_seconds=2, read_timeout=1)
        t0 = _t.monotonic()
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "run_seconds")
        self.assertLess(_t.monotonic() - t0, 4.0)

    def test_r1_direct_407_from_a_cdn_is_one_failed_item(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://cdn.test/a.css": page("a{}", content_type="text/css"),
                        "https://cdn.test/l.png": {"status": 407, "headers": {}, "body": ""}})
        f.fetch_home()
        out = f.run_queue([("https://cdn.test/l.png", "logo"), ("https://cdn.test/a.css", "css")])
        self.assertEqual([(r.kind, r.outcome, r.reason) for r in out],
                         [("css", "ok", ""), ("logo", "error", "http_status")])
        self.assertIsNone(f.stopped)

    def test_r1_proxy_login_mid_run_stops_without_losing_results(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://cdn.test/a.css": page("a{}", content_type="text/css"),
                        "https://cdn2.test/robots.txt": {"raise": "proxy_login"}})
        f.fetch_home()
        out = f.run_queue([("https://cdn2.test/l.png", "logo"), ("https://cdn.test/a.css", "css")])
        self.assertEqual([(r.kind, r.outcome) for r in out], [("css", "ok"), ("logo", "stopped")])
        self.assertEqual(f.stopped, "proxy_login")

    def test_r1_robots_redirect_to_another_port_is_refused(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://clinic.test/robots.txt": moved("https://clinic.test:6379/robots.txt")})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "network")
        self.assertFalse(any(":6379" in r["url"] for r in t.requests))

    def test_r1_page_redirect_cannot_leave_the_path_scope(self):
        f, t, _ = make({"https://sites.test/view/x": page(), "https://sites.test/view/x/a": moved("/view/other/"),
                        "https://sites.test/view/other/": page()}, start="https://sites.test/view/x")
        f.fetch_home()
        r = f.fetch("https://sites.test/view/x/a", "page")
        self.assertEqual((r.outcome, r.reason), ("refused", "out_of_scope"))
        self.assertNotIn("https://sites.test/view/other/", sent(t))

    def test_r1_home_redirect_inside_the_path_scope_is_followed(self):
        f, t, _ = make({"https://sites.test/view/x": moved("/view/x/home"), "https://sites.test/view/x/home": page()},
                       start="https://sites.test/view/x")
        self.assertEqual(f.fetch_home().outcome, "ok")

    def test_r1_cache_is_per_kind_and_never_keeps_refusals(self):
        f, t, _ = make({"https://clinic.test/": page(), "https://cdn.test/a.jpg": {"status": 200, "body": "J"},
                        "https://cdn.test/a.css": page("a{}", content_type="text/css")})
        f.fetch_home()
        self.assertEqual(f.fetch("https://cdn.test/a.jpg", "page").reason, "offsite")
        self.assertEqual(f.fetch("https://cdn.test/a.jpg", "photo").outcome, "ok")
        self.assertEqual(f.fetch("https://cdn.test/a.css", "css").outcome, "ok")
        self.assertEqual(f.fetch("https://cdn.test/a.css", "css", depth=5).reason, "depth")
        self.assertEqual(f.fetch("https://cdn.test/a.css", "page").reason, "offsite")

    def test_r1_dot_segments_removed_so_robots_and_scope_hold(self):
        self.assertEqual(fetch.normalize("https://clinic.test/pub/../private/x"), "https://clinic.test/private/x")
        self.assertEqual(fetch.normalize("https://clinic.test/a/./b/%2e%2E/c"), "https://clinic.test/a/c")
        self.assertEqual(fetch.normalize("https://clinic.test/../../x"), "https://clinic.test/x")
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/robots.txt": page(
            "User-agent: *\nDisallow: /private\n")})
        f.fetch_home()
        self.assertEqual(f.fetch("https://clinic.test/pub/../private/x", "page").reason, "robots")
        s = fetch.Scope("https://sites.test/view/x")
        self.assertFalse(s.page_ok("https://sites.test/view/x/../other/")[0])

    def test_r1_truncated_robots_drops_the_cut_line(self):
        cut = 500 * 1024
        head = "User-agent: *\nDisallow: /\n" + ("#" * 70 + "\n") * 7000
        head += "#" * (cut - len("Allow: /") - len(head) - 1) + "\n"
        body = head + "Allow: /" + "s" * 50 + "\n"          # the cut lands right after "Allow: /"
        self.assertEqual(body.encode()[:cut].decode().rsplit("\n", 1)[1], "Allow: /")
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/robots.txt": page(body)})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "refused_by_site")

    def test_r1_robots_unreserved_percent_escapes_decoded(self):
        self.assertFalse(robots.parse("User-agent: *\nDisallow: /admin\n").allowed("/%61dmin"))
        self.assertFalse(robots.parse("User-agent: *\nDisallow: /%7Euser\n").allowed("/~user"))
        self.assertTrue(robots.parse("User-agent: *\nDisallow: /a%2Fb\n").allowed("/a/b"))

    def test_r1_robots_agent_line_with_version_matches_our_token(self):
        r = robots.parse("User-agent: *\nAllow: /\n\nUser-agent: WhyNotCut/3.0\nDisallow: /\n")
        self.assertFalse(r.allowed("/a"))
        self.assertTrue(robots.parse("User-agent: WhyNotCutter\nDisallow: /\n").allowed("/a"))

    def test_r1_hosts_contacted_only_for_robots_are_named(self):
        f, t, _ = make({"https://clinic.test/robots.txt": page("User-agent: *\nDisallow: /\n")})
        with self.assertRaises(fetch.FetchStop):
            f.fetch_home()
        self.assertEqual(sorted(f.hosts_read), ["clinic.test"])

    def test_r1_notes_report_pac_unsupported_proxy_and_insecure_start(self):
        Conn, made = fake_conn_class()
        tr = fetch.RealTransport(proxy=fetch.ProxyConfig({"https": "socks5://p:1"}, lambda h: False, None),
                                 tls=lambda: "CTX", http_conn=Conn, https_conn=Conn)
        f = fetch.Fetcher("https://clinic.test/", transport=tr, resolver=lambda h, p: [PUB], sleep=lambda s: None)
        f.fetch_home()
        self.assertIn("proxy_unsupported", f.notes())
        tr2 = fetch.RealTransport(proxy=fetch.ProxyConfig({}, lambda h: False, "http://wpad/x.pac"), tls=lambda: "C",
                                  http_conn=Conn, https_conn=Conn)
        f2 = fetch.Fetcher("http://clinic.test/", transport=tr2, resolver=lambda h, p: [PUB], sleep=lambda s: None)
        f2.fetch_home()
        self.assertIn("pac_ignored", f2.notes())
        self.assertIn("insecure_start", f2.notes())

    def test_r1_windows_auto_detect_and_macos_auto_discovery_count_as_pac(self):
        blob = bytes([0x46, 0, 0, 0, 1, 0, 0, 0, 0x09, 0, 0, 0])
        p = fetch.ProxyConfig.system(platform="win32", getproxies=lambda: {}, bypass=lambda h: False,
                                     win_reg=lambda: {"DefaultConnectionSettings": blob})
        self.assertIsNone(p.pac)                       # Windows' default "detect automatically" is not a PAC script
        self.assertTrue(p.auto_detect)
        self.assertIsNone(p.for_url("https", "clinic.test"))
        self.assertFalse(p.pac_ignored)
        p0 = fetch.ProxyConfig.system(platform="win32", getproxies=lambda: {}, bypass=lambda h: False,
                                      win_reg=lambda: {"DefaultConnectionSettings": bytes([0x46, 0, 0, 0, 1, 0, 0, 0,
                                                                                             0x01, 0, 0, 0])})
        self.assertFalse(p0.auto_detect)
        p2 = fetch.ProxyConfig.system(platform="darwin", getproxies=lambda: {}, bypass=lambda h: False,
                                      scutil=lambda: "<dictionary> {\n  ProxyAutoDiscoveryEnable : 1\n}\n")
        self.assertTrue(p2.auto_detect)
        self.assertIsNone(p2.pac)

    def test_r2_manual_proxy_plus_auto_detect_uses_the_manual_proxy(self):
        blob = bytes([0x46, 0, 0, 0, 1, 0, 0, 0, 0x0B, 0, 0, 0])
        p = fetch.ProxyConfig.system(platform="win32", getproxies=lambda: {"https": "http://proxy.corp:3128"},
                                     bypass=lambda h: False, win_reg=lambda: {"DefaultConnectionSettings": blob})
        self.assertEqual(p.for_url("https", "clinic.test"), ("proxy.corp", 3128))

    def test_r1_each_checked_address_is_tried(self):
        base = fetch.FixtureTransport({"dns": {"clinic.test": ["2606:4700::1", PUB]},
                                       "routes": {"https://clinic.test/": page()}})

        class T:
            requests = base.requests

            def send(self, method, url, headers, ip, ct, rt, deadline=None):
                if ":" in ip:
                    raise ConnectionRefusedError("no ipv6 route")
                return base.send(method, url, headers, ip, ct, rt)
        tr = T()
        f = fetch.Fetcher("https://clinic.test/", transport=tr, resolver=base.resolve, sleep=lambda s: None)
        self.assertEqual(f.fetch_home().outcome, "ok")

    def test_r1_font_count_cap(self):
        routes = {"https://clinic.test/": page()}
        routes.update({f"https://cdn.test/{i}.ttf": {"status": 200, "body": "F"} for i in range(3)})
        f, t, _ = make(routes, caps={"font_count": 2})
        f.fetch_home()
        self.assertEqual([f.fetch(f"https://cdn.test/{i}.ttf", "font").reason for i in range(3)],
                         ["", "", "font_count"])
        self.assertEqual(fetch.CAPS["font_count"], 20)

    def test_r1_run_budget_counts_decoded_bytes(self):
        body = gzip.compress(b"a" * 90, mtime=0)
        f, t, _ = make({"https://clinic.test/": {"status": 200, "body_bytes": body,
                                                 "headers": {"content-type": "text/html", "content-encoding": "gzip"}},
                        "https://clinic.test/b": page("b" * 20)}, caps={"run_bytes": 100})
        f.fetch_home()
        self.assertEqual(f.fetch("https://clinic.test/b", "page").reason, "run_bytes")

    def test_r1_after_upgrade_to_https_no_more_http(self):
        f, t, _ = make({"http://clinic.test/": moved("https://clinic.test/"), "https://clinic.test/": page(),
                        "http://clinic.test/a": page()}, start="http://clinic.test/")
        f.fetch_home()
        self.assertEqual(f.fetch("http://clinic.test/a", "page").reason, "downgrade")

    def test_r1_home_redirect_to_another_port_asks(self):
        f, t, _ = make({"https://clinic.test/": moved("https://clinic.test:8443/")})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual((cm.exception.code, cm.exception.url), ("offsite_redirect", "https://clinic.test:8443/"))

    def test_r1_garbage_crawl_delay_paces_at_one_second(self):
        f, t, clock = make({"https://clinic.test/": page(), "https://clinic.test/a": page(),
                            "https://clinic.test/robots.txt": page("User-agent: *\nCrawl-delay: soon\n")})
        f.fetch_home()
        f.fetch("https://clinic.test/a", "page")
        self.assertEqual(clock.sleeps, [1.0, 1.0])

    def test_r1_per_request_timeouts_reach_the_connection(self):
        Conn, made = fake_conn_class()
        tr = fetch.RealTransport(proxy=fetch.ProxyConfig.none(), tls=lambda: "C", http_conn=Conn, https_conn=Conn)
        f = fetch.Fetcher("https://clinic.test/", transport=tr, resolver=lambda h, p: [PUB], sleep=lambda s: None)
        f.fetch_home()
        self.assertEqual(made[-1].kw["timeout"], 10)
        self.assertEqual(made[-1].sock.timeouts[-1], 20)
        made.clear()
        clock = FakeClock()
        f2 = fetch.Fetcher("https://clinic.test/", transport=tr, resolver=lambda h, p: [PUB], clock=clock,
                           sleep=clock.sleep, caps={"run_seconds": 5}, min_gap=0)
        f2.fetch_home()
        self.assertEqual(made[-1].kw["timeout"], 5)         # min(cap, the run's time left)
        self.assertEqual(made[-1].sock.timeouts[-1], 5)

    def test_r1_tunnel_connect_names_the_ip_and_sni_the_name(self):
        ctx = mock.MagicMock()
        c = fetch._PinnedHTTPSConnection("proxy.corp", 3128, sni="clinic.test", context=ctx, timeout=10)
        c.set_tunnel(PUB, 443)
        sent_bytes = []

        class Sock:
            def sendall(self, b):
                sent_bytes.append(bytes(b))

            def makefile(self, mode, *a, **k):
                return io.BytesIO(b"HTTP/1.1 200 Connection established\r\n\r\n")

            def setsockopt(self, *a):
                pass

            def close(self):
                pass
        c._create_connection = mock.MagicMock(return_value=Sock())
        c.connect()
        self.assertEqual(c._create_connection.call_args[0][0], ("proxy.corp", 3128))
        self.assertTrue(b"".join(sent_bytes).startswith(f"CONNECT {PUB}:443 ".encode()))
        self.assertEqual(ctx.wrap_socket.call_args[1]["server_hostname"], "clinic.test")

    def test_r1_malformed_reply_closes_the_socket(self):
        port = _slow_server(self, b"HTTP/1.1 200 OK\r\n" + b"".join(b"X-%d: a\r\n" % i for i in range(150)) + b"\r\n",
                            0)
        f = self._loopback_fetcher(port)
        caught = []
        old = sys.unraisablehook
        sys.unraisablehook = lambda u: caught.append(u)      # a leaked socket warns from __del__, which only this sees
        try:
            with self.assertRaises(fetch.FetchStop) as cm:
                f.fetch_home()
            import gc
            gc.collect()
        finally:
            sys.unraisablehook = old
        self.assertEqual(cm.exception.code, "network")
        self.assertEqual([u for u in caught if issubclass(u.exc_type, ResourceWarning)], [])


# ------------------------------------------------------------------------------- review round 2 (J-T1)
class TestReviewRound2(NetGuardCase):
    def test_r2_a_website_407_through_the_tunnel_is_one_item(self):
        Conn, made = fake_conn_class(status=407)
        tr = fetch.RealTransport(proxy=fetch.ProxyConfig({"https": "http://proxy.corp:3128"}, lambda h: False, None),
                                 tls=lambda: "C", http_conn=Conn, https_conn=Conn)
        r = tr.send("GET", "https://cdn.test/l.png", {}, PUB, 10, 20)
        self.assertEqual(r.status, 407)
        r.close()

    def test_r2_body_shorter_than_its_content_length_is_not_accepted(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://clinic.test/cut": {"status": 200, "body": "123456789",
                                                    "headers": {"content-type": "text/html", "content-length": "1000"}}})
        f.fetch_home()
        r = f.fetch("https://clinic.test/cut", "page")
        self.assertEqual((r.outcome, r.reason, r.body), ("error", "truncated", None))

    def test_r2_truncated_robots_is_deny(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://clinic.test/robots.txt": {"status": 200, "body": "User-agent: *\nAllow: /\n",
                                                           "headers": {"content-length": "5000"}}})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "network")

    def test_r2_robots_over_the_cap_with_cr_only_line_ends(self):
        body = "User-agent: *\rDisallow: /\r" + "#" * (600 * 1024)
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/robots.txt": page(body)})
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "refused_by_site")
        body2 = "#" * (600 * 1024)                       # no line end at all within the cap → deny
        f2, _, _ = make({"https://clinic.test/": page(), "https://clinic.test/robots.txt": page(body2)})
        with self.assertRaises(fetch.FetchStop):
            f2.fetch_home()

    def test_r2_watchdog_stops_a_body_that_trickles_slower_than_nothing_times_out(self):
        import time as _t
        port = _slow_server(self, b"x" * 50, 2.5,
                            fast_prefix=b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n")
        f = self._loopback_fetcher(port, run_seconds=3, read_timeout=20)
        t0 = _t.monotonic()
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()                    # a byte every 2.5 s: no read times out (3 s), only the watchdog ends it
        self.assertEqual(cm.exception.code, "run_seconds")
        self.assertLess(_t.monotonic() - t0, 4.5)

    _loopback_fetcher = TestReviewRound1._loopback_fetcher

    def test_r2_no_request_once_pacing_has_used_up_the_time(self):
        clock = FakeClock()
        f, t, _ = make({"https://clinic.test/": page(), "https://clinic.test/a": page(),
                        "https://clinic.test/robots.txt": page("User-agent: *\nCrawl-delay: 10\n")},
                       clock=clock, sleep=clock.sleep, caps={"run_seconds": 15})
        f.fetch_home()                                   # robots at 0, home at 10
        r = f.fetch("https://clinic.test/a", "page")     # would start at 20 > 15
        self.assertEqual((r.outcome, r.reason), ("stopped", "run_seconds"))
        self.assertNotIn("https://clinic.test/a", sent(t))

    def test_r2_proxy_refusing_the_tunnel_has_its_own_message(self):
        tr, made = TestProxy._transport(self, {"http": "http://proxy.corp:8080"},
                                        fail="Tunnel connection failed: 403 Forbidden")
        with self.assertRaises(fetch.ProxyRefused):
            tr.send("GET", "http://clinic.test/", {}, PUB, 10, 20)
        t = fetch.FixtureTransport({"dns": DNS, "routes": {"http://clinic.test/robots.txt": {"raise": "proxy_refused"}}})
        f = fetch.Fetcher("http://clinic.test/", transport=t, resolver=t.resolve, sleep=lambda s: None)
        with self.assertRaises(fetch.FetchStop) as cm:
            f.fetch_home()
        self.assertEqual(cm.exception.code, "proxy_refused")
        self.assertIn("البروكسي", cm.exception.message_ar)

    def test_r3_tunnel_5xx_means_the_site_is_down_not_a_proxy_refusal(self):
        tr, made = TestProxy._transport(self, {"https": "http://proxy.corp:3128"},
                                        fail="Tunnel connection failed: 503 Service Unavailable")
        with self.assertRaises(OSError) as cm:
            tr.send("GET", "https://clinic.test/", {}, PUB, 10, 20)
        self.assertNotIsInstance(cm.exception, fetch.ProxyRefused)

    def test_r3_chunked_body_with_a_stray_content_length_is_not_truncated(self):
        f, t, _ = make({"https://clinic.test/": page(),
                        "https://clinic.test/c": {"status": 200, "body": "123456789",
                                                  "headers": {"content-type": "text/html", "content-length": "1000",
                                                              "transfer-encoding": "chunked"}}})
        f.fetch_home()
        self.assertEqual(f.fetch("https://clinic.test/c", "page").outcome, "ok")


if __name__ == "__main__":
    unittest.main()
