"""Security building blocks of the local engine daemon `reel serve` (3.0 T6.2).

Pure stdlib, no server or engine-state dependency, so the daemon, the app and the tests share one implementation:
  * `<engine home>/bridge/engine.json` (port, token, pid, version): written atomically, user-only permissions
    (POSIX chmod 0600; Windows: inheritance removed and only the current user granted, via icacls);
  * `check_host` / `check_origin`: DNS-rebinding and browser-origin defences for the HTTP/WebSocket handshake;
  * `token_ok`: constant-time token compare; `make_token`: 256-bit token;
  * `RateLimiter`: token bucket (clock injectable);
  * `AuditLog`: JSON lines, size-capped rotation, thread-safe, and it can never write the token (every field is
    redacted: the exact token value and any run of 64 or more hex characters).
The token must never appear in a URL, a log line or an error message; callers pass it in only to compare / redact.
"""
from __future__ import annotations

import getpass
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL = 4

# Origins a non-browser client (the Premiere UXP panel) may send. PROVISIONAL until spike 0.1.3 records the exact
# Origin UXP's WebSocket really sends (the spike's probe was waiting for this daemon). Every Origin seen is
# audit-logged by the caller so the spike can confirm. Browser schemes (BROWSER_SCHEMES) and "null" are always
# rejected, whatever is listed here.
ALLOWED_ORIGIN_PREFIXES = ("uxp://", "plugin:")

# A web page (or a browser extension) can reach 127.0.0.1; these origins mean "this came from a browser context".
BROWSER_SCHEMES = frozenset({"http", "https", "file", "chrome-extension", "moz-extension", "safari-web-extension",
                             "ws", "wss"})

REDACTED = "[redacted]"
_HEX_RUN = re.compile(r"[0-9a-fA-F]{64,}")
_FIELD_MAX = 500          # audit fields are clipped (after redaction) so a hostile peer cannot bloat the log


# ----------------------------------------------------------------------------------------------------------------
# token + engine.json
# ----------------------------------------------------------------------------------------------------------------
def make_token() -> str:
    """256-bit random token as 64 lowercase hex characters."""
    return secrets.token_hex(32)


def token_ok(given, expected) -> bool:
    """Constant-time compare. Anything that is not a non-empty string never authenticates; never raises."""
    if not isinstance(given, str) or not isinstance(expected, str) or not expected:
        return False
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def engine_json_path(home) -> Path:
    return Path(home) / "bridge" / "engine.json"


def audit_log_path(home) -> Path:
    return Path(home) / "logs" / "serve-audit.log"


def _windows_principal() -> str:
    user = os.environ.get("USERNAME") or getpass.getuser()
    dom = os.environ.get("USERDOMAIN")
    return f"{dom}\\{user}" if dom else user


