"""Security building blocks of the local engine daemon `reel serve` (3.0 T6.2).

Pure stdlib, no server or engine-state dependency, so the daemon, the app and the tests share one implementation:
  * `<engine home>/bridge/engine.json` (port, token, pid, version): written atomically, user-only permissions
    (POSIX chmod 0600; Windows: inheritance removed and only the process user's SID granted, via icacls), and removed
    only by the daemon that wrote it (tombstone rename, no check-then-delete race);
  * `private_dir` / `private_file` / `open_private`: the daemon's folders and files user-only even when they already
    existed (POSIX 0700 / 0600; Windows an exact protected DACL for the process SID, inherited by new files);
  * `check_host` / `check_origin`: DNS-rebinding and browser-origin defences for the HTTP/WebSocket handshake;
  * `token_ok`: constant-time token compare; `make_token`: 256-bit token;
  * `RateLimiter`: token bucket (clock injectable);
  * `AuditLog`: JSON lines, size-capped rotation (cleared when rotation fails), thread-safe, and it can never write the
    token (every field is redacted: the exact token value and any run of 64 or more hex characters).
The token must never appear in a URL, a log line or an error message; callers pass it in only to compare / redact.

Origin threat model. The Origin gate only keeps browser pages out; it is not what authenticates. Premiere 26.5.2's UXP
WebSocket sends exactly `Origin: file://` (measured live, see ALLOWED_ORIGINS_EXACT), so that one exact value passes
the gate; every other file form, `null` and every http(s) / ws(s) / *-extension origin stay refused. Not only UXP
sends it. Chromium-family browsers send `null` from a file page by default, but `file://` when file-URL access is
enabled (measured by the T6.2 security review: Chrome 154 with `--allow-file-access-from-files` sends `Origin: file://`
on both WebSocket and fetch), and embedders with the equivalent setting do too (Electron `allowFileAccessFromFileUrls`
or `webSecurity: false`, Android WebView); a CEP panel runs in CEF, so the future CEP adapter connection is likely to
send it as well and is covered by this rule. Those contexts reach only the pre-auth surface: a WebSocket upgrade with
`hello_timeout` (3 s) to send a valid hello while holding one connection slot (MAX_CONNECTIONS), or a 401 from the
HTTP routes. The token still decides: it lives only in engine.json, which is user-only (POSIX 0600 / a DACL for the
user's SID) and which no web page can read, and a hello or HTTP request without it is refused. Residual risk: a file
page in a context with file-URL access enabled can also read the user's local files, engine.json included, so for
it the token is no barrier. That needs the user to run such a browser or embedder AND open a hostile local HTML file,
which already holds the user's files (the same trust as the user's own processes, below); the Origin gate refused it
before T6.2 allowed `file://`. The Host check (`127.0.0.1:<port>` / `localhost:<port>` / `[::1]:<port>` only) stops
DNS rebinding, and the daemon binds the loopback addresses 127.0.0.1 and ::1 only (never 0.0.0.0, :: or a LAN
address), so nothing off the machine reaches it. A process running as the user that can
read engine.json is already past every defence here (the same trust as the user's own shell).
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL = 4

# The exact Origin values a non-browser client may send, compared as-is (case-sensitive, no prefix, no path; a value
# with whitespace or a control character anywhere is refused before this list is read). Measured live on Windows 11,
# Premiere Pro 26.5.2 (UXP 9.3.0): the WhyNot Cut panel 3.0.0 and spike 0.1.4 send exactly `file://` on the /session
# upgrade (spike 0.1.3's attempt never left Premiere: manifest, parity W1), and the daemon refused every one while
# `file` was only a browser scheme
# (~/.whynot-cut/logs/serve-audit.log, 2026-10-12 18:28:58Z-18:52:26Z: 205 rows
# {"event":"origin","action":"/session","outcome":"rejected","reason":"file://"} and no other Origin). Chromium-family
# browsers send "null" from a file page by default, but `file://` when file-URL access is enabled
# (`--allow-file-access-from-files`, or embedders with the equivalent setting); those contexts reach only the pre-auth
# hello (3 s window, one connection slot) and the token still decides (module docstring: threat model). Controller
# ruling (T6.2): this one value and nothing else new; the token, the Host check and the loopback bind still apply.
# Every entry must pass validate_exact_origins (no "null", no browser-scheme value except this exact `file://`),
# because origin_rejection reads this list before the null / browser-scheme checks.
ALLOWED_ORIGINS_EXACT = ("file://",)

# Origin prefixes kept from the provisional policy. UNMEASURED: nothing live has sent them (the UXP panel sends
# `file://`, above). Kept because macOS UXP has not been measured yet and test_serve_app pins `uxp://`; no browser gives
# a page a uxp: or plugin: origin, and they pass only the Origin gate (the token still decides). Drop them once the
# macOS measurement shows what macOS sends. "null" and BROWSER_SCHEMES are always rejected, whatever is listed here.
ALLOWED_ORIGIN_PREFIXES = ("uxp://", "plugin:")

# A web page (or a browser extension) can reach 127.0.0.1; these origins mean "this came from a browser context".
# `file` stays: every file-scheme Origin except the exact ALLOWED_ORIGINS_EXACT value (`file:///C:/...`, `file://host`,
# `FILE://`, `file:`) is refused as a browser scheme.
BROWSER_SCHEMES = frozenset({"http", "https", "file", "chrome-extension", "moz-extension", "safari-web-extension",
                             "ws", "wss"})

_BAD_ORIGIN_CHARS = re.compile(r"[\s\x00-\x1f\x7f]")


def _exact_entry_ok(value) -> bool:
    """May `value` stand in ALLOWED_ORIGINS_EXACT? The list is read BEFORE the "null" / browser-scheme checks, so an
    entry must not be "null" (any case) nor a browser-scheme value, except the one measured `file://`."""
    if not isinstance(value, str) or not value or _BAD_ORIGIN_CHARS.search(value):
        return False
    low = value.lower()
    if low == "null":
        return False
    scheme = low.split(":", 1)[0] if ":" in low else ""
    return scheme not in BROWSER_SCHEMES or value == "file://"


def validate_exact_origins(values) -> None:
    """ValueError unless every entry may stand in ALLOWED_ORIGINS_EXACT (_exact_entry_ok)."""
    bad = [v for v in values if not _exact_entry_ok(v)]
    if bad:
        raise ValueError(f"ALLOWED_ORIGINS_EXACT may not hold null, a browser-scheme value or a malformed one: {bad!r}")


validate_exact_origins(ALLOWED_ORIGINS_EXACT)        # import time; origin_rejection re-checks at check time too

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
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "whoami.exe")   # never PATH (L-G11)
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
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "icacls.exe")   # never PATH (L-G11)
    try:
        r = subprocess.run([exe, p, "/inheritance:r", "/grant:r", f"*{sid}:F"],
                           capture_output=True, timeout=30)     # bytes: only the return code is read
    except (OSError, subprocess.SubprocessError) as e:
        raise OSError(f"icacls failed for {p}: {type(e).__name__}") from e
    if r.returncode != 0:
        raise OSError(f"icacls failed for {p} (exit {r.returncode})")


def _dacl(path) -> list[tuple[int, int, str]] | None:
    """Windows: [(ACE type, ACE flags, SID)] of `path`'s DACL, read with the Win32 API; None when it cannot be read
    (or the DACL is NULL, i.e. open to everyone)."""
    import ctypes
    from ctypes import wintypes
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    vp = ctypes.c_void_p
    adv.GetNamedSecurityInfoW.argtypes = (wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, vp, vp,
                                          ctypes.POINTER(vp), vp, ctypes.POINTER(vp))
    adv.GetNamedSecurityInfoW.restype = wintypes.DWORD
    adv.GetAce.argtypes = (vp, wintypes.DWORD, ctypes.POINTER(vp))
    adv.ConvertSidToStringSidW.argtypes = (vp, ctypes.POINTER(vp))
    k32.LocalFree.argtypes = (vp,)
    k32.LocalFree.restype = vp
    dacl, sd = vp(), vp()
    if adv.GetNamedSecurityInfoW(str(path), 1, 4, None, None, ctypes.byref(dacl), None, ctypes.byref(sd)) != 0:
        return None                                  # 1 = SE_FILE_OBJECT, 4 = DACL_SECURITY_INFORMATION
    try:
        if not dacl.value:
            return None
        out = []
        for i in range(ctypes.c_uint16.from_address(dacl.value + 4).value):      # ACL.AceCount
            ace = vp()
            if not adv.GetAce(dacl, i, ctypes.byref(ace)):
                return None
            text = vp()
            if not adv.ConvertSidToStringSidW(ace.value + 8, ctypes.byref(text)):  # ACCESS_ALLOWED_ACE.SidStart
                return None
            try:
                out.append((ctypes.c_ubyte.from_address(ace.value).value,
                            ctypes.c_ubyte.from_address(ace.value + 1).value, ctypes.wstring_at(text.value)))
            finally:
                k32.LocalFree(text)
        return out
    finally:
        k32.LocalFree(sd)


def user_only(path, *, directory: bool = False) -> bool:
    """Windows: is the DACL of `path` "this process's user, allowed" and nothing else? For a folder the ACE must also
    be inherited by new files and folders (OI|CI), so what is created inside is user-only from birth."""
    try:
        aces = _dacl(path)
        sid = current_user_sid()
    except (OSError, AttributeError, ValueError):
        return False
    if not aces or any(t != 0 or s != sid for t, _, s in aces):
        return False
    return not directory or any(f & 0x03 == 0x03 and not f & 0x10 for _, f, _ in aces)


def private_dir(path) -> Path:
    """Create `path` (and parents) and make it user-only even when it already existed (mkdir's mode does not touch
    an existing folder): POSIX chmod 0700; Windows inheritance removed and full control for the process user's SID
    only, inherited by everything created inside (`*SID:(OI)(CI)F`). Skipped when it already is. Raises OSError."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(p, 0o700)
        return p
    if not user_only(p, directory=True):
        _set_dacl(p, f"D:P(A;OICI;FA;;;{current_user_sid()})")
    return p


