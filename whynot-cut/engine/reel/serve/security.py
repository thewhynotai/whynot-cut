"""Security building blocks of the local engine daemon `reel serve` (3.0 T6.2).

Pure stdlib, no server or engine-state dependency, so the daemon, the app and the tests share one implementation:
  * `<engine home>/bridge/engine.json` (port, token, pid, version): written atomically, user-only permissions
    (POSIX chmod 0600; Windows: inheritance removed and only the process user's SID granted, via icacls), and removed
    only by the daemon that wrote it (tombstone rename, no check-then-delete race);
  * `check_host` / `check_origin`: DNS-rebinding and browser-origin defences for the HTTP/WebSocket handshake;
  * `token_ok`: constant-time token compare; `make_token`: 256-bit token;
  * `RateLimiter`: token bucket (clock injectable);
  * `AuditLog`: JSON lines, size-capped rotation (cleared when rotation fails), thread-safe, and it can never write the
    token (every field is redacted: the exact token value and any run of 64 or more hex characters).
The token must never appear in a URL, a log line or an error message; callers pass it in only to compare / redact.
"""
from __future__ import annotations

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
TOKEN_RE = re.compile(r"[0-9a-f]{64}")      # the only token shape ever written or accepted (make_token's)
RESERVED_KEYS = frozenset({"port", "token", "pid", "version", "protocol"})


# ----------------------------------------------------------------------------------------------------------------
# token + engine.json
# ----------------------------------------------------------------------------------------------------------------
def make_token() -> str:
    """256-bit random token as 64 lowercase hex characters."""
    return secrets.token_hex(32)


def token_shape_ok(token) -> bool:
    """True for exactly 64 lowercase hex characters (a make_token() value)."""
    return isinstance(token, str) and TOKEN_RE.fullmatch(token) is not None


def token_ok(given, expected) -> bool:
    """Constant-time compare. Both sides must be 64 lowercase hex characters, else it never authenticates; never
    raises."""
    if not token_shape_ok(given) or not token_shape_ok(expected):
        return False
    return hmac.compare_digest(given.encode("ascii"), expected.encode("ascii"))


def engine_json_path(home) -> Path:
    return Path(home) / "bridge" / "engine.json"


def audit_log_path(home) -> Path:
    return Path(home) / "logs" / "serve-audit.log"


_SID_RE = re.compile(r"S-1-\d+(-\d+)+")
_SID: list = []                                  # the process user's SID, once known (it cannot change)


def _sid_from_token() -> str:
    """The current process user's SID string, read from the process token (Win32 API, no child process)."""
    import ctypes
    from ctypes import wintypes
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    vp = ctypes.c_void_p
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    k32.LocalFree.argtypes = (vp,)
    k32.LocalFree.restype = vp
    adv.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    adv.GetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, vp, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.DWORD))
    adv.ConvertSidToStringSidW.argtypes = (vp, ctypes.POINTER(vp))
    token = wintypes.HANDLE()
    if not adv.OpenProcessToken(k32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):      # TOKEN_QUERY
        raise OSError(f"OpenProcessToken failed ({ctypes.get_last_error()})")
    try:
        size = wintypes.DWORD()
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))                       # 1 = TokenUser
        if not size.value:
            raise OSError(f"GetTokenInformation failed ({ctypes.get_last_error()})")
        buf = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
            raise OSError(f"GetTokenInformation failed ({ctypes.get_last_error()})")
        psid = ctypes.cast(buf, ctypes.POINTER(vp))[0]          # TOKEN_USER.User.Sid is the first field
        text = vp()
        if not adv.ConvertSidToStringSidW(psid, ctypes.byref(text)):
            raise OSError(f"ConvertSidToStringSidW failed ({ctypes.get_last_error()})")
        try:
            return ctypes.wstring_at(text.value)
        finally:
            k32.LocalFree(text)
    finally:
        k32.CloseHandle(token)


def _sid_from_whoami() -> str:
    exe = shutil.which("whoami") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "whoami.exe")
    r = subprocess.run([exe, "/user", "/fo", "csv", "/nh"], capture_output=True, timeout=30)
    return r.stdout.decode("utf-8", "replace").strip().rsplit(",", 1)[-1].strip().strip('"')


def current_user_sid() -> str:
    """The SID (S-1-5-...) of the user this process runs as: from the process token, else `whoami /user`. Never the
    USERNAME / USERDOMAIN environment variables (any parent process can set those). OSError when neither works."""
    if _SID:
        return _SID[0]
    for how in (_sid_from_token, _sid_from_whoami):
        try:
            sid = how()
        except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
            continue
        if isinstance(sid, str) and _SID_RE.fullmatch(sid):
            _SID[:] = [sid]
            return sid
    raise OSError("cannot tell which user this process runs as (no SID)")


def restrict_to_user(path) -> None:
    """Make `path` readable and writable by the current user only. Fails closed: raises OSError if it cannot.
    Windows: inheritance removed and full control granted to the process user's SID only (`*S-1-5-...:F`)."""
    p = str(path)
    if os.name != "nt":
        os.chmod(p, 0o600)
        return
    sid = current_user_sid()
    exe = shutil.which("icacls") or os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icacls.exe")
    try:
        r = subprocess.run([exe, p, "/inheritance:r", "/grant:r", f"*{sid}:F"],
                           capture_output=True, timeout=30)     # bytes: only the return code is read
    except (OSError, subprocess.SubprocessError) as e:
        raise OSError(f"icacls failed for {p}: {type(e).__name__}") from e
    if r.returncode != 0:
        raise OSError(f"icacls failed for {p} (exit {r.returncode})")


