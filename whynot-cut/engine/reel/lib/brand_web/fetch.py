# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The website reader's network core (Addendum J2, J13.2, J13.4). The only code in the brand-from-website feature
that touches the network.

  * URLs (J2.1): http/https with a host, the start site = the editor's host plus its www/apex twin (and, when the
    start URL has a path, that path and below, plus hreflang alternates on the same host); pages only from the start
    site; sub-resources (CSS, images, icons, fonts) from any host but only by the exact URL a fetched page or
    stylesheet names, depth ≤ 2, never crawled; never https → http (also after an http start was upgraded).
    Dot segments are removed before any rule is applied.
  * Addresses (J2.2): every address a host resolves to must be global (netcheck.ip_ok), checked again after every
    redirect and for every sub-resource; the connection goes to a checked address (each one is tried in turn), and
    the TLS name check keeps the host name. Through a proxy, http and https alike go through a CONNECT tunnel to the
    checked address, so the proxy never resolves the name itself (stricter than J2.2's absolute-URI form for http).
  * robots.txt (RFC 9309, robots.py) for every host, 4xx = allow, 5xx/unreachable = deny, 500 KiB, Crawl-delay ≤ 10 s;
    the one exemption is the hash-pinned open-font source (`pinned=True`, J2.1 ruling).
  * Caps (CAPS, the J2.2 table, plus a font count): each stops cleanly with its name. The run budget counts decoded
    bytes; gzip is decoded as it streams, so every byte cap applies to decoded bytes. A watchdog closes the socket when
    the run's time is up, so a server that trickles bytes can't hold the run past its time cap.
  * TLS (J2.3): `truststore`, the operating system's own trust store, one context per connection, never a global
    patch; missing → `setup_needed`, never a fallback.
  * Privacy (J2.5, J13.4): GET only, no cookies, no query string of our own, a User-Agent that says nothing about the
    user or the machine; nothing is ever sent anywhere else.
Pacing uses an injectable clock and sleeper; the fixture transport (tests and evals, only inside the test sandbox)
maps URLs to files.
"""
from __future__ import annotations

import hashlib
import http.client
import importlib.util
import io
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import zlib
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from . import netcheck, robots

CAPS = {
    "pages_default": 6, "pages_max": 10,
    "page_bytes": 3_000_000,
    "css_bytes": 2_000_000, "css_count": 30,
    "image_bytes": 15_000_000, "image_pixels": 50_000_000, "logo_count": 30, "photo_count": 20,
    "font_bytes": 8_000_000, "font_count": 20,
    "robots_bytes": 500 * 1024,
    "run_bytes": 150_000_000, "run_seconds": 180,
    "connect_timeout": 10, "read_timeout": 20,
    "host_gap": 1.0, "crawl_delay_max": 10.0, "redirects": 5, "depth": 2,
}
KIND_ORDER = ("page", "css", "logo", "font", "photo")
_BYTES_CAP = {"page": "page_bytes", "css": "css_bytes", "logo": "image_bytes", "photo": "image_bytes",
              "font": "font_bytes"}
_COUNT_CAP = {"page": "pages", "css": "css_count", "logo": "logo_count", "photo": "photo_count",
              "font": "font_count"}
_RUN_STOPS = ("run_bytes", "run_seconds", "proxy_login")
PINNED_FONT_HOST = "raw.githubusercontent.com"
PINNED_FONT_PREFIX = "/google/fonts/"
_DEFAULT_PORT = {"http": 80, "https": 443}
_REDIRECT = (301, 302, 303, 307, 308)
_CHUNK = 64 * 1024
_LABEL = re.compile(r"^(?!-)[a-z0-9_-]{1,63}(?<!-)$")


def _version() -> str:
    try:
        from .. import selfid
        v = selfid.plugin_info().get("version") or ""
    except Exception:
        v = ""
    return v if re.fullmatch(r"\d+\.\d+(\.\d+)?", v) else "3.0.0"


USER_AGENT = f"WhyNotCut/{_version()} (brand intake; +https://thewhynot.ai)"

_ASK_CLIENT_AR = "اطلب ملفات الهوية من العميل"
_ASK_CLIENT_EN = "ask the client for the brand files"
MESSAGES = {
    "bad_url": ("اللينك ده مش عنوان موقع نقدر نقراه (لازم يكون موقع عام يبدأ بـ http أو https)؛ اتأكد منه أو "
                + _ASK_CLIENT_AR,
                "this link isn't a website address we can read (a public site starting with http or https); check "
                "it or " + _ASK_CLIENT_EN),
    "private_address": ("اللينك ده بيشاور على جهاز في الشبكة الداخلية، وإحنا بنقرا المواقع العامة بس؛ "
                        + _ASK_CLIENT_AR,
                        "this link points to a computer on a local network; we only read public websites; "
                        + _ASK_CLIENT_EN),
    "refused_by_site": ("الموقع طالب إن البرامج ما تقراهوش؛ " + _ASK_CLIENT_AR,
                        "the site asks programs not to read it; " + _ASK_CLIENT_EN),
    "offsite_redirect": ("الموقع بيحوّل على {url}؛ نستخدمه؟",
                         "the site redirects to {url}; use it?"),
    "certificate": ("جهازك ما قدرش يتأكد من شهادة أمان الموقع. لو الموقع بيفتح عادي في المتصفح: اتأكد إن تاريخ "
                    "وساعة الجهاز مظبوطين وجرّب تاني؛ لو لسه، قول لـ Claude «الموقع مش بيتقري» (أو من زرار Feedback "
                    "في البانل بعد المرحلة ٦)، وفي الوقت ده " + _ASK_CLIENT_AR,
                    "this computer couldn't verify the site's security certificate. If the site opens in your "
                    "browser: check the computer's date and time and try again; if it still fails, tell Claude «the "
                    "site can't be read» (or use the panel's Feedback button after Phase 6), and meanwhile "
                    + _ASK_CLIENT_EN),
    "network": ("مش قادرين نوصل للموقع دلوقتي؛ اتأكد من النت وجرّب تاني، أو " + _ASK_CLIENT_AR,
                "we can't reach the site right now; check the internet connection and try again, or "
                + _ASK_CLIENT_EN),
    "proxy_login": ("البروكسي محتاج تسجيل دخول؛ " + _ASK_CLIENT_AR,
                    "the proxy needs a login; " + _ASK_CLIENT_EN),
    "setup_needed": ("جزء قراءة المواقع ناقص من التثبيت؛ شغّل reel setup وجرّب تاني",
                     "the website reader is missing from the install; run reel setup and try again"),
    "downgrade": ("الموقع بيحوّل من اتصال آمن (https) لاتصال مش آمن، فوقفنا؛ " + _ASK_CLIENT_AR,
                  "the site redirects from a secure (https) connection to an insecure one, so we stopped; "
                  + _ASK_CLIENT_EN),
    "run_bytes": ("وصلنا لأقصى حجم تحميل للمرة الواحدة (150 ميجا) فوقفنا؛ اللي اتجاب لحد هنا موجود",
                  "we reached the download limit for one run (150 MB) and stopped; what was read so far is kept"),
    "run_seconds": ("وصلنا لأقصى وقت للمرة الواحدة (3 دقايق) فوقفنا؛ اللي اتجاب لحد هنا موجود",
                    "we reached the time limit for one run (3 minutes) and stopped; what was read so far is kept"),
    "proxy_refused": ("البروكسي بتاع الشبكة رافض يوصّلنا للموقع ده؛ لو اللينك بيبدأ بـ http جرّبه بـ https، أو "
                      + _ASK_CLIENT_AR,
                      "the network's proxy refuses to connect us to this site; if the link starts with http, try it "
                      "with https, or " + _ASK_CLIENT_EN),
}


class FetchStop(Exception):
    """The run (or its home page) can't go on: one line in the report, with one fix."""

    def __init__(self, code: str, url: str | None = None, detail: str = ""):
        self.code, self.url, self.detail = code, url, detail
        ar, en = MESSAGES.get(code, MESSAGES["network"])
        self.message_ar = ar.replace("{url}", url or "")
        self.message_en = en.replace("{url}", url or "")
        super().__init__(f"{code}: {self.message_en}")


class CertificateFailed(Exception):
    pass


class ProxyLoginNeeded(Exception):
    pass


class ProxyRefused(Exception):
    """The proxy answered the CONNECT with something other than 200 or 407."""


class _Truncated(Exception):
    pass


class _CapHit(Exception):
    def __init__(self, cap):
        self.cap = cap


class _BadEncoding(Exception):
    pass


class RawResponse:
    """One HTTP answer from a transport: no redirects followed, the body not read yet."""

    def __init__(self, status: int, headers: dict, stream, close=None, sock=None):
        self.status = int(status)
        self.headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        self.stream = stream
        self._close = close
        self._sock = sock

    def read_chunk(self, n: int, timeout: float | None = None) -> bytes:
        """What has arrived (never "wait for n bytes"), waiting at most `timeout` seconds for it. The timeout is set
        before every read: on Windows nothing else can wake a read that is already waiting."""
        if self._sock is not None and timeout is not None:
            try:
                self._sock.settimeout(max(0.05, timeout))
            except OSError:
                pass
        r1 = getattr(self.stream, "read1", None)
        return r1(n) if r1 else self.stream.read(n)

    def close(self):
        try:
            if self._close:
                self._close()
        except Exception:
            pass


class Result:
    __slots__ = ("url", "final_url", "kind", "status", "headers", "body", "sha256", "outcome", "reason", "depth")

    def __init__(self, url, kind, outcome, reason="", status=None, final_url=None, headers=None, body=None, depth=1):
        self.url, self.kind, self.outcome, self.reason = url, kind, outcome, reason
        self.status, self.final_url, self.headers, self.body = status, final_url or url, headers or {}, body
        self.sha256 = hashlib.sha256(body).hexdigest() if body is not None else None
        self.depth = depth

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"

    def __repr__(self):
        return f"Result({self.kind} {self.url} {self.outcome} {self.reason} {self.status})"


# ------------------------------------------------------------------------------------------------------- URLs
def _host_of(p) -> str:
    try:
        return (p.hostname or "").rstrip(".")
    except ValueError:
        return ""


def _encode_host(host: str) -> str:
    host = host.strip().rstrip(".").lower()
    if not host:
        raise ValueError("empty host")
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        host = host.encode("idna").decode("ascii")
    labels = host.split(".")
    if len(host) > 253 or not all(_LABEL.match(lb) for lb in labels):
        raise ValueError("bad_host")
    return host


def _quote_part(s: str, safe: str) -> str:
    s = quote(s, safe=safe + "%")
    return re.sub(r"%(?![0-9A-Fa-f]{2})", "%25", s)


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 5.2.4, with %2e treated as a dot, so `/a/%2e%2E/b` can't step around robots or the path scope."""
    segs = path.split("/")
    out = []
    for i, seg in enumerate(segs):
        s = seg.replace("%2e", ".").replace("%2E", ".")
        last = i == len(segs) - 1
        if s == ".":
            if last:
                out.append("")
        elif s == "..":
            if len(out) > 1:
                out.pop()
            if last:
                out.append("")
        else:
            out.append(seg)
    res = "/".join(out)
    return res if res.startswith("/") else "/" + res


def normalize(url: str) -> str:
    """Absolute http(s) URL in one form: scheme and host in lower case (IDN → punycode), default port dropped, dot
    segments removed, non-ASCII path and query percent-encoded as UTF-8, fragment removed. ValueError otherwise."""
    p = urlsplit(url.strip())
    scheme = p.scheme.lower()
    if scheme not in _DEFAULT_PORT:
        raise ValueError("scheme")
    if p.username is not None or p.password is not None:
        raise ValueError("credentials")
    raw_host = _host_of(p)
    if not raw_host:
        raise ValueError("host")
    try:
        port = p.port
    except ValueError:
        raise ValueError("port") from None
    kind, val = netcheck.classify_host(raw_host)
    if kind == "bad":
        raise ValueError("bad_host")
    host = val if kind == "ip" else _encode_host(raw_host)
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != _DEFAULT_PORT[scheme]:
        netloc += f":{port}"
    path = _remove_dot_segments(_quote_part(p.path or "/", "/:@!$&'()*+,;=-._~"))
    query = _quote_part(p.query, "/?:@!$&'()*+,;=-._~")
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_start(text: str) -> tuple:
    """(url, insecure) for what the editor typed: a missing scheme gets https://, a typed http:// is kept (insecure)."""
    t = (text or "").strip()
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", t) or re.match(r"^[^/:]+:\d+(/|$)", t):
        t = "https://" + t
    try:
        url = normalize(t)
    except (ValueError, UnicodeError):
        raise FetchStop("bad_url") from None
    return url, url.startswith("http://")


def _port(p) -> int:
    return p.port or _DEFAULT_PORT[p.scheme]


def _twin(a: str, b: str) -> bool:
    if a == b:
        return True
    return a == "www." + b or b == "www." + a


def _refusal(e: Exception) -> str:
    return str(e) if str(e) in ("credentials", "port", "bad_host") else "scheme"


class Scope:
    """Which URLs are pages of the start site, and which sub-resources may be read (J2.1)."""

    def __init__(self, start_url: str, same_host_only: bool = False):
        p = urlsplit(start_url)
        self.scheme = p.scheme
        self.host = _host_of(p)
        self.typed_port = p.port
        path = p.path or "/"
        self.prefix = "" if path in ("", "/") else path.rstrip("/")
        self.same_host_only = same_host_only

    def upgrade(self):
        """The site moved us to https: from now on http is a downgrade."""
        self.scheme = "https"

    def is_site_host(self, host: str) -> bool:
        return _twin(host, self.host)

    def _common(self, url):
        try:
            u = normalize(url)
        except ValueError as e:
            return None, _refusal(e)
        except UnicodeError:
            return None, "bad_host"
        p = urlsplit(u)
        if self.scheme == "https" and p.scheme == "http":
            return None, "downgrade"
        return p, ""

    def page_ok(self, url: str, alternate: bool = False) -> tuple:
        p, why = self._common(url)
        if p is None:
            return False, why
        if not self.is_site_host(_host_of(p)):
            return False, "offsite"
        if self.typed_port:
            if _port(p) != self.typed_port:
                return False, "port"
        elif p.port is not None and p.port != _DEFAULT_PORT[p.scheme]:
            return False, "port"
        if self.prefix and not alternate:
            path = p.path or "/"
            if not (path == self.prefix or path.startswith(self.prefix + "/")):
                return False, "out_of_scope"
        return True, ""

    def resource_ok(self, url: str) -> tuple:
        p, why = self._common(url)
        if p is None:
            return False, why
        site = self.is_site_host(_host_of(p))
        if self.same_host_only and not site:
            return False, "same_host_only"
        if site and self.typed_port:
            if _port(p) != self.typed_port:
                return False, "port"
        elif p.port is not None and p.port != _DEFAULT_PORT[p.scheme]:
            return False, "port"
        return True, ""


# -------------------------------------------------------------------------------------------------- transports
class FixtureTransport:
    """URL → canned answer, for tests and evals only (transport_from_env honours it only inside the test sandbox).

    spec = {"dns": {host: [ip, …]}, "routes": {url: route}}; a route is {"status", "headers", "body" (text) or
    "body_bytes" or "file" (relative to `base`)} or {"raise": "certificate" | "proxy_login" | "reset" | "timeout"}.
    A URL with no route answers 404; a host with no DNS entry does not resolve."""

    def __init__(self, spec: dict, base: Path | None = None):
        self.dns = {k.lower(): list(v) for k, v in (spec.get("dns") or {}).items()}
        self.routes = dict(spec.get("routes") or {})
        self.base = Path(base) if base else None
        self.requests = []
        self.read_bytes = {}

    @classmethod
    def from_dir(cls, d) -> "FixtureTransport":
        d = Path(d)
        return cls(json.loads((d / "routes.json").read_text(encoding="utf-8")), d)

    def resolve(self, host: str, port: int) -> list:
        ips = self.dns.get(host.lower())
        if not ips:
            raise OSError(f"fixture: no address for {host}")
        return ips

    def send(self, method, url, headers, ip, connect_timeout, read_timeout, deadline=None) -> RawResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "ip": ip})
        route = self.routes.get(url)
        if route is None:
            return RawResponse(404, {"content-type": "text/plain"}, io.BytesIO(b""))
        err = route.get("raise")
        if err == "certificate":
            raise CertificateFailed("fixture certificate failure")
        if err == "proxy_login":
            raise ProxyLoginNeeded("fixture 407")
        if err == "proxy_refused":
            raise ProxyRefused("fixture 403")
        if err == "timeout":
            raise socket.timeout("fixture timeout")
        if err:
            raise ConnectionResetError("fixture reset")
        if "body_bytes" in route:
            body = route["body_bytes"]
        elif "file" in route:
            body = (self.base / route["file"]).read_bytes()
        else:
            body = str(route.get("body", "")).encode("utf-8")
        counts = self.read_bytes

        class _Counting(io.BytesIO):
            def read(self, n=-1):
                b = super().read(n)
                counts[url] = counts.get(url, 0) + len(b)
                return b

            def read1(self, n=-1):
                return self.read(n)
        return RawResponse(route.get("status", 200), route.get("headers") or {}, _Counting(body))


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Plain HTTP to an address we checked (or through a CONNECT tunnel to it)."""


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS to an address we checked (or through a CONNECT tunnel to it), with the host name kept for SNI and the
    certificate check."""

    def __init__(self, host, port=None, *, sni: str, context, timeout):
        super().__init__(host, port, timeout=timeout, context=context)
        self._sni = sni

    def connect(self):
        http.client.HTTPConnection.connect(self)          # TCP to the address (or the proxy) + CONNECT when tunnelled
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self._sni)