def _set_dacl(path, sddl: str) -> None:
    """Windows: replace the DACL of `path` with exactly the one in `sddl`, protected from inheritance (Win32
    SetNamedSecurityInfoW, which also passes inheritable ACEs on to what is inside a folder). icacls cannot do this
    for a folder: `/inheritance:r` keeps explicit ACEs, such as the SYSTEM and Administrators entries Python's
    mkdir(mode=0o700) puts on Windows, and new files would inherit them. Raises OSError."""
    import ctypes
    from ctypes import wintypes
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    vp = ctypes.c_void_p
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD,
                                                                         ctypes.POINTER(vp), vp)
    adv.GetSecurityDescriptorDacl.argtypes = (vp, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(vp),
                                              ctypes.POINTER(wintypes.BOOL))
    adv.SetNamedSecurityInfoW.argtypes = (wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, vp, vp, vp, vp)
    adv.SetNamedSecurityInfoW.restype = wintypes.DWORD
    k32.LocalFree.argtypes = (vp,)
    k32.LocalFree.restype = vp
    sd = vp()
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None):
        raise OSError(f"bad security descriptor ({ctypes.get_last_error()})")
    try:
        present, defaulted, dacl = wintypes.BOOL(), wintypes.BOOL(), vp()
        if not adv.GetSecurityDescriptorDacl(sd, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)):
            raise OSError(f"GetSecurityDescriptorDacl failed ({ctypes.get_last_error()})")
        # 1 = SE_FILE_OBJECT; DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION
        rc = adv.SetNamedSecurityInfoW(str(path), 1, 0x00000004 | 0x80000000, None, None, dacl, None)
        if rc != 0:
            raise OSError(f"SetNamedSecurityInfoW failed for {path} ({rc})")
    finally:
        k32.LocalFree(sd)