def write_engine_json(home, *, port: int, token: str, pid: int, version: str, **extra) -> Path:
    """Atomically write <home>/bridge/engine.json. The temp file is restricted BEFORE the token is written, so the
    token is never on disk under a wider ACL; on any failure the old file is untouched and the temp file removed.
    `token` must be 64 lowercase hex characters; `extra` may not name a reserved key (ValueError)."""
    if not token_shape_ok(token):
        raise ValueError("the engine token must be 64 lowercase hex characters (make_token)")
    clash = RESERVED_KEYS.intersection(extra)
    if clash:
        raise ValueError(f"extra fields may not override {sorted(clash)}")
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
        _replace_retry(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    try:
        restrict_to_user(path)      # belt and braces: the final file never relies on what replace() kept
    except BaseException:
        try:                        # never leave the token behind under an ACL we could not confirm
            path.unlink()
        except OSError:
            pass
        raise
    return path


def read_engine_json(home) -> dict | None:
    """The parsed engine.json, or None when missing / unreadable / not a JSON object."""
    try:
        d = json.loads(engine_json_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def remove_engine_json(home, pid: int) -> bool:
    """Delete engine.json only when it records `pid` (a newer daemon's file is never removed by an older one).
    No check-then-delete race: the file is first renamed to a private tombstone (atomic), the tombstone is read, and
    only the tombstone is deleted. When it records another pid it goes back without ever overwriting: a file another
    daemon wrote meanwhile always wins (the tombstone, an older record, is then dropped). The tombstone is deleted
    only once engine.json exists again; if every way back fails, it stays on disk (user-only, like engine.json), so
    a live daemon's record is never lost."""
    path = engine_json_path(home)
    tomb = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.gone")
    try:
        _replace_retry(path, tomb)
    except OSError:
        return False                               # missing (or cannot be moved): nothing of ours to remove
    try:
        d = json.loads(tomb.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = None
    ours = isinstance(d, dict) and d.get("pid") == pid
    if ours or _restore_no_overwrite(tomb, path):
        try:
            tomb.unlink()                          # gone already when the restore renamed it back
        except OSError:
            pass
    return ours


REPLACE_TRIES = 20
RETRY_S = 0.025


def _replace_retry(src: Path, dst: Path) -> None:
    """os.replace, retried briefly on PermissionError: on Windows a reader that has engine.json open at that instant
    (`reel serve --status`, the stop poller, an antivirus scan) makes the rename fail with a sharing violation."""
    for i in range(REPLACE_TRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == REPLACE_TRIES - 1:
                raise
            time.sleep(RETRY_S)


def _restore_once(tomb: Path, path: Path) -> bool:
    """One non-overwriting attempt to put `tomb` back at `path`. True when `path` exists afterwards (put back, or a
    newer file is already there)."""
    try:
        os.link(tomb, path)                        # same file, same ACL
        return True
    except FileExistsError:
        return True
    except OSError:
        pass
    if os.name == "nt":
        try:
            os.rename(tomb, path)                  # Windows: FileExistsError instead of replacing
            return True
        except FileExistsError:
            return True
        except OSError:
            return path.exists()
    try:                                           # POSIX without hard links: exclusive create, user-only from birth
        data = tomb.read_bytes()
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return True
    except OSError:
        return path.exists()
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return True


def _restore_no_overwrite(tomb: Path, path: Path) -> bool:
    """Put `tomb` back at `path`, never over a file that exists there again. Retried briefly (a sharing violation on
    Windows); while `path` is still missing after that, a last os.replace (_replace_retry) puts it back. True when
    `path` exists at the end, so the caller may delete `tomb`; False keeps the tombstone (nothing worked)."""
    for _ in range(REPLACE_TRIES):
        if _restore_once(tomb, path):
            return True
        time.sleep(RETRY_S)
    if path.exists():
        return True
    try:
        _replace_retry(tomb, path)
    except OSError:
        return path.exists()
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
        try:
            return redact(v, self._token)[:_FIELD_MAX]
        except Exception:           # a value whose str() raises (or anything odd) is logged as redacted, never raised
            return REDACTED

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
        try:
            return self._log(event, peer, session, action, outcome, reason)
        except Exception:           # auditing must never take the daemon down
            return False

    def _log(self, event, peer, session, action, outcome, reason) -> bool:
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
                size = self._size()
                if size and size + len(data) > self.max_bytes:
                    self._rotate()
                    if self._size():                  # rotation failed (e.g. a reader holds the file on Windows)
                        data = self._truncated_row() + data
                        mode = "wb"                   # start over rather than grow without bound
                    else:
                        mode = "ab"
                else:
                    mode = "ab"
                with open(self.path, mode) as f:
                    f.write(data)
            except OSError:
                return False
            return True

    def _size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def _truncated_row(self) -> bytes:
        row = {"at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": "audit", "peer": "",
               "outcome": "truncated", "reason": "rotation failed: the log was cleared to stay within its size cap"}
        return (json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