def tls_context():
    """The OS trust store (truststore): CryptoAPI on Windows, Security.framework / Keychain on macOS (J2.3)."""
    try:
        import truststore
    except ImportError:
        raise FetchStop("setup_needed") from None
    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def doctor_status() -> dict:
    """The `reel doctor` line (J2.3): can this runtime check certificates with the system trust store?"""
    if importlib.util.find_spec("truststore") is not None:
        return {"ok": True, "line_ar": "قراءة المواقع: شهادات الجهاز متاحة",
                "line_en": "website reading: system certificates available", "fix": ""}
    return {"ok": False, "line_ar": "قراءة المواقع: شهادات الجهاز ناقصة ← شغّل reel setup",
            "line_en": "website reading: system certificates missing → reel setup", "fix": "reel setup"}


def _pac_windows(reg) -> tuple:
    """(PAC script URL or None, "Automatically detect settings" on)."""
    vals = reg() or {}
    url = str(vals.get("AutoConfigURL") or "").strip() or None
    blob = vals.get("DefaultConnectionSettings")
    auto = isinstance(blob, (bytes, bytearray)) and len(blob) > 8 and bool(blob[8] & 0x08)
    return url, auto


def _win_reg_values() -> dict:
    import winreg
    out = {}
    base = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    for sub, name in ((base, "AutoConfigURL"), (base + r"\Connections", "DefaultConnectionSettings")):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
                out[name] = winreg.QueryValueEx(k, name)[0]
        except OSError:
            pass
    return out


