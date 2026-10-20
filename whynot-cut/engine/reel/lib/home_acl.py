"""The engine home's access list (BL-16). The engine home holds the Python runtime and the models, so an account that
may change files there could plant code that runs as the editor.

* `prepare_home(home)` (reel setup, before anything is written there): on Windows, outside the user profile,
  - a NEW home (e.g. D:\\WhyNotCut: a folder made at a drive root inherits "Authenticated Users: Modify") is created
    exclusively and locked right away: `icacls <home> /inheritance:r /grant:r <user SID>:(OI)(CI)F
    *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F`, then read back (and must still be empty). If that fails, the new
    folder is removed and HomeAclError (Arabic first, with the exact command) stops setup;
  - an EXISTING home other accounts may write in, or with a top-level item another account owns, stops setup the
    same way (setup never continues on one).
  A home or parent that is a junction or symlink stops setup on every system, new or existing.
* `doctor_fixes(home)` (reel doctor, every time): Windows reads the ACL; a write right for any SID but the user,
  SYSTEM and Administrators, another owner, or a top-level item owned by another account is an editor fix with the
  exact command. A home or parent that is a junction or symlink is a fix too. POSIX: no group or other write.

The ACL is read as SDDL: SIDs and the fixed SDDL aliases (SY, BA, AU...), never account names, so a localized Windows
reads the same. icacls and whoami run only from System32 (never PATH, L-G11), as a list argv with no shell.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .errors import Guidance
from .linksafe import is_link

SYSTEM, ADMINS, CREATOR_OWNER = "S-1-5-18", "S-1-5-32-544", "S-1-3-0"
# every SDDL alias that is the same SID on every machine (the domain-relative ones, DA, DU..., stay as letters)
_ALIASES = {"SY": SYSTEM, "BA": ADMINS, "WD": "S-1-1-0", "AU": "S-1-5-11", "BU": "S-1-5-32-545", "IU": "S-1-5-4",
            "CO": CREATOR_OWNER, "OW": "S-1-3-4", "BG": "S-1-5-32-546", "PU": "S-1-5-32-547", "AN": "S-1-5-7",
            "NU": "S-1-5-2", "NS": "S-1-5-20", "LS": "S-1-5-19", "AC": "S-1-15-2-1", "CG": "S-1-3-1",
            "AO": "S-1-5-32-548", "SO": "S-1-5-32-549", "PO": "S-1-5-32-550", "BO": "S-1-5-32-551",
            "RE": "S-1-5-32-552", "RU": "S-1-5-32-554", "RD": "S-1-5-32-555", "NO": "S-1-5-32-556",
            "MU": "S-1-5-32-558", "LU": "S-1-5-32-559", "IS": "S-1-5-32-568", "CY": "S-1-5-32-569",
            "ER": "S-1-5-32-573", "CD": "S-1-5-32-574", "RA": "S-1-5-32-575", "ES": "S-1-5-32-576",
            "MS": "S-1-5-32-577", "HA": "S-1-5-32-578", "AA": "S-1-5-32-579", "RM": "S-1-5-32-580",
            "SU": "S-1-5-6", "ED": "S-1-5-9", "PS": "S-1-5-10", "RC": "S-1-5-12", "WR": "S-1-5-33"}
_NAMES = {"S-1-1-0": "Everyone", "S-1-5-11": "Authenticated Users", "S-1-5-32-545": "Users",
          "S-1-5-4": "Interactive users", "S-1-5-32-546": "Guests", "S-1-5-7": "Anonymous",
          "S-1-15-2-1": "All app packages"}
# SDDL rights (generic, standard, file / directory-service letters, which share the same bits)
_RIGHTS = {"GA": 0x10000000, "GX": 0x20000000, "GW": 0x40000000, "GR": 0x80000000, "SD": 0x10000, "RC": 0x20000,
           "WD": 0x40000, "WO": 0x80000, "CC": 0x1, "DC": 0x2, "LC": 0x4, "SW": 0x8, "RP": 0x10, "WP": 0x20,
           "DT": 0x40, "LO": 0x80, "CR": 0x100, "FA": 0x1F01FF, "FR": 0x120089, "FW": 0x120116, "FX": 0x1200A0}
# write data / add file, append / add folder, delete child, delete, change permissions, take ownership, generic
# write and all: anything that lets an account put or swap a file
_WRITE = 0x2 | 0x4 | 0x40 | 0x10000 | 0x40000 | 0x80000 | 0x40000000 | 0x10000000
_DENY = {"D", "OD", "XD"}
_SID_RE = re.compile(r"S-1-\d+(-\d+)+")
_UNREADABLE = "an access entry this check cannot read"


class HomeAclError(OSError):
    def __init__(self, msg: str, how: str):
        super().__init__(msg)
        self.how = how


def system32(name: str, environ=None) -> str:
    env = os.environ if environ is None else environ
    return os.path.join(env.get("SystemRoot", r"C:\Windows"), "System32", name)


def current_user_sid(runner=subprocess.run, environ=None) -> str:
    """The SID of the user this process runs as, from System32's `whoami /user` (CSV: "name","S-1-5-..."). OSError
    when it cannot be told."""
    try:
        r = runner([system32("whoami.exe", environ), "/user", "/fo", "csv", "/nh"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise OSError(f"whoami failed ({type(e).__name__})") from e
    sid = (r.stdout or b"").decode("utf-8", "replace").strip().rsplit(",", 1)[-1].strip().strip('"')
    if r.returncode != 0 or not _SID_RE.fullmatch(sid):
        raise OSError("cannot tell which user this process runs as (no SID)")
    return sid


def _ops(sid: str, remove=()) -> list[str]:
    rm = [x for s in remove for x in ("/remove:g", f"*{s}")]
    return ["/inheritance:r", *rm, "/grant:r", *(f"*{s}:(OI)(CI)F" for s in (sid, SYSTEM, ADMINS))]


def lock_argv(home, sid: str, environ=None, remove=()) -> list[str]:
    """icacls: inherited entries off, the explicit grants of `remove` (SIDs) off, full control for the user, SYSTEM
    and Administrators only, inherited by everything inside."""
    return [system32("icacls.exe", environ), str(home), *_ops(sid, remove)]


def lock_command(home, sid: str, remove=()) -> str:
    """The same command for the editor to type in PowerShell or Command Prompt: every SID argument in quotes, or
    PowerShell would read (OI) as a command. (Git Bash may rewrite the /switches of a native command, so the texts
    name the two shells.)"""
    return f'icacls "{home}" ' + " ".join(a if a.startswith("/") else f'"{a}"' for a in _ops(sid, remove))


def _mask(rights: str) -> int:
    if rights.lower().startswith("0x"):
        return int(rights, 16)
    if rights.isdigit():
        return int(rights)
    parts = [rights[i:i + 2] for i in range(0, len(rights), 2)]
    return sum(_RIGHTS.get(p, _WRITE) for p in parts)                  # an unknown letter pair counts as write


def _sid(field: str, user_sid: str) -> str:
    if field == "LA" and user_sid.endswith("-500"):                     # the built-in Administrator account itself
        return user_sid
    return _ALIASES.get(field, field)


def _label(sid: str) -> str:
    return f"{_NAMES[sid]} ({sid})" if sid in _NAMES else sid


def owner_of(sddl: str, user_sid: str = "") -> str | None:
    m = re.search(r"O:(.*?)(?=G:|D:|S:|$)", sddl)
    return _sid(m.group(1), user_sid) if m else None


def _problems(sddl: str, user_sid: str) -> list[tuple[str | None, str]]:
    """[(SID whose explicit grant the fix removes, or None; label)] for acl_problems."""
    ok = {user_sid, SYSTEM, ADMINS, CREATOR_OWNER}    # Creator Owner only reaches what an account may create anyway
    out: list[tuple[str | None, str]] = []

    def add(sid, label):
        if label not in (lb for _, lb in out):
            out.append((sid, label))
    dacl = re.search(r"D:([A-Z_]*)(.*)$", sddl)
    if not dacl or "NO_ACCESS_CONTROL" in dacl.group(1):
        add(None, "Everyone (no access list)")
    else:
        aces = re.findall(r"\(([^()]*)\)", dacl.group(2))
        if dacl.group(2).count("(") != len(aces):
            add(None, _UNREADABLE)
        for ace in aces:
            f = ace.split(";")
            if len(f) < 6:
                add(None, _UNREADABLE)
                continue
            if f[0] in _DENY:
                continue
            sid = _sid(f[5], user_sid)
            if sid not in ok and _mask(f[2]) & _WRITE:
                add(sid if _SID_RE.fullmatch(sid) else None, _label(sid))
    o = owner_of(sddl, user_sid)
    if o is not None and o not in ok - {CREATOR_OWNER}:
        add(None, f"{_label(o)} (owner)")
    return out


def acl_problems(sddl: str, user_sid: str) -> list[str]:
    """Who else may write in the folder this SDDL describes: one label per SID with a write right in an allow entry
    (inherit-only entries count: new files get them), plus an owner other than the user, SYSTEM or Administrators.
    No access list at all (a NULL DACL) is "Everyone"; an entry this reader cannot split (a conditional entry with
    its own brackets) is a problem too."""
    return [label for _, label in _problems(sddl, user_sid)]


def read_sddl(path) -> str:
    """Windows: the owner and access list of `path` as SDDL (Win32 GetNamedSecurityInfoW). OSError when unreadable."""
    import ctypes
    from ctypes import wintypes
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    vp = ctypes.c_void_p
    adv.GetNamedSecurityInfoW.argtypes = (wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD, vp, vp, vp, vp,
                                          ctypes.POINTER(vp))
    adv.GetNamedSecurityInfoW.restype = wintypes.DWORD
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = (vp, wintypes.DWORD, wintypes.DWORD,
                                                                         ctypes.POINTER(vp), vp)
    k32.LocalFree.argtypes = (vp,)
    k32.LocalFree.restype = vp
    sd = vp()
    # 1 = SE_FILE_OBJECT; OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
    rc = adv.GetNamedSecurityInfoW(str(path), 1, 0x1 | 0x4, None, None, None, None, ctypes.byref(sd))
    if rc != 0:
        raise OSError(f"cannot read the access list of {path} ({rc})")
    try:
        text = vp()
        if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(sd, 1, 0x1 | 0x4, ctypes.byref(text), None):
            raise OSError(f"cannot read the access list of {path} ({ctypes.get_last_error()})")
        try:
            return ctypes.wstring_at(text.value)
        finally:
            k32.LocalFree(text)
    finally:
        k32.LocalFree(sd)


def under_profile(home, environ=None) -> bool:
    env = os.environ if environ is None else environ
    prof = env.get("USERPROFILE")
    if not prof:
        return False
    h, p = (os.path.normcase(os.path.realpath(x)) for x in (home, prof))    # a junction inside is not the profile
    try:
        return os.path.commonpath([h, p]) == p
    except ValueError:                                                     # another drive
        return False


def _link_problem(home: Path) -> str | None:
    for p in (home, home.parent):
        try:
            if is_link(p):
                return str(p)
        except Guidance:                                                   # can't tell = a link (linksafe fails closed)
            return str(p)
    return None


def _foreign_items(home: Path, sid: str, read) -> list[str]:
    """Top-level items of the home owned by another account (it could change them whatever the home's own list)."""
    ok = {sid, SYSTEM, ADMINS}
    with os.scandir(home) as it:
        return sorted(e.name for e in it if owner_of(read(e.path), sid) not in ok)


_NEW_HOME_HOW = ("point WHYNOT_HOME to a new empty folder, open a new Claude Code session, then reel setup (it builds "
                 "the engine there)")


def _open_fix_how(home, sid: str, todo) -> str:
    return (f"run in PowerShell or Command Prompt: {lock_command(home, sid, [s for s, _ in todo if s])}   (only if "
            "you made this folder and it holds only the engine; if it says access is denied, another account made it: "
            "point WHYNOT_HOME to a new empty folder instead)")


def prepare_home(home, *, is_win: bool | None = None, environ=None, runner=subprocess.run, sid: str | None = None,
                 read=None) -> bool:
    """reel setup, before anything is written in the engine home: create it (parents as needed) and, on Windows
    outside the user profile, lock a new one to the user, SYSTEM and Administrators, or refuse an existing one that
    other accounts may write in. True when it was made here. Raises HomeAclError (a new folder is removed again)."""
    home = Path(home)
    is_win = os.name == "nt" if is_win is None else is_win
    read = read or read_sddl
    existed = home.is_dir()
    if os.path.lexists(home) and not existed:
        raise HomeAclError(f"فيه ملف مكان فولدر المحرك {home} / a file is in the way of the engine home {home}",
                           "point WHYNOT_HOME to a folder, open a new session, then reel setup again")
    bad = _link_problem(home)
    if bad:
        raise HomeAclError(f"فولدر المحرك {home} أو الفولدر اللي فوقه اختصار (junction أو symlink)، فالإعداد وقف / "
                           f"the engine home {home} or its parent folder is a link ({bad}), so setup stopped",
                           "pick a real folder: set WHYNOT_HOME to it, open a new session, then reel setup again")
    if not existed:
        try:
            home.parent.mkdir(parents=True, exist_ok=True)
            os.mkdir(home)                             # exclusive: FileExistsError if another process made it first
        except OSError as e:
            raise HomeAclError(f"مقدرناش نعمل فولدر المحرك {home}، فالإعداد وقف / could not create the engine home "
                               f"{home} ({type(e).__name__}), so setup stopped",
                               "pick another folder: set WHYNOT_HOME to it, open a new session, then reel setup "
                               "again") from e
    if not is_win or under_profile(home, environ):
        return not existed
    if existed:
        try:
            sid = sid or current_user_sid(environ=environ)
            todo = _problems(read(home), sid)
            foreign = _foreign_items(home, sid, read)
        except OSError as e:
            raise HomeAclError(f"مقدرناش نقرا صلاحيات فولدر المحرك {home} / cannot read the access list of the "
                               f"engine home {home} ({e})", "run reel setup again; if it repeats, send this report") from e
        if todo or foreign:
            who = [lb for _, lb in todo] + [f"{n} (another owner)" for n in foreign]
            raise HomeAclError(f"حسابات تانية على الجهاز تقدر تغيّر في فولدر المحرك {home}، فالإعداد وقف / other "
                               f"accounts on this PC may change files in the engine home {home} "
                               f"({', '.join(who)}), so setup stopped",
                               _NEW_HOME_HOW if foreign else _open_fix_how(home, sid, todo) + "; then reel setup again")
        return False
    cmd = None
    try:
        sid = sid or current_user_sid(environ=environ)
        cmd = lock_command(home, sid)
        r = runner(lock_argv(home, sid, environ), capture_output=True, timeout=60)
        if r.returncode != 0:
            raise OSError(f"icacls exit {r.returncode}")
        left = acl_problems(read(home), sid)
        if left:
            raise OSError("still writable by " + ", ".join(left))
        if os.listdir(home):                           # made by someone else in the moment before the lock
            raise OSError("something appeared in the new folder before it was locked")
    except (OSError, subprocess.SubprocessError) as e:
        try:
            os.rmdir(home)                             # only an EMPTY folder goes; a next setup creates it again
        except OSError:
            pass
        raise HomeAclError(f"مقدرناش نقفل فولدر المحرك {home} على حسابك بس، فالإعداد وقف (حساب تاني على الجهاز كان "
                           f"هيقدر يغيّر فيه) / could not lock the engine home {home} to your account ({e}), so setup "
                           "stopped: another account on this PC could change the engine there",
                           (f"run in PowerShell or Command Prompt: {cmd}  then reel setup again (or point "
                            "WHYNOT_HOME to a new folder)"
                            if cmd else "run reel setup again; if it repeats, send this report")) from e
    return True


def doctor_fixes(home, *, is_win: bool | None = None, read=None, sid: str | None = None) -> list[dict]:
    """Doctor's fixes for the engine home: a link, or a folder other accounts may write in. None for a missing home."""
    home = Path(home)
    is_win = os.name == "nt" if is_win is None else is_win
    read = read or read_sddl
    if not os.path.lexists(home):
        return []
    if is_win:
        fixes = []
        bad = _link_problem(home)
        if bad:
            fixes.append({"item": f"the engine home {home} is reached through a link ({bad}): the engine never "
                                  "trusts a junction or symlink for its own runtime", "who": "editor",
                          "fix": "set WHYNOT_HOME to the real folder (or a new one), open a new Claude Code session, "
                                 "then reel setup"})
        try:
            sid = sid or current_user_sid()
            todo = _problems(read(home), sid)
            foreign = _foreign_items(home, sid, read) if home.is_dir() else []
        except OSError as e:
            return fixes + [{"item": f"the access list of the engine home {home} could not be read ({e})",
                             "who": "editor", "fix": "run reel doctor again; if it repeats, send this report"}]
        if todo:
            fixes.append({"item": f"other accounts on this PC may change files in the engine home {home} "
                                  f"({', '.join(lb for _, lb in todo)}): one could plant code that runs as you",
                          "who": "editor", "fix": _open_fix_how(home, sid, todo) + "; then reel doctor again"})
        if foreign:
            fixes.append({"item": f"items in the engine home {home} belong to another account ({', '.join(foreign)}):"
                                  " it could change the engine whatever the folder's own access list says",
                          "who": "editor", "fix": _NEW_HOME_HOW})
        return fixes
    try:
        mode = os.stat(home).st_mode
    except OSError as e:                                                   # e.g. a symlink to nothing
        return [{"item": f"the engine home {home} could not be read ({type(e).__name__})", "who": "editor",
                 "fix": "set WHYNOT_HOME to the real folder (or a new one), open a new Claude Code session, then "
                        "reel setup"}]
    if mode & 0o022:
        return [{"item": f"the engine home {home} is writable by the group or others: another account could plant "
                         "code that runs as you", "who": "editor",
                 "fix": f'run in a terminal: chmod go-w "{home}"  then reel doctor again'}]
    return []