def private_file(path) -> None:
    """Make an existing file user-only (POSIX 0600; Windows restrict_to_user unless it already is). Raises OSError."""
    if os.name != "nt":
        os.chmod(path, 0o600)
    elif not user_only(path):
        restrict_to_user(path)


def open_private(path, flags: int) -> int:
    """os.open with O_CREAT and mode 0600, so a new file is never readable by others for an instant (POSIX); an
    existing file is narrowed to 0600 too. Windows: the caller's folder (private_dir) makes it user-only."""
    fd = os.open(str(path), flags | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o600)
    if os.name != "nt":
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            os.close(fd)
            raise
    return fd


def write_engine_json(home, /, *, port: int, token: str, pid: int, version: str, **extra) -> Path:
    """Atomically write <home>/bridge/engine.json. The temp file is restricted BEFORE the token is written, so the
    token is never on disk under a wider ACL; on any failure the old file is untouched and the temp file removed.
    `token` must be 64 lowercase hex characters; `extra` may not name a reserved key (ValueError)."""
    if not token_shape_ok(token):
        raise ValueError("the engine token must be 64 lowercase hex characters (make_token)")
    clash = RESERVED_KEYS.intersection(extra)
    if clash:
        raise ValueError(f"extra fields may not override {sorted(clash)}")
    path = engine_json_path(home)
    private_dir(path.parent)
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