def restrict_to_user(path) -> None:
    """Make `path` readable and writable by the current user only. Fails closed: raises OSError if it cannot."""
    p = str(path)
    if os.name != "nt":
        os.chmod(p, 0o600)
        return
    exe = shutil.which("icacls") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icacls.exe")
    try:
        r = subprocess.run([exe, p, "/inheritance:r", "/grant:r", f"{_windows_principal()}:F"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise OSError(f"icacls failed for {p}: {type(e).__name__}") from e
    if r.returncode != 0:
        raise OSError(f"icacls failed for {p} (exit {r.returncode})")


def write_engine_json(home, *, port: int, token: str, pid: int, version: str, **extra) -> Path:
    """Atomically write <home>/bridge/engine.json. The temp file is restricted BEFORE the token is written, so the
    token is never on disk under a wider ACL; on any failure the old file is untouched and the temp file removed."""
    path = engine_json_path(home)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = {"port": int(port), "token": token, "pid": int(pid), "version": version, "protocol": PROTOCOL}
    data.update(extra)
    payload = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        try:
            restrict_to_user(tmp)
            with os.fdopen(fd, "wb") as f:
                fd = -1
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
        finally:
            if fd != -1:
                os.close(fd)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    restrict_to_user(path)          # belt and braces: the final file never relies on what replace() kept
    return path


def read_engine_json(home) -> dict | None:
    """The parsed engine.json, or None when missing / unreadable / not a JSON object."""
    try:
        d = json.loads(engine_json_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def remove_engine_json(home, pid: int) -> bool:
    """Delete engine.json only when it records `pid` (a newer daemon's file is never removed by an older one)."""
    d = read_engine_json(home)
    if d is None or d.get("pid") != pid:
        return False
    try:
        engine_json_path(home).unlink()
    except OSError:
        return False
    return True


# ----------------------------------------------------------------------------------------------------------------
# Host / Origin
# ----------------------------------------------------------------------------------------------------------------
def _header(headers, name: str):
    """The single value of header `name` (case-insensitive) from a dict-like or email.message.Message; None when
    absent. A repeated header is returned as a list so callers can reject it."""
    if headers is None:
        return None
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        vals = get_all(name)
        if not vals:
            return None
        return vals[0] if len(vals) == 1 else list(vals)
    low = name.lower()
    found = [v for k, v in headers.items() if isinstance(k, str) and k.lower() == low]
    if not found:
        return None
    return found[0] if len(found) == 1 else found


def check_host(headers, port: int) -> bool:
    """Only `127.0.0.1:<port>` or `localhost:<port>` (any case): anything else is a rebinding or misrouted request.
    A missing, repeated, port-less, other-port or IPv6 Host is rejected."""
    host = _header(headers, "Host")
    if not isinstance(host, str):
        return False
    return host.lower() in (f"127.0.0.1:{int(port)}", f"localhost:{int(port)}")


def origin_rejection(headers) -> str | None:
    """None when the Origin is acceptable, else a short reason code (safe to audit-log, no values)."""
    origin = _header(headers, "Origin")
    if origin is None:
        return None            # non-browser clients send no Origin
    if not isinstance(origin, str):
        return "origin-repeated"
    low = origin.lower()
    if not origin or re.search(r"[\s\x00-\x1f\x7f]", origin):
        return "origin-malformed"
    if low == "null":
        return "origin-null"
    scheme = low.split(":", 1)[0] if ":" in low else ""
    if scheme in BROWSER_SCHEMES:
        return "origin-browser-scheme"
    if any(low.startswith(p.lower()) for p in ALLOWED_ORIGIN_PREFIXES):
        return None
    return "origin-not-allowed"


def check_origin(headers) -> bool:
    return origin_rejection(headers) is None


# ----------------------------------------------------------------------------------------------------------------
# rate limit
# ----------------------------------------------------------------------------------------------------------------
class RateLimiter:
    """Token bucket: `rate_per_s` tokens per second up to `burst`; starts full. Thread-safe."""

    def __init__(self, rate_per_s: float, burst: int, clock=time.monotonic):
        if not rate_per_s > 0 or not burst >= 1:
            raise ValueError("rate_per_s must be > 0 and burst >= 1")
        self.rate = float(rate_per_s)
        self.burst = float(burst)
        self._clock = clock
        self._tokens = self.burst
        self._last = clock()
        self._lock = threading.Lock()

    def allow(self, cost: float = 1.0) -> bool:
        with self._lock:
            now = self._clock()
            if now > self._last:                      # a clock that goes backwards mints nothing
                self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
                self._last = now
            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False


# ----------------------------------------------------------------------------------------------------------------
# audit log
# ----------------------------------------------------------------------------------------------------------------
def redact(value, token: str | None = None) -> str:
    """`value` as text with the token (exact, any case) and any run of 64+ hex characters replaced."""
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    if token:
        s = re.sub(re.escape(token), REDACTED, s, flags=re.IGNORECASE)
    return _HEX_RUN.sub(REDACTED, s)


class AuditLog:
    """JSON-lines audit log `{at, event, peer, session?, action?, outcome, reason?}` with size-capped rotation
    (path, path.1 ... path.<keep>). Thread-safe; never raises into the daemon (log() returns False on I/O failure);
    every field is redacted so the token cannot reach the file."""

    def __init__(self, path, max_bytes: int = 5 * 1024 * 1024, keep: int = 3, token: str | None = None):
        if max_bytes < 1 or keep < 1:
            raise ValueError("max_bytes and keep must be >= 1")
        self.path = Path(path)
        self.max_bytes = int(max_bytes)
        self.keep = int(keep)
        self._token = token
        self._lock = threading.Lock()

    def set_token(self, token: str | None) -> None:
        with self._lock:
            self._token = token

    def _clean(self, v) -> str:
        return redact(v, self._token)[:_FIELD_MAX]

    def _rotate(self) -> None:
        def rn(a: Path, b: Path):
            try:
                os.replace(a, b)
            except OSError:
                pass
        numbered = lambda i: self.path.with_name(f"{self.path.name}.{i}")  # noqa: E731
        try:
            numbered(self.keep).unlink()
        except OSError:
            pass
        for i in range(self.keep - 1, 0, -1):
            if numbered(i).exists():
                rn(numbered(i), numbered(i + 1))
        rn(self.path, numbered(1))

    def log(self, event, *, peer="", session=None, action=None, outcome, reason=None) -> bool:
        with self._lock:
            row = {"at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                   "event": self._clean(event), "peer": self._clean(peer)}
            if session is not None:
                row["session"] = self._clean(session)
            if action is not None:
                row["action"] = self._clean(action)
            row["outcome"] = self._clean(outcome)
            if reason is not None:
                row["reason"] = self._clean(reason)
            line = json.dumps(row, ensure_ascii=True, separators=(",", ":"))
            if self._token:                           # the token's JSON-escaped form, if it differs from the raw one
                esc = json.dumps(self._token)[1:-1]
                if esc != self._token:
                    line = line.replace(esc, REDACTED)
            line = _HEX_RUN.sub(REDACTED, line) + "\n"
            data = line.encode("utf-8")
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    size = self.path.stat().st_size
                except OSError:
                    size = 0
                if size and size + len(data) > self.max_bytes:
                    self._rotate()
                with open(self.path, "ab") as f:
                    f.write(data)
            except OSError:
                return False
            return True
