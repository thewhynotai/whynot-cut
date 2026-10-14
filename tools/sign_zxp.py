#!/usr/bin/env python3
"""Sign the WhyNot Cut CEP bundle into whynot-cut/adobe/WhyNotCut-Bridge-3.0.0.zxp (3.0 T6.3 Task 6). Stdlib only.

    python tools/sign_zxp.py setup [--from <ZXPSignCmd file already downloaded>]
    python tools/sign_zxp.py build [--tsa <timestamp server URL>]
    python tools/sign_zxp.py verify [<zxp>]

setup   (once per machine; everything lives in ~/.whynot-cut/signing/, never in the repo)
  * ZXPSignCmd: Adobe's signing tool, pinned by Adobe-CEP/CEP-Resources commit + path + size + sha256 (`PINS`).
    `--from <file>` copies a file that is already downloaded after checking it against the same pin; without it the
    pinned raw.githubusercontent.com URL is fetched into a temp folder and checked the same way. A mismatch is
    refused and nothing is written. The tool already in place is checked against the pin before every use.
    Windows x64 and macOS. The macOS tool (its own commit) is Mach-O x86_64 only: on Apple Silicon it runs through
    Rosetta 2. It is not notarized; it is fetched by urllib (never a browser), so it has no quarantine attribute, and
    setup makes it 0755 after the pin check. It is a build-time tool on the signing machine: it never ships.
  * The certificate: a self-signed one, made once: `EG Cairo "The Why Not AI" "WhyNot Cut"`, valid 3650 days, in
    signing/whynot-cut.p12. An existing certificate is never replaced.
  * Its password: secrets.token_urlsafe(32), kept in the OS credential store (target `WhyNotCut/zxp-signing`):
    the Windows Credential Manager (ctypes CredWriteW / CredReadW; no `keyring` dependency, plan decision 12) or the
    macOS keychain (`security -i`, the password on stdin: never on an argv, which `ps` shows; read back to check).
build
  * assembles the bundle (engine lib/cep_bundle.assemble) in a temp staging folder and refuses it when it holds any
    symlink, junction, `.DS_Store` or `__MACOSX` (Adobe's KnownIssue2024: UPIA-installed ZXPs that hold links fail
    their signature check);
  * `ZXPSignCmd -sign <staging> <zxp> <p12> <password> -tsa <url>`: `-tsa` is ALWAYS passed (default
    http://timestamp.digicert.com); a failed timestamp fails the build (plan decision 11);
  * `ZXPSignCmd -verify <zxp> -certinfo` (VERIFY_TIMEOUT s; a timeout is retried once, a second failure fails the
    build) must report a verified signature and a `Timestamp: Valid ...` line (`Timestamp: None` = signed without
    -tsa: refused), and the archive must hold META-INF/signatures.xml plus exactly the staged files (only META-INF/*
    and `mimetype` may be added);
  * an atomic rename to whynot-cut/adobe/WhyNotCut-Bridge-3.0.0.zxp, and every other *.zxp there is removed: exactly
    one .zxp is left (tools/release.py --fill-artefacts refuses two). A failed build leaves the folder as it was.
verify  the -verify -certinfo and archive checks on the built ZXP (no password needed).

The password is never printed, logged or put in an error: every command shown is redacted (`shown`), every output of
ZXPSignCmd is scrubbed of it (`scrub`), and failures are raised as SignError built from the redacted command only.
(ZXPSignCmd itself takes the password as an argument; that cannot be avoided.) ZXPSignCmd's stdout and stderr go to
temp files, never pipes (a timeout kill on Windows cannot block on a pipe a child inherited).
Exit codes: 0 ok, 2 refused / failed (one line on stderr says why and what to do).
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "whynot-cut" / "engine" / "reel"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from lib import cep_bundle, plat  # noqa: E402  (stdlib only)

ZXP_NAME = cep_bundle.ZXP_NAME                      # WhyNotCut-Bridge-3.0.0.zxp
OUT_DIR = REPO / "whynot-cut" / "adobe"             # git-ignored *.zxp; shipped with the plugin (package.py)
_REPO_OUT = OUT_DIR                                 # the test-sandbox guard (never patched)
DEFAULT_TSA = "http://timestamp.digicert.com"
CRED_TARGET = "WhyNotCut/zxp-signing"
CERT_NAME = "whynot-cut.p12"
CERT_SUBJECT = ("EG", "Cairo", "The Why Not AI", "WhyNot Cut")   # country, state, organisation, common name
CERT_DAYS = 3650
SIGN_TIMEOUT = 600
VERIFY_TIMEOUT = 120                                # -verify -certinfo: retried once on a timeout (exit 124) only
FORBIDDEN_NAMES = {".ds_store", "__macosx"}
IS_WIN = os.name == "nt"

# ZXPSignCmd, pinned (plan decision 10). Version 4.1.3 is Adobe's 2025 build ("added new Windows version with SHA2
# fix"); the controller downloaded it once and checked it (2026-10-13). The exe is not Authenticode-signed: the
# pinned size + sha256 is the check. Each pin names its own commit (`commit`, default PIN_COMMIT).
PIN_REPO = "Adobe-CEP/CEP-Resources"
PIN_COMMIT = "8897cfaf9801b0ad5321951199dd831a82964583"
PINS = {
    "windows-x64": {"version": "4.1.3", "path": "ZXPSignCMD/4.1.3/x64/ZXPSignCmd.exe", "file": "ZXPSignCmd.exe",
                    "size": 4542464, "git_blob": "f5df2ed805e04a4d3c6adc722f602d4df6c762f7",
                    "sha256": "ffc2223167225ce61d024eb463fc5ad1a1be16133f99ef334a646f7311916c98"},
    # Mach-O x86_64 only (Rosetta 2 on Apple Silicon) and not notarized; fetched by urllib, so no quarantine
    # attribute. A build-time tool on the signing machine: it never ships with the plugin or the installer.
    "macos": {"version": "4.1.3", "path": "ZXPSignCMD/4.1.3/macOS/ZXPSignCmd", "file": "ZXPSignCmd",
              "size": 6391280, "git_blob": "38b958508c5a249d12418845dd07ad43e4f34a92",
              "sha256": "bc773fae0b97416fc7a462e7dadcc00270428a9913480c9b78b5606ff1cfb095",
              "commit": "fcee8de5537d2dd2ed3d91d5a495b7041155b280", "arch": "x86_64", "notarized": False},
}


class SignError(Exception):
    """A refusal or failure. Its text is built from redacted commands and scrubbed output only."""

    def __init__(self, error: str, how: str = ""):
        super().__init__(error)
        self.error, self.how = error, how


# --------------------------------------------------------------------------------------------- secrets hygiene
def shown(argv, secret: str | None) -> list:
    """The command as it may be shown: the password replaced by ***."""
    return ["***" if secret and a == secret else str(a) for a in argv]


def scrub(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret else text


def _tail(text: str, n: int = 600) -> str:
    text = " ".join(str(text).split())
    return text[-n:]


# --------------------------------------------------------------------------------------------- the credential store
class WinCredStore:
    """The Windows Credential Manager through advapi32 (generic credential, persisted on this machine)."""
    CRED_TYPE_GENERIC, CRED_PERSIST_LOCAL_MACHINE, ERROR_NOT_FOUND = 1, 2, 1168

    def __init__(self):
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIALW(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        self.CREDENTIALW = CREDENTIALW
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        self._write = adv.CredWriteW
        self._write.argtypes, self._write.restype = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD], wintypes.BOOL
        self._read = adv.CredReadW
        self._read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
        self._read.restype = wintypes.BOOL
        self._free = adv.CredFree
        self._free.argtypes, self._free.restype = [ctypes.c_void_p], None
        self._delete = adv.CredDeleteW
        self._delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self._delete.restype = wintypes.BOOL

    def delete(self, target: str) -> None:
        """Remove the credential; a missing one is no error."""
        if not self._delete(target, self.CRED_TYPE_GENERIC, 0):
            err = ctypes.get_last_error()
            if err != self.ERROR_NOT_FOUND:
                raise SignError(f"the Windows Credential Manager could not remove {target} (error {err})")

    def read(self, target: str) -> str | None:
        p = ctypes.POINTER(self.CREDENTIALW)()
        if not self._read(target, self.CRED_TYPE_GENERIC, 0, ctypes.byref(p)):
            err = ctypes.get_last_error()
            if err == self.ERROR_NOT_FOUND:
                return None
            raise SignError(f"the Windows Credential Manager could not be read (error {err})")
        try:
            c = p.contents
            return bytes(c.CredentialBlob[:c.CredentialBlobSize]).decode("utf-8")
        finally:
            self._free(p)

    def write(self, target: str, secret: str) -> None:
        blob = secret.encode("utf-8")
        buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        c = self.CREDENTIALW()
        c.Type, c.TargetName, c.Persist = self.CRED_TYPE_GENERIC, target, self.CRED_PERSIST_LOCAL_MACHINE
        c.CredentialBlobSize, c.CredentialBlob = len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
        c.UserName = "WhyNot Cut"
        if not self._write(ctypes.byref(c), 0):
            raise SignError(f"the Windows Credential Manager refused the password (error {ctypes.get_last_error()})")


class MacKeychain:
    """The macOS login keychain through /usr/bin/security (generic password, service = the target). The password is
    written through `security -i` on stdin, never on an argv (`ps` shows every argv to every user of the machine)."""
    SECURITY = "/usr/bin/security"
    ACCOUNT = "WhyNot Cut"
    _SAFE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_./-]*")         # what `security -i`'s line parser takes as-is

    def read(self, target: str) -> str | None:
        r = subprocess.run([self.SECURITY, "find-generic-password", "-s", target, "-a", self.ACCOUNT, "-w"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        return r.stdout.rstrip("\n") if r.returncode == 0 and r.stdout.strip() else None

    def write(self, target: str, secret: str) -> None:
        if not (self._SAFE.fullmatch(secret or "") and self._SAFE.fullmatch(target)):
            raise SignError("the password or target holds characters `security -i` could misread: not written")
        line = f'add-generic-password -U -s "{target}" -a "{self.ACCOUNT}" -w "{secret}"\n'
        r = subprocess.run([self.SECURITY, "-i"], input=line, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise SignError(f"the macOS keychain refused the password (exit {r.returncode})")
        if self.read(target) != secret:          # `security -i` can exit 0 after a failed command: check the write
            raise SignError("the macOS keychain did not keep the password",
                            "unlock the login keychain (Keychain Access) and run setup again")


def default_store():
    if os.name == "nt":
        return WinCredStore()
    if sys.platform == "darwin":
        return MacKeychain()
    raise SignError("no supported credential store on this system (Windows or macOS only)")


# --------------------------------------------------------------------------------------------- tool, pin, paths
def platform_key() -> str:
    if os.name == "nt":
        return "windows-x64" if platform.machine().lower() in ("amd64", "x86_64") else f"windows-{platform.machine()}"
    return "macos" if sys.platform == "darwin" else sys.platform


def pin_for(key: str) -> dict:
    pin = PINS.get(key)
    if pin is None:
        raise SignError(f"no ZXPSignCmd pin for this system ({key})", "sign on Windows x64 or macOS")
    return pin


def pin_url(pin: dict) -> str:
    return f"https://raw.githubusercontent.com/{PIN_REPO}/{pin.get('commit', PIN_COMMIT)}/{pin['path']}"


def pin_note(pin: dict) -> str | None:
    """A note for this machine: the macOS tool is x86_64 only, so Apple Silicon runs it through Rosetta 2."""
    if pin.get("arch") == "x86_64" and platform.machine().lower() in ("arm64", "aarch64"):
        return ("ZXPSignCmd for macOS is x86_64 only: on Apple Silicon it runs through Rosetta 2 (install it once "
                "with `softwareupdate --install-rosetta`)")
    return None


def signing_dir(home: Path | None = None) -> Path:
    """~/.whynot-cut/signing (the user's home, like config.json; never the repo)."""
    return Path(home) if home is not None else Path.home() / ".whynot-cut" / "signing"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pin_problem(p: Path, pin: dict) -> str | None:
    """None when `p` is a regular file of the pinned size and sha256, else why not."""
    try:
        st = os.lstat(p)
    except OSError:
        return f"{p} does not exist"
    if not stat.S_ISREG(st.st_mode):
        return f"{p} is not a regular file"
    if st.st_size != pin["size"]:
        return f"{p.name} is {st.st_size} bytes; the pinned ZXPSignCmd {pin['version']} is {pin['size']}"
    got = _sha256(p)
    if got != pin["sha256"]:
        return f"{p.name} has sha256 {got}; the pinned ZXPSignCmd {pin['version']} has {pin['sha256']}"
    return None


def _refuse_live(what: str, *targets) -> None:
    """Inside the unit-test sandbox: never the real ~/.whynot-cut, never the repo's own whynot-cut/adobe."""
    r = plat.sandbox_refusal(what, *targets)
    if r:
        raise SignError(r["error"], r["how"])
    if os.environ.get(plat.SANDBOX_ENV) and any(Path(t).resolve() == _REPO_OUT.resolve() for t in targets):
        raise SignError(f"test sandbox: refused to {what} in the repo's {_REPO_OUT}", "pass a temp out_dir")


def run_tool(argv: list, timeout: float = SIGN_TIMEOUT, secret: str | None = None) -> tuple:
    """(exit code, stdout+stderr) of one ZXPSignCmd run: 124 on a timeout, 127 when it cannot start. stdout and stderr
    go to temp files, never pipes: after a timeout kill, Windows would wait on a pipe that a child of the tool
    inherited. The files are read back and scrubbed of `secret`. Never raises CalledProcessError (its text holds the
    argv)."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            rc = subprocess.run([str(a) for a in argv], stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
            note = ""
        except subprocess.TimeoutExpired:
            rc, note = 124, f"timed out after {timeout:.0f} s"
        except OSError as e:
            return 127, f"could not start ({e.strerror or type(e).__name__})"
        text = ""
        for f in (out, err):
            f.seek(0)
            text += f.read().decode("utf-8", errors="replace")
    if note:
        text = (text.rstrip("\n") + "\n" + note).lstrip("\n")
    return rc, scrub(text, secret)


def fetch_url(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:     # noqa: S310 (pinned https URL)
        shutil.copyfileobj(r, f, 1 << 20)


def _call(runner, argv: list, secret: str | None, what: str, log, timeout: float = SIGN_TIMEOUT,
          retry_timeout: bool = False) -> str:
    """Run one ZXPSignCmd command; with `retry_timeout`, a timeout (exit 124) is tried once more, nothing else is."""
    for attempt in (1, 2):
        log("$ " + " ".join(shown(argv, secret)))
        rc, out = runner(list(argv), timeout=timeout, secret=secret)
        out = scrub(str(out), secret)
        if rc == 124 and retry_timeout and attempt == 1:
            log(f"{what} timed out after {timeout:.0f} s: trying once more")
            continue
        break
    if rc != 0:
        raise SignError(f"{what} failed (exit {rc}): {_tail(out)}")
    return out


# --------------------------------------------------------------------------------------------- setup
def new_password() -> str:
    """secrets.token_urlsafe(32), never starting with "-" (ZXPSignCmd would read it as an option)."""
    while True:
        secret = secrets.token_urlsafe(32)
        if not secret.startswith("-"):
            return secret


def setup(*, src: Path | None = None, home: Path | None = None, runner=None, store=None, fetch=None,
          key: str | None = None, log=print) -> dict:
    pin = pin_for(key or platform_key())
    sdir = signing_dir(home)
    _refuse_live("set up ZXP signing", sdir)
    runner, fetch = runner or run_tool, fetch or fetch_url
    tool = sdir / pin["file"]
    if src is not None:                                 # checked BEFORE anything is written
        bad = pin_problem(Path(src), pin)
        if bad:
            raise SignError(f"refused: {bad}", f"download {pin_url(pin)} again")
    tool_state = "kept"
    if src is not None or pin_problem(tool, pin):
        with tempfile.TemporaryDirectory(prefix="wnc-zxpsign-") as t:
            cand = Path(src) if src is not None else Path(t) / pin["file"]
            if src is None:
                log(f"fetching ZXPSignCmd {pin['version']} from {pin_url(pin)}")
                try:
                    fetch(pin_url(pin), cand)
                except OSError as e:
                    raise SignError(f"could not fetch ZXPSignCmd ({e})",
                                    f"download {pin_url(pin)} yourself, then run setup --from <file>") from None
                bad = pin_problem(cand, pin)
                if bad:
                    raise SignError(f"refused: {bad}", "nothing was written; check the download")
            sdir.mkdir(parents=True, exist_ok=True)
            part = sdir / f".{pin['file']}.{os.getpid()}.part"
            shutil.copyfile(cand, part)
            bad = pin_problem(part, pin)
            if bad:
                part.unlink()
                raise SignError(f"refused: the copy changed ({bad})")
            if not IS_WIN:                              # after the pin check only (macOS: never a quarantine
                os.chmod(part, 0o755)                   # attribute to strip: urllib, not a browser)
            os.replace(part, tool)
        tool_state = "installed"
    note = pin_note(pin)
    if note:
        log(note)
    try:
        sdir.chmod(0o700)
    except OSError:
        pass
    store = store or default_store()
    cert = sdir / CERT_NAME
    if cert.exists():
        if store.read(CRED_TARGET) is None:
            raise SignError(f"the certificate {cert} exists but its password is not in the credential store "
                            f"({CRED_TARGET})", f"remove {cert} to make a new certificate (sign again after that)")
        cert_state = "kept"
    else:
        secret = store.read(CRED_TARGET)
        if secret is None:
            secret = new_password()
            store.write(CRED_TARGET, secret)
        _call(runner, [tool, "-selfSignedCert", *CERT_SUBJECT, secret, cert, "-validityDays", str(CERT_DAYS)],
              secret, "making the certificate", log)
        if not cert.is_file():
            raise SignError(f"ZXPSignCmd reported success but wrote no {cert.name}")
        cert_state = "made"
    return {"ok": True, "tool": str(tool), "tool_state": tool_state, "version": pin["version"],
            "cert": str(cert), "cert_state": cert_state, "password": f"in the credential store ({CRED_TARGET})"}


# --------------------------------------------------------------------------------------------- build / verify
def staging_problems(root: Path) -> list:
    """Every symlink, junction, .DS_Store or __MACOSX in the staging tree (Adobe KnownIssue2024)."""
    bad = []
    if cep_bundle._is_link(root):
        return [str(root)]
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            if cep_bundle._is_link(p) or name.casefold() in FORBIDDEN_NAMES:
                bad.append(p.relative_to(root).as_posix())
        dirnames[:] = [d for d in dirnames if not cep_bundle._is_link(Path(dirpath) / d)]
    return sorted(bad)


def _timestamp_ok(out: str) -> bool:
    """`-verify -certinfo` of ZXPSignCmd 4.1.3 prints `Timestamp: Valid and within certificate validity dates at time
    of signing` for a timestamped signature and `Timestamp: None` without -tsa (tests/fixtures/zxpsigncmd). Every
    `Timestamp:` line must say Valid, with no negative word; at least one must be there."""
    lines = [ln.strip() for ln in out.splitlines() if re.match(r"\s*time\s*stamp\s*:", ln, re.I)]
    neg = re.compile(r"\b(invalid|not|no|none|fail\w*|error|missing|expired|untrusted)\b", re.I)
    return bool(lines) and all(re.match(r"time\s*stamp\s*:\s*valid\b", ln, re.I) and not neg.search(ln)
                               for ln in lines)


def check_zxp(zxp: Path, staged: Path | None = None) -> None:
    """The archive holds META-INF/signatures.xml and, when `staged` is given, exactly the staged files with the same
    CRC (only META-INF/* and `mimetype` may be added)."""
    try:
        with zipfile.ZipFile(zxp) as zf:
            infos = {zi.filename: zi for zi in zf.infolist() if not zi.is_dir()}
            if zf.testzip() is not None:
                raise SignError(f"{zxp.name} is damaged")
    except (zipfile.BadZipFile, OSError) as e:
        raise SignError(f"{zxp.name} is not a readable ZXP ({e})") from None
    if cep_bundle.SIGNATURES not in infos:
        raise SignError(f"{zxp.name} holds no {cep_bundle.SIGNATURES}: it is not signed")
    if staged is None:
        return
    import zlib
    want = {p.relative_to(staged).as_posix(): p for p in staged.rglob("*") if p.is_file()}
    missing = sorted(set(want) - set(infos))
    extra = sorted(n for n in set(infos) - set(want) if not (n.startswith("META-INF/") or n == "mimetype"))
    if missing or extra:
        raise SignError(f"{zxp.name} does not hold the staged bundle (missing {missing}, extra {extra})")
    for rel, p in want.items():
        if zlib.crc32(p.read_bytes()) & 0xFFFFFFFF != infos[rel].CRC:
            raise SignError(f"{zxp.name}: {rel} differs from the staged file")


def _verify(runner, tool: Path, zxp: Path, log, staged: Path | None = None, secret: str | None = None) -> str:
    out = _call(runner, [tool, "-verify", zxp, "-certinfo"], secret, "verifying the signature", log,
                timeout=VERIFY_TIMEOUT, retry_timeout=True)
    if not re.search(r"signature verified", out, re.I):
        raise SignError(f"ZXPSignCmd did not report a verified signature: {_tail(out)}")
    if not _timestamp_ok(out):
        raise SignError(f"the signature carries no valid timestamp: {_tail(out)}",
                        "check the timestamp server (--tsa) and build again; an untimestamped ZXP is never kept")
    check_zxp(zxp, staged)
    return out


def _tool(home: Path | None, key: str | None) -> Path:
    pin = pin_for(key or platform_key())
    tool = signing_dir(home) / pin["file"]
    bad = pin_problem(tool, pin)
    if bad:
        raise SignError(f"ZXPSignCmd is not set up: {bad}", "run `python tools/sign_zxp.py setup` first")
    return tool


def build(*, tsa: str = DEFAULT_TSA, home: Path | None = None, out_dir: Path | None = None, runner=None,
          store=None, assemble=None, key: str | None = None, log=print) -> dict:
    if not isinstance(tsa, str) or not re.fullmatch(r"https?://[^\s\"']+", tsa):
        raise SignError(f"--tsa must be an http(s) URL, not {tsa!r}", f"the default is {DEFAULT_TSA}")
    out_dir = Path(out_dir) if out_dir is not None else OUT_DIR
    sdir = signing_dir(home)
    _refuse_live("build the signed ZXP", sdir, out_dir)
    tool = _tool(home, key)
    cert = sdir / CERT_NAME
    if not cert.is_file():
        raise SignError(f"no signing certificate ({cert})", "run `python tools/sign_zxp.py setup` first")
    store = store or default_store()
    secret = store.read(CRED_TARGET)
    if not secret:
        raise SignError(f"the certificate password is not in the credential store ({CRED_TARGET})",
                        "run `python tools/sign_zxp.py setup` (or remove the certificate to make a new one)")
    runner, assemble = runner or run_tool, assemble or cep_bundle.assemble
    final = out_dir / ZXP_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / f".wnc-zxp-{os.getpid()}"         # same volume as the final name: the rename is atomic
    with tempfile.TemporaryDirectory(prefix="wnc-zxp-stage-") as t:
        staged = Path(t) / cep_bundle.EXT_ID
        try:
            assemble(staged)
        except FileNotFoundError as e:
            raise SignError(f"the bundle cannot be assembled: {e}") from None
        bad = staging_problems(staged)
        if bad:
            raise SignError(f"the staged bundle holds links or macOS metadata ({', '.join(bad)}): nothing was signed",
                            "remove them from the sources (Adobe KnownIssue2024: such ZXPs fail their signature "
                            "check after a UPIA install)")
        cep_bundle._remove(work)
        work.mkdir()
        try:
            tmp = work / ZXP_NAME
            _call(runner, [tool, "-sign", staged, tmp, cert, secret, "-tsa", tsa], secret,
                  "signing (with the timestamp server " + tsa + ")", log)
            if not tmp.is_file():
                raise SignError("ZXPSignCmd reported success but wrote no ZXP")
            _verify(runner, tool, tmp, log, staged, secret)
            os.replace(tmp, final)
        finally:
            cep_bundle._remove(work)
    removed = []
    for other in sorted(out_dir.glob("*.zxp")):
        if other.name != ZXP_NAME and other.is_file() and not cep_bundle._is_link(other):
            other.unlink()
            removed.append(other.name)
    return {"ok": True, "zxp": str(final), "sha256": _sha256(final), "tsa": tsa, "removed": removed}


def verify(zxp: Path | None = None, *, home: Path | None = None, runner=None, key: str | None = None,
           log=print) -> dict:
    zxp = Path(zxp) if zxp is not None else OUT_DIR / ZXP_NAME
    if not zxp.is_file():
        raise SignError(f"no ZXP at {zxp}", "run `python tools/sign_zxp.py build` first")
    out = _verify(runner or run_tool, _tool(home, key), zxp, log)
    return {"ok": True, "zxp": str(zxp), "sha256": _sha256(zxp), "certinfo": _tail(out, 2000)}


# --------------------------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="sign_zxp.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="ZXPSignCmd (pinned), the self-signed certificate, its password in the OS store")
    s.add_argument("--from", dest="src", type=Path, help="a ZXPSignCmd file already downloaded (checked by the pin)")
    b = sub.add_parser("build", help=f"sign the bundle into whynot-cut/adobe/{ZXP_NAME}")
    b.add_argument("--tsa", default=DEFAULT_TSA, help=f"timestamp server (default {DEFAULT_TSA})")
    v = sub.add_parser("verify", help="verify the built ZXP")
    v.add_argument("zxp", nargs="?", type=Path)
    a = ap.parse_args(argv)
    log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    try:
        if a.cmd == "setup":
            r = setup(src=a.src, log=log)
        elif a.cmd == "build":
            r = build(tsa=a.tsa, log=log)
        else:
            r = verify(a.zxp, log=log)
    except SignError as e:
        print(f"sign_zxp: {e.error}" + (f"\n  how: {e.how}" if e.how else ""), file=sys.stderr)
        return 2
    for k, val in r.items():
        print(f"{k}: {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