_ANY = object()


def remove_engine_json(home, pid: int, *, pid_created=_ANY) -> bool:
    """Delete engine.json only when it records `pid` (a newer daemon's file is never removed by an older one), and,
    when `pid_created` is given, that process start time too (a dead pid reused by another daemon is not "ours").
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
    ours = isinstance(d, dict) and d.get("pid") == pid and (pid_created is _ANY or d.get("pid_created") == pid_created)
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
    """Only `127.0.0.1:<port>`, `localhost:<port>` or `[::1]:<port>` (any case): anything else is a rebinding or
    misrouted request. The daemon also listens on ::1 (Windows resolves `localhost` there first), and a client that
    connects by the IPv6 literal sends the bracketed form. A missing, repeated, port-less, other-port, unbracketed or
    other IPv6 Host is rejected."""
    host = _header(headers, "Host")
    if not isinstance(host, str):
        return False
    return host.lower() in (f"127.0.0.1:{int(port)}", f"localhost:{int(port)}", f"[::1]:{int(port)}")


def origin_rejection(headers) -> str | None:
    """None when the Origin is acceptable, else a short reason code (safe to audit-log, no values). Order: absent ->
    ok; repeated / empty / any whitespace or control character -> refused; an exact ALLOWED_ORIGINS_EXACT value
    (case-sensitive) -> ok; "null" or a BROWSER_SCHEMES scheme (any case) -> refused; an ALLOWED_ORIGIN_PREFIXES
    prefix -> ok; anything else -> refused."""
    origin = _header(headers, "Origin")
    if origin is None:
        return None            # non-browser clients send no Origin
    if not isinstance(origin, str):
        return "origin-repeated"
    low = origin.lower()
    if not origin or re.search(r"[\s\x00-\x1f\x7f]", origin):
        return "origin-malformed"
    if origin in ALLOWED_ORIGINS_EXACT and _exact_entry_ok(origin):
        return None            # the measured UXP value, exactly (FILE://, file:///x, file://host fall through; a
                               # widened entry that is null or a browser-scheme value is never honoured)
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
        self._private = False

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
                self._make_private()
                size = self._size()
                flags = os.O_WRONLY | os.O_APPEND
                if size and size + len(data) > self.max_bytes:
                    self._rotate()
                    if self._size():                  # rotation failed (e.g. a reader holds the file on Windows)
                        data = self._truncated_row() + data
                        flags = os.O_WRONLY | os.O_TRUNC   # start over rather than grow without bound
                with os.fdopen(open_private(self.path, flags), "wb") as f:
                    f.write(data)
            except OSError:
                return False
            return True

    def _make_private(self) -> None:
        """Once per log: the folder user-only (files created in it inherit that on Windows; POSIX files are created
        0600 by open_private) and an existing log narrowed too. A failure here never stops the auditing."""
        if self._private:
            return
        self._private = True
        try:
            private_dir(self.path.parent)
            for f in [self.path] + [self.path.with_name(f"{self.path.name}.{i}") for i in range(1, self.keep + 1)]:
                if f.exists():
                    private_file(f)
        except OSError:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def _truncated_row(self) -> bytes:
        row = {"at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": "audit", "peer": "",
               "outcome": "truncated", "reason": "rotation failed: the log was cleared to stay within its size cap"}
        return (json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