def _scutil_proxy() -> str:
    r = subprocess.run(["/usr/sbin/scutil", "--proxy"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       timeout=5, check=False)
    return r.stdout.decode("utf-8", "replace")


def _pac_macos(scutil) -> tuple:
    out = scutil()
    url = None
    if re.search(r"ProxyAutoConfigEnable\s*:\s*1", out):
        m = re.search(r"ProxyAutoConfigURLString\s*:\s*(\S+)", out)
        url = m.group(1) if m else "pac"
    return url, bool(re.search(r"ProxyAutoDiscoveryEnable\s*:\s*1", out))


class ProxyConfig:
    """The system proxy (J2.2): static http proxies only; the bypass list honoured; a PAC script is never evaluated
    (no proxy, reported); an unsupported proxy scheme (socks, https://) is ignored and reported. "Detect settings
    automatically" (WPAD, on by default on Windows) is only recorded: the manual proxy, if any, is used as set."""

    def __init__(self, proxies: dict, bypass, pac: str | None, auto_detect: bool = False):
        self.proxies = dict(proxies or {})
        self.bypass = bypass
        self.pac = pac
        self.auto_detect = auto_detect
        self.pac_ignored = False
        self.unsupported = None

    @classmethod
    def none(cls) -> "ProxyConfig":
        return cls({}, lambda h: False, None)

    @classmethod
    def system(cls, platform: str | None = None, getproxies=None, bypass=None, win_reg=None, scutil=None):
        import urllib.request
        platform = platform or sys.platform
        getproxies = getproxies or urllib.request.getproxies
        bypass = bypass or urllib.request.proxy_bypass
        pac, auto = None, False
        try:
            if platform == "win32":
                pac, auto = _pac_windows(win_reg or _win_reg_values)
            elif platform == "darwin":
                pac, auto = _pac_macos(scutil or _scutil_proxy)
        except Exception:
            pac, auto = None, False
        try:
            proxies = getproxies() or {}
        except Exception:
            proxies = {}
        return cls(proxies, bypass, pac, auto)

    def for_url(self, scheme: str, host: str):
        if self.pac:
            self.pac_ignored = True
            return None
        raw = self.proxies.get(scheme)
        if not raw:
            return None
        try:
            if self.bypass(host):
                return None
        except Exception:
            pass
        if "://" not in raw:
            raw = "http://" + raw
        p = urlsplit(raw)
        if p.scheme.lower() != "http" or not p.hostname:
            self.unsupported = p.scheme.lower() or "unknown"
            return None
        try:
            port = p.port or 80
        except ValueError:
            self.unsupported = "bad_port"
            return None
        return (p.hostname, port)


class RealTransport:
    """http.client to the checked address, through a CONNECT tunnel when the system proxy applies. The run's time is
    enforced twice: every body read waits at most min(read timeout, time left) (RawResponse.read_chunk), and a
    watchdog shuts the socket at the deadline (this wakes a waiting read on macOS; on Windows the per-read timeout is
    what ends it). Known limit: while the status line and headers arrive, one timeout covers the whole header read,
    so a server dripping header bytes can hold a request up to the read timeout (20 s) past the run's 180 s."""

    def __init__(self, proxy: ProxyConfig | None = None, tls=tls_context, http_conn=_PinnedHTTPConnection,
                 https_conn=_PinnedHTTPSConnection):
        self.proxy = proxy if proxy is not None else ProxyConfig.system()
        self.tls = tls
        self.http_conn = http_conn
        self.https_conn = https_conn

    def send(self, method, url, headers, ip, connect_timeout, read_timeout, deadline=None) -> RawResponse:
        p = urlsplit(url)
        host = _host_of(p)
        port = _port(p)
        target = (p.path or "/") + (("?" + p.query) if p.query else "")
        hostport = (f"[{host}]" if ":" in host else host) + (f":{p.port}" if p.port else "")
        via = self.proxy.for_url(p.scheme, host)
        if p.scheme == "https":
            ctx = self.tls()
            conn = self.https_conn(via[0] if via else ip, via[1] if via else port, sni=host, context=ctx,
                                   timeout=connect_timeout)
        else:
            conn = self.http_conn(via[0] if via else ip, via[1] if via else port, timeout=connect_timeout)
        if via:
            conn.set_tunnel(ip, port)
        held = {"sock": None, "resp": None}            # the socket outlives conn.sock once the reply says "close"
        timer = None
        if deadline is not None:
            def _kill():
                s = held["sock"] or getattr(conn, "sock", None)
                try:
                    if s is not None:
                        s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            timer = threading.Timer(max(0.0, deadline), _kill)
            timer.daemon = True
            timer.start()

        def _close():
            if timer:
                timer.cancel()
            if held["resp"] is not None:
                try:
                    held["resp"].close()
                except Exception:
                    pass
            conn.close()
        try:
            conn.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", hostport)
            for k, v in headers.items():
                conn.putheader(k, v)
            conn.endheaders()
            held["sock"] = getattr(conn, "sock", None)
            if held["sock"] is not None:
                held["sock"].settimeout(read_timeout)
            resp = conn.getresponse()
            held["resp"] = resp
        except ssl.SSLCertVerificationError as e:
            _close()
            raise CertificateFailed(str(e)) from None
        except OSError as e:
            _close()
            if via and "Tunnel connection failed" in str(e):
                if re.search(r"\b407\b", str(e)):
                    raise ProxyLoginNeeded(str(e)) from None
                if not re.search(r":\s*5\d\d\b", str(e)):     # a 5xx is the site being down, not a refusal
                    raise ProxyRefused(str(e)) from None
            raise
        except BaseException:
            _close()
            raise
        return RawResponse(resp.status, dict(resp.getheaders()), resp, _close, sock=held["sock"])


def _system_resolver(host: str, port: int) -> list:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    out = []
    for info in infos:
        ip = info[4][0]
        if ip not in out:
            out.append(ip)
    return out


def transport_from_env(env=None):
    """(transport, resolver, sleep). `WHYNOT_BRAND_TRANSPORT=fixture:<dir>` is honoured ONLY when WHYNOT_TEST_SANDBOX
    is also set (tests and evals), so it can never redirect a real fetch; fixture runs use zero gaps."""
    env = os.environ if env is None else env
    sw = env.get("WHYNOT_BRAND_TRANSPORT", "")
    if env.get("WHYNOT_TEST_SANDBOX") and sw.startswith("fixture:"):
        t = FixtureTransport.from_dir(sw[len("fixture:"):])
        return t, t.resolve, (lambda s: None)
    return RealTransport(), _system_resolver, time.sleep


# ----------------------------------------------------------------------------------------------------- fetcher
class Fetcher:
    """One website run: scope, addresses, robots, caps, pacing and the fetch log."""

    def __init__(self, start_url: str, *, transport, resolver, max_pages: int | None = None,
                 same_host_only: bool = False, clock=time.monotonic, sleep=time.sleep, log_path=None,
                 ip_ok=netcheck.ip_ok, min_gap: float | None = None, caps: dict | None = None):
        self.start_url, self.insecure = normalize_start(start_url)
        self.scope = Scope(self.start_url, same_host_only)
        self.transport, self.resolver = transport, resolver
        self.caps = dict(CAPS, **(caps or {}))
        mp = self.caps["pages_default"] if max_pages is None else int(max_pages)
        self.max_pages = max(1, min(mp, self.caps["pages_max"]))
        self.clock, self.sleep = clock, sleep
        self.log_path = Path(log_path) if log_path else None
        self.ip_ok = ip_ok
        self.min_gap = self.caps["host_gap"] if min_gap is None else float(min_gap)
        self.t0 = clock()
        self.bytes = 0
        self.stopped = None
        self.counts = {}
        self.cache = {}
        self.robots = {}
        self.last = {}
        self.delay = {}
        self.dead_hosts = {}                      # host → reason (certificate)
        self.external_links = []
        self.hosts_read = set()

    def notes(self) -> list:
        """Things the report should say about how the site was read."""
        out = []
        if self.insecure and self.scope.scheme == "http":
            out.append("insecure_start")
        proxy = getattr(self.transport, "proxy", None)
        if proxy is not None and getattr(proxy, "pac_ignored", False):
            out.append("pac_ignored")
        if proxy is not None and getattr(proxy, "unsupported", None):
            out.append("proxy_unsupported")
        return out

    # ---- log
    def _log(self, **e):
        if not self.log_path:
            return
        row = {"url": e.get("url"), "host": e.get("host"), "kind": e.get("kind"), "status": e.get("status"),
               "bytes": e.get("bytes", 0), "sha256": e.get("sha256"), "robots": e.get("robots", "n/a"),
               "ms": e.get("ms", 0), "outcome": e.get("outcome"), "reason": e.get("reason", "")}
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _done(self, r: Result, robots_state="n/a", ms=0, host=None) -> Result:
        self._log(url=r.url, host=host or _host_of(urlsplit(r.url)), kind=r.kind, status=r.status,
                  bytes=len(r.body) if r.body is not None else 0, sha256=r.sha256, robots=robots_state, ms=ms,
                  outcome=r.outcome, reason=r.reason)
        return r

    # ---- checks
    def _remaining(self) -> float:
        return self.caps["run_seconds"] - (self.clock() - self.t0)

    def _time_left(self, margin: float = 0.0) -> bool:
        """False (and the run stops) once the time cap is reached; `margin` covers a read that timed out on the
        deadline a few milliseconds early."""
        if self._remaining() < margin:
            self.stopped = self.stopped or "run_seconds"
            return False
        return True

    def _addresses(self, host: str, port: int) -> tuple:
        """([checked ips], "") or ([], reason)."""
        kind, val = netcheck.classify_host(host)
        if kind == "bad":
            return [], "bad_host"
        if kind == "ip":
            return ([val], "") if self.ip_ok(val) else ([], "private_address")
        try:
            ips = list(self.resolver(host, port))
        except (OSError, UnicodeError):
            return [], "unreachable"
        if not ips:
            return [], "unreachable"
        if not all(self.ip_ok(ip) for ip in ips):
            return [], "private_address"
        return ips, ""

    def _pace(self, host: str):
        gap = max(self.min_gap, self.delay.get(host, 0.0))
        last = self.last.get(host)
        if last is not None and gap > 0:
            wait = last + gap - self.clock()
            if wait > 0:
                self.sleep(wait)
        self.last[host] = self.clock()

    def _headers(self, kind: str) -> dict:
        accept = {"page": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5", "css": "text/css,*/*;q=0.1",
                  "robots": "text/plain,*/*;q=0.1"}.get(kind, "*/*")
        return {"User-Agent": USER_AGENT, "Accept": accept, "Accept-Encoding": "gzip", "Connection": "close"}

    def _read(self, raw: RawResponse, cap_name: str | None, cap: int, truncate: bool = False) -> bytes:
        enc = raw.headers.get("content-encoding", "").strip().lower()
        if enc not in ("", "identity", "gzip", "x-gzip"):
            raise _BadEncoding(enc)
        clen = raw.headers.get("content-length", "")
        if not enc.endswith("gzip") and clen.isdigit() and int(clen) > cap and not truncate:
            raise _CapHit(cap_name)
        d = zlib.decompressobj(31) if enc.endswith("gzip") else None
        out = bytearray()

        def take(data: bytes):
            self.bytes += len(data)
            if self.bytes > self.caps["run_bytes"]:
                self.stopped = self.stopped or "run_bytes"
                raise _CapHit("run_bytes")
            out.extend(data)

        while True:
            if not self._time_left():
                raise _CapHit("run_seconds")
            try:
                chunk = raw.read_chunk(_CHUNK, min(self.caps["read_timeout"], self._remaining()))
            except (OSError, ValueError, http.client.HTTPException):
                if not self._time_left(0.1):
                    raise _CapHit("run_seconds") from None
                raise
            if not chunk:
                if d is None and clen.isdigit() and len(out) != int(clen) and \
                        "transfer-encoding" not in raw.headers:       # chunked: Content-Length doesn't apply
                    raise _Truncated()                # read1 returns b"" when the server closes early
                break
            if d is None:
                take(chunk)
            else:
                try:
                    take(d.decompress(chunk, cap + 1 - len(out)))
                    while d.unconsumed_tail and len(out) <= cap:
                        take(d.decompress(d.unconsumed_tail, cap + 1 - len(out)))
                except zlib.error:
                    raise _BadEncoding("gzip") from None
            if len(out) > cap:
                if truncate:
                    return bytes(out[:cap])
                raise _CapHit(cap_name)
        if d is not None:
            try:
                take(d.flush())
            except zlib.error:
                raise _BadEncoding("gzip") from None
            if not d.eof:
                raise _BadEncoding("gzip")
            if len(out) > cap:
                if truncate:
                    return bytes(out[:cap])
                raise _CapHit(cap_name)
        return bytes(out)

    def _send(self, url: str, kind: str, ip: str) -> RawResponse:
        """One request. ProxyLoginNeeded stops the run (every request goes through that proxy)."""
        host = _host_of(urlsplit(url))
        self._pace(host)
        left = self._remaining()
        if left <= 0:                                 # the pacing sleep used up the run's time: no request
            self.stopped = self.stopped or "run_seconds"
            raise _CapHit("run_seconds")
        self.hosts_read.add(host)
        try:
            return self.transport.send("GET", url, self._headers(kind), ip, min(self.caps["connect_timeout"], left),
                                       min(self.caps["read_timeout"], left), deadline=left)
        except ProxyLoginNeeded:
            self.stopped = self.stopped or "proxy_login"
            raise
        except (OSError, http.client.HTTPException):
            if not self._time_left(0.1):
                raise _CapHit("run_seconds") from None
            raise

    def _send_any(self, url: str, kind: str, ips: list) -> RawResponse:
        """Try each checked address in turn; a connection that can't be made moves on, anything else is final."""
        last = None
        for ip in ips:
            try:
                return self._send(url, kind, ip)
            except (ConnectionRefusedError, ConnectionAbortedError, socket.gaierror) as e:
                last = e
            except OSError as e:
                if isinstance(e, (socket.timeout, ConnectionResetError)) or not self._time_left():
                    raise
                last = e
        raise last or OSError("no address")

    # ---- robots
    def _robots_for(self, url: str):
        p = urlsplit(url)
        key = (p.scheme, _host_of(p), _port(p))
        if key in self.robots:
            return self.robots[key]
        rules = self._load_robots(p)
        self.robots[key] = rules
        if rules.crawl_delay is not None:
            self.delay[key[1]] = min(rules.crawl_delay, self.caps["crawl_delay_max"])
        return rules

    def _load_robots(self, p):
        origin_host, origin_port = _host_of(p), _port(p)
        url = urlunsplit((p.scheme, p.netloc, "/robots.txt", "", ""))
        for _hop in range(self.caps["redirects"] + 1):
            q = urlsplit(url)
            host = _host_of(q)
            ips, why = self._addresses(host, _port(q))
            if not ips:
                self._done(Result(url, "robots", "error", why), host=host)
                return robots.deny_all("unreachable")
            if not self._time_left():
                return robots.deny_all("unreachable")
            t1 = self.clock()
            try:
                raw = self._send_any(url, "robots", ips)
            except CertificateFailed:
                self.dead_hosts[origin_host] = "certificate"
                self._done(Result(url, "robots", "error", "certificate"), host=host)
                return robots.deny_all("certificate")
            except ProxyLoginNeeded:
                self._done(Result(url, "robots", "stopped", "proxy_login"), host=host)
                return robots.deny_all("unreachable")
            except ProxyRefused:
                self._done(Result(url, "robots", "error", "proxy_refused"), host=host)
                return robots.deny_all("proxy_refused")
            except _CapHit:
                return robots.deny_all("unreachable")
            except (OSError, http.client.HTTPException):
                self._done(Result(url, "robots", "error", "unreachable"), host=host)
                return robots.deny_all("unreachable")
            try:
                if raw.status in _REDIRECT:
                    self._done(Result(url, "robots", "redirect", "", status=raw.status), host=host)
                    try:
                        nxt = normalize(urljoin(url, raw.headers.get("location", "")))
                    except (ValueError, UnicodeError):
                        return robots.deny_all("unreachable")
                    nq = urlsplit(nxt)
                    if not _twin(_host_of(nq), origin_host) or (p.scheme == "https" and nq.scheme == "http") or \
                            _port(nq) not in (origin_port, _DEFAULT_PORT[nq.scheme]):
                        return robots.deny_all("unreachable")
                    url = nxt
                    continue
                if 400 <= raw.status < 500:
                    self._done(Result(url, "robots", "ok", "4xx", status=raw.status), host=host)
                    return robots.allow_all("4xx")
                if not (200 <= raw.status < 300):
                    self._done(Result(url, "robots", "error", "http_status", status=raw.status), host=host)
                    return robots.deny_all("5xx")
                try:
                    cap = self.caps["robots_bytes"]
                    body = self._read(raw, "robots_bytes", cap, truncate=True)
                    if len(body) >= cap:                  # a cut rule must not turn a ban into permission
                        end = max(body.rfind(b"\n"), body.rfind(b"\r"))
                        if end < 0:
                            self._done(Result(url, "robots", "error", "robots_bytes", status=raw.status), host=host)
                            return robots.deny_all("unreachable")
                        body = body[: end + 1]
                except (_BadEncoding, _CapHit, _Truncated, OSError, ValueError, http.client.HTTPException):
                    self._done(Result(url, "robots", "error", "unreachable", status=raw.status), host=host)
                    return robots.deny_all("unreachable")
                self._done(Result(url, "robots", "ok", "", status=raw.status, body=body), host=host,
                           ms=int((self.clock() - t1) * 1000))
                return robots.parse(body.decode("utf-8", "replace"))
            finally:
                raw.close()
        return robots.deny_all("unreachable")

    def _robots_ok(self, url: str, pinned: bool) -> tuple:
        p = urlsplit(url)
        if pinned and _host_of(p) == PINNED_FONT_HOST and p.scheme == "https" and p.path.startswith(PINNED_FONT_PREFIX):
            return True, "exempt"
        rules = self._robots_for(url)
        path = (p.path or "/") + (("?" + p.query) if p.query else "")
        ok = rules.allowed(path)
        return ok, ("allowed" if ok else "disallowed")

    # ---- the main entry points
    def fetch_home(self) -> Result:
        r = self._fetch(self.start_url, "page", 0, False, False, home=True)
        if r.ok:
            if urlsplit(r.final_url).scheme == "https":
                self.scope.upgrade()
            return r
        if self.stopped in _RUN_STOPS:
            raise FetchStop(self.stopped)
        reason = r.reason
        if reason == "robots":
            rules = self._robots_for(r.final_url or self.start_url)
            if rules.source in ("certificate", "proxy_refused"):
                raise FetchStop(rules.source)
            raise FetchStop("refused_by_site" if rules.source == "file" else "network")
        if reason in ("private_address", "certificate", "downgrade", "proxy_refused"):
            raise FetchStop(reason)
        if reason in ("bad_host", "scheme", "credentials", "port"):
            raise FetchStop("bad_url")
        raise FetchStop("network")

    def fetch(self, url: str, kind: str, *, depth: int = 1, alternate: bool = False, pinned: bool = False) -> Result:
        if kind not in KIND_ORDER:
            raise ValueError(f"unknown kind {kind!r}")
        try:
            return self._fetch(url, kind, depth, alternate, pinned)
        except FetchStop as e:                    # only the home page's off-site move raises; never from here
            return self._done(Result(url, kind, "refused", e.code, final_url=e.url or url, depth=depth))

    def run_queue(self, items) -> list:
        order = {k: i for i, k in enumerate(KIND_ORDER)}
        todo = sorted(enumerate(items), key=lambda x: (order[x[1][1]], x[0]))
        out = []
        for _i, item in todo:
            url, kind = item[0], item[1]
            depth = item[2] if len(item) > 2 else 1
            out.append(self.fetch(url, kind, depth=depth))
        return out

    def _fetch(self, url, kind, depth, alternate, pinned, home=False) -> Result:
        try:
            nurl = normalize(url)
        except ValueError as e:
            return self._done(Result(url, kind, "refused", _refusal(e), depth=depth))
        except UnicodeError:
            return self._done(Result(url, kind, "refused", "bad_host", depth=depth))
        why = self._check(nurl, kind, depth, alternate)
        if why:                                   # scope and depth refusals are never cached
            return self._done(Result(nurl, kind, "refused", why, depth=depth))
        key = (nurl, kind)
        if key in self.cache:
            return self.cache[key]
        r = self._fetch_new(nurl, kind, depth, alternate, pinned, home)
        if r.outcome != "stopped":
            self.cache[key] = r
        return r

    def _check(self, url, kind, depth, alternate):
        if kind == "page":
            ok, why = self.scope.page_ok(url, alternate=alternate)
            if not ok and why == "offsite" and url not in self.external_links:
                self.external_links.append(url)
            return "" if ok else why
        if depth > self.caps["depth"]:
            return "depth"
        ok, why = self.scope.resource_ok(url)
        return "" if ok else why

    def _fetch_new(self, url, kind, depth, alternate, pinned, home) -> Result:
        if self.stopped:
            return self._done(Result(url, kind, "stopped", self.stopped, depth=depth))
        cname = _COUNT_CAP[kind]
        limit = self.max_pages if kind == "page" else self.caps[cname]
        if self.counts.get(kind, 0) >= limit:
            return self._done(Result(url, kind, "cap", cname, depth=depth))
        counted = False                           # a refusal before any request (robots, address) costs no budget
        cur = url
        for _hop in range(self.caps["redirects"] + 1):
            if not self._time_left():
                return self._done(Result(url, kind, "stopped", "run_seconds", depth=depth))
            p = urlsplit(cur)
            host = _host_of(p)
            if host in self.dead_hosts:
                return self._done(Result(url, kind, "refused", self.dead_hosts[host], final_url=cur, depth=depth))
            ips, why = self._addresses(host, _port(p))
            if not ips:
                outcome = "error" if why == "unreachable" else "refused"
                return self._done(Result(url, kind, outcome, why, final_url=cur, depth=depth), host=host)
            allowed, rstate = self._robots_ok(cur, pinned)
            if self.stopped:
                return self._done(Result(url, kind, "stopped", self.stopped, depth=depth))
            if host in self.dead_hosts:
                return self._done(Result(url, kind, "refused", self.dead_hosts[host], final_url=cur, depth=depth))
            if not allowed:
                return self._done(Result(url, kind, "refused", "robots", final_url=cur, depth=depth), rstate,
                                  host=host)
            if not counted:
                self.counts[kind] = self.counts.get(kind, 0) + 1
                counted = True
            t1 = self.clock()
            try:
                raw = self._send_any(cur, kind, ips)
            except CertificateFailed:
                self.dead_hosts[host] = "certificate"
                return self._done(Result(url, kind, "error", "certificate", final_url=cur, depth=depth), rstate,
                                  host=host)
            except ProxyLoginNeeded:
                return self._done(Result(url, kind, "stopped", "proxy_login", final_url=cur, depth=depth), rstate,
                                  host=host)
            except ProxyRefused:
                return self._done(Result(url, kind, "error", "proxy_refused", final_url=cur, depth=depth), rstate,
                                  host=host)
            except _CapHit as c:
                return self._done(Result(url, kind, "stopped", c.cap, final_url=cur, depth=depth), rstate, host=host)
            except socket.timeout:
                return self._done(Result(url, kind, "error", "timeout", final_url=cur, depth=depth), rstate, host=host)
            except (OSError, http.client.HTTPException):
                return self._done(Result(url, kind, "error", "unreachable", final_url=cur, depth=depth), rstate,
                                  host=host)
            try:
                if raw.status in _REDIRECT:
                    self._done(Result(cur, kind, "redirect", "", status=raw.status, depth=depth), rstate, host=host)
                    nxt, why = self._next_hop(cur, raw.headers.get("location", ""), kind, alternate)
                    if why:
                        if home and why in ("offsite_redirect", "port", "out_of_scope"):
                            raise FetchStop("offsite_redirect", url=nxt)
                        return self._done(Result(url, kind, "refused", why, final_url=nxt or cur, depth=depth))
                    cur = nxt
                    continue
                if not (200 <= raw.status < 300):
                    return self._done(Result(url, kind, "error", "http_status", status=raw.status, final_url=cur,
                                             depth=depth), rstate, host=host)
                cap_name = _BYTES_CAP[kind]
                try:
                    body = self._read(raw, cap_name, self.caps[cap_name])
                except _CapHit as c:
                    return self._done(Result(url, kind, "cap", c.cap, status=raw.status, final_url=cur, depth=depth),
                                      rstate, host=host)
                except _BadEncoding:
                    return self._done(Result(url, kind, "error", "bad_encoding", status=raw.status, final_url=cur,
                                             depth=depth), rstate, host=host)
                except _Truncated:
                    return self._done(Result(url, kind, "error", "truncated", status=raw.status, final_url=cur,
                                             depth=depth), rstate, host=host)
                except socket.timeout:
                    return self._done(Result(url, kind, "error", "timeout", status=raw.status, final_url=cur,
                                             depth=depth), rstate, host=host)
                except (OSError, ValueError, http.client.HTTPException):
                    return self._done(Result(url, kind, "error", "unreachable", status=raw.status, final_url=cur,
                                             depth=depth), rstate, host=host)
                return self._done(Result(url, kind, "ok", "", status=raw.status, final_url=cur, headers=raw.headers,
                                         body=body, depth=depth), rstate, ms=int((self.clock() - t1) * 1000),
                                  host=host)
            finally:
                raw.close()
        return self._done(Result(url, kind, "refused", "redirects", final_url=cur, depth=depth))

    def _next_hop(self, cur, location, kind, alternate) -> tuple:
        """(next url, "") or (url or None, reason) for a redirect (J2.1): http(s) only, never https → http, pages stay
        on the start site and inside its path scope (the home page's off-site move becomes the editor's question)."""
        if not location:
            return None, "redirects"
        target = urljoin(cur, location.strip())
        if urlsplit(target).scheme.lower() not in _DEFAULT_PORT:
            return None, "scheme"
        try:
            nxt = normalize(target)
        except ValueError as e:
            return None, _refusal(e)
        except UnicodeError:
            return None, "bad_host"
        if urlsplit(cur).scheme == "https" and nxt.startswith("http://"):
            return nxt, "downgrade"
        if kind == "page":
            ok, why = self.scope.page_ok(nxt, alternate=alternate)
            if not ok:
                return nxt, ("offsite_redirect" if why == "offsite" else why)
        else:
            ok, why = self.scope.resource_ok(nxt)
            if not ok:
                return nxt, why
        return nxt, ""
