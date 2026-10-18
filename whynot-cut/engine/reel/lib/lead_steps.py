"""Lead-only steps and their approval token: the engine-side second wall (BL-15; Addendum L, L-G13). Stdlib only.

The PreToolUse guard (hooks/guard.py) reads shell text, so a deliberately unusual spelling can get past it. This module
gives the engine its own check:
  * LEAD_STEPS is the ONE table of steps only the lead editor runs. guard.py keeps a copy for its subagent rules (it
    must not pay this module's import on every call); tests/test_lead_token_guard.py pins the two as equal.
  * When the guard allows the LEAD's own plain call of such a step, it writes a single-use token,
    <engine home>/run/lead-tokens/<key>.<nonce>.tok, that expires after TTL_S seconds and names the Claude Code session
    (hook_issue(), issue()). "The lead's call" is checked twice: the hook input has no subagent `agent_type`, AND the
    session's own main transcript holds that exact tool call (not a sidechain), so a payload fed to guard.py by hand
    gets no token; one tool call gets at most one token.
  * cli.main runs a lead-only step only when it consumes a token for the same normalised call (engine_check(),
    take()): any spelling the guard did not see as a plain lead call gets no token, so the engine refuses it, and the
    refusal names the cause (diagnose(): the guard hook is missing from hooks.json, not running, saw no plain lead call,
    could not confirm the call in the transcript, approved another call, or the approval expired). `reel doctor` checks
    the hook registration and a token round trip (doctor_check()).
  * There is no way around it from the environment. The editor's own-terminal escape of the first design
    (WHYNOT_LEAD_TTY=1 with a TTY and no Claude Code variables) was removed on purpose (executor, 2026-10-18; review
    patch-BL-15-core-r1 P1-2): Claude Code could satisfy it three ways (Windows reports the NUL device as a TTY, so
    `env -i ... < /dev/null` passed; `Start-Process -UseNewEnvironment` gives a real console without Claude variables;
    macOS `script` gives a real pty). The editor runs these steps through the lead (Claude); from Phase 6 the panel's
    daemon issues its own token (issue_for(..., issuer="panel")).

What this is and is not: a guard against agent mistakes and prompt injection (an agent steered into running a lead
step through a form the guard does not parse). It is NOT a security boundary against a process running as the same
user: such a process can write a token file, call issue() itself or edit the transcript. The guard confirms the lead's
call only in a transcript whose real path lies in Claude Code's own <claude config>/projects folder, and refuses every
hand write there it can see (Write/Edit/MultiEdit, shell redirects and copies, the PowerShell writers). The gap that
remains, accepted by the executor (2026-10-18): a write the guard cannot see (code a process runs, a path built from a
variable set in an earlier command), and editing the real transcript. Code that imports the engine's library
functions directly (not cli.main) is out of scope here; that is the engine write gate (L-T8).

The key binds the whole call: every argument as written (NFC; `--opt=value` split; on Windows Git Bash's `/d/...` and
`name=/d/...` read as `D:/...`), the real path of each --root value (links and junctions resolved; case folded on
Windows), and, when there is no --root, the real path of the current folder (the engine's default root). Both sides
compute it with key().
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

IS_WIN = os.name == "nt"

# (step, the options that make it lead-only). guard.py's copy (LEAD_STEPS there) must stay equal: a test pins it.
LEAD_STEPS = (
    ("approve-plan", ()), ("auto-approve", ()), ("reels-select", ()),
    ("lock", ("--release",)), ("settings", ("--init",)), ("handoff", ("--delivered",)),
    ("verify", ("--record",)), ("ae-probe", ("--record",)), ("ref-style", ("--adopt", "--yes")),
    ("caption-looks", ("--pick", "--yes")),                 # Task 28: the editor's caption-look swap is recorded
    ("rules", ("--add",)), ("rules", ("--remove",)))        # T4.3: a client rule is written or dropped
# transcript-verify is lead-only unless --by names a subagent (agent, claude, or a WhyNot Cut agent; the guard pins a
# subagent to its own name)
TRANSCRIPT_VERIFY = "transcript-verify"
SUBAGENT_VERIFY_BY = frozenset({"agent", "claude"})
PLUGIN_AGENT = "whynot-cut:"
GLOBAL_VALUE_OPTS = ("--root", "--video-id", "--profile", "--episode")

TTL_S = 120                 # a token lives this long after the guard allowed the call
SKEW_S = 5                  # a token dated further in the future than this is refused
TOKEN_DIR = ("run", "lead-tokens")
USED_KEEP_S = 2 * 86400     # how long a tool call's "token issued" mark is kept
SEEN_FILE = "hook-seen.json"   # the guard's last look at a lead call (time, result, key): only to explain a refusal
TRANSCRIPT_TAIL = 1 << 20   # the transcript bytes searched for the tool call (it is the newest entry)
TRANSCRIPT_WAIT_S = 2.0     # Claude Code writes the transcript asynchronously: the call may land a moment after the hook
RENAME_TRIES = (0.0, 0.05, 0.1, 0.2)                        # a scanner may hold a fresh token open for a moment
_MSYS = re.compile(r"^/([a-zA-Z])(/|$)")
_MSYS_VALUE = re.compile(r"^([^=/\\]+=)/([a-zA-Z])(/|$)")   # Git Bash also converts `name=/d/x`
_NAME = re.compile(r"^([0-9a-f]{64})\.([0-9a-f]{32})\.tok$")
_USED = re.compile(r"^[0-9a-f]{64}\.used$")

REFUSAL_HEAD = ("الخطوة دي للمحرر بس (`{step}`). لو انت المحرر: شغّلها من Claude نفسه، مكالمة واحدة بسيطة "
                "(ولو اترفضت تاني شغّل reel doctor). "
                "This step is the lead editor's only (`{step}`); this call came without the guard's approval for "
                "exactly this call.")
# why no token was found (diagnose()), Arabic first
CAUSES = {
    "missing": ("الحماية (guard hook) مش متسجلة في البلجن، فمحدش بيدي موافقة. "
                "The guard hook is not registered in the plugin's hooks/hooks.json, so nothing issues approvals: "
                "update or reinstall WhyNot Cut."),
    "not-running": ("الحماية (guard hook) مش شغّالة دلوقتي (مفيش نبضة منها). "
                    "The guard hook is not running (no recent heartbeat): the plugin may be disabled, or Git Bash / "
                    "the engine's Python is missing on this machine."),
    "not-seen": ("الحماية ما شافتش الأمر ده كمكالمة واحدة بسيطة من المحادثة الرئيسية. "
                 "The guard did not see this call as one plain call from the main conversation (a subagent's call, "
                 "or a call with cd, variables or something chained gets no approval)."),
    "not-plain": ("آخر أمر شافته الحماية ما كانش مكالمة واحدة بسيطة. "
                  "The last call the guard saw was not one plain call (cd, variables, chaining, a redirect)."),
    "not-confirmed": ("الحماية ما لقيتش الأمر ده في سجل الجلسة. شغّله تاني. "
                      "The guard could not confirm this call in the session's transcript: run it again."),
    "other-call": ("الحماية وافقت على أمر تاني (فولدر أو اختيارات مختلفة). "
                   "The guard approved a different call (another folder or other options) than the one that ran."),
    "other-session": ("الموافقة دي بتاعة جلسة Claude تانية. "
                      "The approval for this call belongs to another Claude Code session; run it in this session."),
    "used": ("الموافقة دي اتستخدمت قبل كده. كل موافقة لمرة واحدة. "
             "That approval was already used: each approval is for one run."),
    "expired": ("الموافقة خلص وقتها (أكتر من دقيقتين). شغّل نفس الأمر تاني. "
                "The approval expired (more than 2 minutes passed, e.g. at the permission prompt). Run the same "
                "command again."),
}
REFUSAL_HOW = ("Run it from the main conversation as one plain call: `reel {step} ...` with an absolute --root, no cd "
               "and no variables, nothing chained before it (a trailing `2>&1 | tail` is fine). A subagent reports to "
               "the lead instead. `reel doctor` checks the guard and its approvals.")


# --------------------------------------------------------------------------- which calls are lead-only
def _split_eq(args) -> list[str]:
    """`--opt=value` -> `--opt`, `value` (what argparse does for a long option)."""
    out = []
    for a in args:
        a = str(a)
        if a.startswith("--") and "=" in a:
            out += a.split("=", 1)
        else:
            out.append(a)
    return out


def subcommand(args) -> tuple[str | None, list[str]]:
    """(the subcommand, the words after it): the first word that is neither an option nor a global option's value."""
    toks = _split_eq(args)
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.startswith("-"):
            i += 2 if t in GLOBAL_VALUE_OPTS else 1
            continue
        return t, toks[i + 1:]
    return None, []


def subagent_verify_by() -> frozenset:
    """The --by values a subagent may record transcript-verify under: agent, claude, and this plugin's agent names
    (short and `whynot-cut:` forms), read from the plugin's agents/ folder."""
    names = set(SUBAGENT_VERIFY_BY)
    agents = Path(__file__).resolve().parents[3] / "agents"
    try:
        for p in agents.iterdir():
            if p.suffix == ".md":
                names |= {p.stem.lower(), PLUGIN_AGENT + p.stem.lower()}
    except OSError:
        pass
    return frozenset(names)


def _label(step: str, opts: tuple) -> str:
    return " ".join((step,) + tuple(opts))


def _verify_by_is_lead(by) -> bool:
    return by is None or str(by).strip().lower() not in subagent_verify_by()


def lead_step(args) -> str | None:
    """The lead-only step this argv (the engine's arguments, after `reel`) runs, as its label, or None. Text rules,
    the same as argparse's (exact option names; the CLI refuses abbreviations; the last --by wins)."""
    sub, rest = subcommand(args)
    if sub is None:
        return None
    for step, opts in LEAD_STEPS:
        if sub == step and all(o in rest for o in opts):
            return _label(step, opts)
    if sub == TRANSCRIPT_VERIFY:
        bys = [rest[i + 1] for i, t in enumerate(rest[:-1]) if t == "--by"]
        return TRANSCRIPT_VERIFY if _verify_by_is_lead(bys[-1] if bys else None) else None
    return None


def lead_step_ns(ns) -> str | None:
    """The same answer from the engine's parsed argparse namespace (the authoritative reading)."""
    sub = getattr(ns, "cmd", None)
    for step, opts in LEAD_STEPS:
        if sub == step and all(getattr(ns, o[2:].replace("-", "_"), None) for o in opts):
            return _label(step, opts)
    if sub == TRANSCRIPT_VERIFY:
        return TRANSCRIPT_VERIFY if _verify_by_is_lead(getattr(ns, "by", None)) else None
    return None


# --------------------------------------------------------------------------- the key of one call
def _nfc(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFC", s)


def _native(s: str) -> str:
    """On Windows, Git Bash's `/d/x` is `D:/x`, also as a `name=/d/x` value (Git Bash converts both before Python sees
    them; plat.native_path)."""
    if IS_WIN:
        m = _MSYS.match(s)
        if m:
            return f"{m.group(1).upper()}:/{s[3:]}"
        m = _MSYS_VALUE.match(s)
        if m:
            return f"{m.group(1)}{m.group(2).upper()}:/{s[len(m.group(1)) + 3:]}"
    return s


def _realpath(p: str) -> str:
    return os.path.realpath(p)


def _normcase(p: str) -> str:
    return os.path.normcase(p) if IS_WIN else p


def _real(p: str, cwd: str) -> str:
    p = os.path.expanduser(_native(p))
    if not os.path.isabs(p) and not (IS_WIN and re.match(r"^[A-Za-z]:[\\/]", p)):
        p = os.path.join(_native(cwd), p)
    return _nfc(_normcase(_realpath(p)))


def normalise(args, cwd: str) -> list[str]:
    """The call as both sides see it: every word NFC (`--opt=value` split, Git Bash drive paths read as Windows ones),
    each --root value as its real path, and the real current folder when there is no --root."""
    toks = [_native(_nfc(t)) for t in _split_eq(args)]
    out, rooted, i = [], False, 0
    while i < len(toks):
        if toks[i] == "--root" and i + 1 < len(toks):
            out += ["--root", _real(toks[i + 1], cwd)]
            rooted = True
            i += 2
            continue
        out.append(toks[i])
        i += 1
    if not rooted:
        out += ["\0cwd", _real(cwd, cwd)]
    return out


def key(args, cwd: str) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps(normalise(args, cwd), ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- tokens
def token_dir(home: Path | None = None) -> Path:
    if home is None:
        try:
            from . import plat
        except ImportError:                         # the guard imports this module from engine/reel/lib directly
            import plat
        home = plat.engine_home()
    return Path(home).joinpath(*TOKEN_DIR)


def in_token_dir(path: str) -> bool:
    """The REAL path (links, junctions, 8.3 names resolved; any case) lies in a run/lead-tokens folder. guard.py
    applies the same rule to every write target (it keeps its own copy, without this module's imports)."""
    try:
        parts = [x.lower() for x in re.split(r"[\\/]+", os.path.realpath(path))]
    except (OSError, ValueError):
        return False
    return any(parts[i:i + 2] == list(TOKEN_DIR) for i in range(len(parts) - 1))


def claude_config_dir() -> Path:
    """Claude Code's own folder (CLAUDE_CONFIG_DIR, else ~/.claude); its projects/ folder holds the transcripts."""
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude").expanduser()


def in_transcript_store(path: str) -> bool:
    """The REAL path lies under the real <claude config>/projects folder (links and junctions resolved: on this PC
    ~/.claude is a junction to another drive). guard.py refuses every hand write there."""
    try:
        real = os.path.normcase(os.path.realpath(path))
        store = os.path.normcase(os.path.realpath(claude_config_dir() / "projects"))
    except (OSError, ValueError):
        return False
    return real.startswith(store.rstrip("\\/") + os.sep)


def _session_env() -> str:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or ""


def _read(p: Path) -> dict | None:
    import json
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _unlink(p: Path):
    try:
        os.unlink(p)
    except OSError:
        pass


def _rename(src: Path, dst: Path) -> bool:
    """os.rename with short retries: on Windows a scanner may hold a fresh file open (sharing violation) for a moment.
    False when the source is gone (another process took it) or stays locked."""
    for wait in RENAME_TRIES:
        if wait:
            time.sleep(wait)
        try:
            os.rename(src, dst)
            return True
        except FileNotFoundError:
            return False
        except PermissionError:
            continue
        except OSError:
            return False
    return False


def _write_new(p: Path, body: bytes):
    """Exclusive create (never follows or replaces anything already there), 0600 on POSIX."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(p, flags, 0o600)
    try:
        os.write(fd, body)
    finally:
        os.close(fd)


def _stamp(d: Path, result: str, k: str = ""):
    """The guard's last look at a lead call, for diagnose(): replaced atomically, never read as an approval."""
    import json
    tmp = d / f".{SEEN_FILE}.{os.getpid()}.{os.urandom(4).hex()}"
    try:
        tmp.write_text(json.dumps({"time": time.time(), "result": result, "key": k}), encoding="utf-8")
        os.replace(tmp, d / SEEN_FILE)
    except OSError:
        _unlink(tmp)


def cleanup(d: Path, now: float | None = None):
    """Remove expired tokens, crash leftovers (claimed files) and old "token issued" marks from the token folder, by
    file age (one stat each, no read): a token file older than TTL_S + SKEW_S can no longer be valid, whatever it says
    (consume() caps a token's life at TTL_S from its issue time; a claim gets a fresh time when it is made). Only file
    names this module writes are touched; folders are left alone."""
    now = time.time() if now is None else now
    try:
        entries = list(os.scandir(d))
    except OSError:
        return
    for e in entries:
        name = e.name
        if name.endswith(".claim"):
            ok, limit = _NAME.match(name.split(".tok.", 1)[0] + ".tok") is not None, TTL_S + SKEW_S
        elif name.endswith(".used"):
            ok, limit = _USED.match(name) is not None, USED_KEEP_S
        else:
            ok, limit = _NAME.match(name) is not None, TTL_S + SKEW_S
        if not ok:
            continue
        try:
            if e.is_dir(follow_symlinks=False) or now - e.stat(follow_symlinks=False).st_mtime <= limit:
                continue
        except OSError:
            continue
        _unlink(d / name)


def _prepare(home: Path | None, now: float) -> Path:
    d = token_dir(home)
    os.makedirs(d, mode=0o700, exist_ok=True)
    if not IS_WIN:
        os.chmod(d, 0o700)                          # also a folder made earlier with a wider mode
    cleanup(d, now)
    return d


def issue(args, cwd: str, session: str | None = None, issuer: str = "hook", now: float | None = None,
          home: Path | None = None, tool_use_id: str = "") -> Path:
    """Write one single-use token for this call (exclusive create; 0600 in a 0700 folder on POSIX) and return its
    path. session: the Claude Code session id (the hook input's), None = this process's CLAUDE_CODE_SESSION_ID."""
    import json
    now = time.time() if now is None else now
    d = _prepare(home, now)
    k, nonce = key(args, cwd), os.urandom(16).hex()
    p = d / f"{k}.{nonce}.tok"
    _write_new(p, json.dumps({"v": 1, "key": k, "nonce": nonce,
                              "session": _session_env() if session is None else session, "issued": now,
                              "expires": now + TTL_S, "issuer": issuer, "tool_use_id": tool_use_id}).encode("utf-8"))
    return p


def issue_if_lead(args, cwd: str | None = None, session: str | None = None, issuer: str = "panel",
                  home: Path | str | None = None) -> Path | None:
    """Issue a token only when the call is a lead-only step (else None). For a caller that starts the engine itself
    on the editor's behalf: the panel's daemon (Phase 6), and tests that run a lead-only step through cli.py.
    cwd: the folder the engine will run in (None = this process's); session and home: the ones the engine process
    will see (None = this process's)."""
    if lead_step(args) is None:
        return None
    return issue(args, os.getcwd() if cwd is None else str(cwd), session=session, issuer=issuer,
                 home=Path(home) if home else None)


def issue_for(args, env=None, cwd: str | None = None, issuer: str = "panel") -> Path | None:
    """issue_if_lead for an engine process started with the environment `env` (None = this process's): its session id
    and engine home are taken from that environment, so the engine finds the token. The panel's daemon and the tests
    that start cli.py use it."""
    e = os.environ if env is None else env
    return issue_if_lead([str(a) for a in args], cwd=cwd, session=e.get("CLAUDE_CODE_SESSION_ID") or "",
                         issuer=issuer, home=e.get("WHYNOT_HOME") or None)


def _verdict(data: dict | None, k: str, nonce: str, now: float) -> str:
    """ok | expired | session (valid for another session) | bad."""
    if not data or data.get("v") != 1 or data.get("key") != k or data.get("nonce") != nonce:
        return "bad"
    issued, expires = data.get("issued"), data.get("expires")
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (issued, expires)):
        return "bad"
    if issued > now + SKEW_S or expires - issued > TTL_S:
        return "bad"
    if now > expires:
        return "expired"
    return "ok" if data.get("session", "") == _session_env() else "session"


def take(args, cwd: str, now: float | None = None, home: Path | None = None) -> str:
    """Find and use up one valid token for this call. Returns "ok", "expired" (only expired ones were found),
    "other-session" (only another Claude Code session's) or "none". A token is claimed by an atomic rename (two processes never use the same one), read, then deleted; one
    that belongs to another Claude Code session is put back untouched. Never creates the folder."""
    now = time.time() if now is None else now
    d, k = token_dir(home), key(args, cwd)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return "none"
    seen_expired = seen_other = False
    for name in names:
        m = _NAME.match(name)
        if not m or m.group(1) != k:
            continue
        src = d / name
        claim = d / f"{name}.{os.getpid()}.{os.urandom(4).hex()}.claim"
        if not _rename(src, claim):
            continue                                # another process took it, or it is gone
        try:
            os.utime(claim)                         # cleanup() judges a claim by its own age, not the token's
        except OSError:
            pass
        data = _read(claim) if os.path.isfile(claim) and not os.path.islink(claim) else None
        verdict = _verdict(data, k, m.group(2), now)
        if verdict == "session" and _rename(claim, src):
            seen_other = True
            continue                                # another session's token: back where it was
        _unlink(claim)
        if verdict == "ok":
            return "ok"
        seen_expired = seen_expired or verdict == "expired"
    return "expired" if seen_expired else "other-session" if seen_other else "none"


def consume(args, cwd: str, now: float | None = None, home: Path | None = None) -> bool:
    return take(args, cwd, now=now, home=home) == "ok"


# --------------------------------------------------------------------------- the guard's side: a plain lead call
# A plain call is ONE engine call whose words the guard can read exactly as the engine will get them: the `reel`
# launcher (any path) or python + engine/reel/cli.py, then literal words only. Allowed after it: `2>&1` and one pipe
# into a read-only text tool. Anything else (a variable, a substitution, a glob, `~`, `cd`, chaining, a redirect, an
# environment prefix) is not plain: no token, and the engine refuses the step.
READERS = {"bash": {"head", "tail", "cat", "grep", "rg", "wc"},
           "powershell": {"select-object", "select", "out-string", "out-host", "format-list", "select-string"}}
_REEL_CLI = re.compile(r"(?:^|[\\/])engine[\\/]reel[\\/]cli\.py$", re.I)
_PY = re.compile(r"^(?:.*[\\/])?(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?$", re.I)
_LAUNCHER = re.compile(r"^(?:.*[\\/])?reel(?:\.cmd|\.bat|\.exe|\.sh)?$", re.I)


def _words_bash(cmd: str) -> list | None:
    """The bash words of a command in the plain subset, with `|` and `2>&1` as markers; None outside the subset."""
    words, cur, has, i, n = [], [], False, 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c in " \t":
            if has:
                words.append("".join(cur))
                cur, has = [], False
            i += 1
        elif c == "'":
            j = cmd.find("'", i + 1)
            if j < 0:
                return None
            cur.append(cmd[i + 1:j])
            has, i = True, j + 1
        elif c == '"':
            i += 1
            while i < n and cmd[i] != '"':
                if cmd[i] in "$`":
                    return None
                if cmd[i] == "\\" and i + 1 < n and cmd[i + 1] in '"\\':
                    i += 1
                cur.append(cmd[i])
                i += 1
            if i >= n:
                return None
            has, i = True, i + 1
        elif c == "\\":
            if i + 1 >= n or cmd[i + 1] in "\r\n":
                return None
            cur.append(cmd[i + 1])
            has, i = True, i + 2
        elif cmd.startswith("2>&1", i) and not has and (i + 4 == n or cmd[i + 4] in " \t"):
            words.append(("2>&1",))
            i += 4
        elif c == "|":
            if cmd.startswith("||", i):
                return None
            if has:
                words.append("".join(cur))
                cur, has = [], False
            words.append(("|",))
            i += 1
        elif c in "$`;&<>(){}[]*?!#~\r\n":
            return None
        else:
            cur.append(c)
            has, i = True, i + 1
    if has:
        words.append("".join(cur))
    return words


def _words_powershell(cmd: str) -> list | None:
    """The PowerShell words of a command in the plain subset (single quotes literal with '' for ', double quotes
    without $ or `), with `|` and `2>&1` as markers; None outside the subset. An empty or quote-holding argument is
    outside it (Windows PowerShell 5.1 drops or mangles those when it starts a program)."""
    words, cur, has, i, n = [], [], False, 0, len(cmd)

    def flush() -> bool:
        w = "".join(cur)
        if not w or '"' in w or w.endswith("\\"):
            return False
        words.append(w)
        return True
    while i < n:
        c = cmd[i]
        if c in " \t":
            if has:
                if not flush():
                    return None
                cur, has = [], False
            i += 1
        elif c == "'":
            i += 1
            while True:
                j = cmd.find("'", i)
                if j < 0:
                    return None
                cur.append(cmd[i:j])
                if cmd.startswith("''", j):
                    cur.append("'")
                    i = j + 2
                    continue
                i = j + 1
                break
            has = True
        elif c == '"':
            j = cmd.find('"', i + 1)
            if j < 0 or any(x in cmd[i + 1:j] for x in "$`"):
                return None
            cur.append(cmd[i + 1:j])
            has, i = True, j + 1
        elif cmd.startswith("2>&1", i) and not has and (i + 4 == n or cmd[i + 4] in " \t"):
            words.append(("2>&1",))
            i += 4
        elif c == "|":
            if cmd.startswith("||", i):
                return None
            if has:
                if not flush():
                    return None
                cur, has = [], False
            words.append(("|",))
            i += 1
        elif c in "$`;&<>(){}[]*?@,#%^~\r\n" or cmd.startswith("--%", i):
            return None
        else:
            cur.append(c)
            has, i = True, i + 1
    if has and not flush():
        return None
    return words


def plain_call(command: str, shell: str) -> list[str] | None:
    """The engine's arguments (after `reel`) when the command is one plain engine call, else None. shell: "bash" or
    "powershell" (the tool that runs it)."""
    if not isinstance(command, str) or len(command) > 8000:
        return None
    ps = shell == "powershell"
    words = (_words_powershell if ps else _words_bash)(command.strip())
    if not words:
        return None
    stages, cur = [], []
    for w in words:
        if w == ("|",):
            stages.append(cur)
            cur = []
        else:
            cur.append(w)
    stages.append(cur)
    if len(stages) > 2 or not stages[0] or isinstance(stages[0][0], tuple):
        return None
    if len(stages) == 2:
        tail = stages[1]
        if not tail or any(isinstance(w, tuple) for w in tail) or tail[0].lower() not in READERS[
                "powershell" if ps else "bash"]:
            return None
    first = stages[0]
    if first.count(("2>&1",)) > 1 or (("2>&1",) in first and first[-1] != ("2>&1",)):
        return None
    first = [w for w in first if w != ("2>&1",)]
    exe = first[0]
    if _LAUNCHER.match(exe):
        return first[1:]
    if _PY.match(exe) and len(first) > 1 and _REEL_CLI.search(first[1]):
        return first[2:]
    return None


def _find_call(p: Path, sid: str, want: str, tool: str, command: str) -> bool | None:
    """True: the transcript's tail holds the main-thread tool call `want` with this tool and command; False: it holds
    that call id but not as such a call (a sidechain, another tool or command); None: not there (yet)."""
    import json
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TRANSCRIPT_TAIL))
            tail = f.read()
    except OSError:
        return None
    needle = want.encode("utf-8")
    for line in reversed(tail.splitlines()):
        if needle not in line or b'"tool_use"' not in line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        content = (entry.get("message") or {}).get("content") if isinstance(entry, dict) else None
        for c in content if isinstance(content, list) else ():
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("id") == want:
                return (not entry.get("isSidechain") and entry.get("sessionId", sid) == sid
                        and c.get("name") == tool and isinstance(c.get("input"), dict)
                        and c["input"].get("command") == command)
    return None


def _transcript_call(data: dict, tool: str, command: str) -> str | None:
    """The hook input's tool call id when the session's own transcript holds it as a MAIN-thread call of this tool
    with this exact command (a subagent's calls live in its own transcript, or are marked isSidechain). Claude Code
    writes the transcript asynchronously, so a call not there yet is looked for again for up to TRANSCRIPT_WAIT_S.
    None when the input has no call id, the transcript is not this session's, or it never holds the call: a payload
    fed to guard.py by hand names no real lead call."""
    sid, want = str(data.get("session_id") or ""), str(data.get("tool_use_id") or "")
    tp = data.get("transcript_path")
    if not sid or not want or not isinstance(tp, str) or not tp:
        return None
    p = Path(tp)
    if p.name != sid + ".jsonl" or not p.is_file() or not in_transcript_store(tp):
        return None
    deadline = time.monotonic() + TRANSCRIPT_WAIT_S
    while True:
        found = _find_call(p, sid, want, tool, command)
        if found is not None:
            return want if found else None
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


_ENGINE_WORD = re.compile(r"(?<![\w.-])(?:reel(?:\.cmd|\.exe)?|cli\.py)(?![\w-])")   # the engine, called somehow


def hook_issue(data: dict) -> Path | None:
    """The guard calls this for a call it has ALLOWED: when it is the lead's (no subagent agent_type, and the
    session's main transcript holds this exact call) plain Bash or PowerShell call of a lead-only step, write its
    token, once per tool call. Never raises: a token that cannot be written only means the engine will refuse the
    step and say why."""
    try:
        if not isinstance(data, dict) or data.get("agent_type") or data.get("agent_id"):
            return None                             # a subagent or an agent-team teammate
        tool = data.get("tool_name")
        if tool not in ("Bash", "PowerShell"):
            return None
        command = str((data.get("tool_input") or {}).get("command") or "")
        args = plain_call(command, "powershell" if tool == "PowerShell" else "bash")
        now = time.time()
        if args is None:
            if _ENGINE_WORD.search(command.lower()):    # a grep that only names a step is no failed engine call
                _stamp(_prepare(None, now), "not-plain")
            return None
        if lead_step(args) is None:
            return None
        cwd = str(data.get("cwd") or os.getcwd())
        k = key(args, cwd)
        call_id = _transcript_call(data, tool, command)
        d = _prepare(None, now)
        if not call_id:
            _stamp(d, "not-confirmed", k)
            return None
        import hashlib
        try:                                        # one tool call, one token (a replayed payload gets none)
            _write_new(d / (hashlib.sha256(call_id.encode("utf-8")).hexdigest() + ".used"), b"")
        except FileExistsError:
            return None
        p = issue(args, cwd, session=str(data.get("session_id") or ""), issuer="hook", now=now, tool_use_id=call_id)
        _stamp(d, "issued", k)
        return p
    except Exception:  # noqa: BLE001  the hook must never fail an allowed call because of the token
        return None


# --------------------------------------------------------------------------- the engine's check
def hook_registered(plugin: Path | None = None) -> bool:
    """The plugin's hooks/hooks.json starts guard.py on PreToolUse for Bash and for PowerShell."""
    import json
    plugin = Path(__file__).resolve().parents[3] if plugin is None else Path(plugin)
    try:
        hooks = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    tools = set()
    for block in hooks if isinstance(hooks, list) else ():
        if isinstance(block, dict) and any(isinstance(h, dict) and "guard.py" in str(h.get("command", ""))
                                           and not h.get("if") for h in block.get("hooks") or ()):
            tools |= set(str(block.get("matcher", "")).split("|"))
    return {"Bash", "PowerShell"} <= tools


def guard_running() -> bool | None:
    """The guard's own heartbeat (guard-ok, lib/onboard.py): True / False, None when it cannot be told (an older
    plugin's guard writes none)."""
    try:
        from . import onboard
    except ImportError:
        return None
    try:
        return onboard.guard_heartbeat()["active"]
    except Exception:  # noqa: BLE001  a diagnosis never stops the refusal itself
        return None


def diagnose(argv, cwd: str, got: str, now: float | None = None, home: Path | None = None) -> str:
    """Why no token was used for this call: a CAUSES key."""
    import json
    if got == "expired":
        return "expired"
    if got == "other-session":
        return "other-session"
    if not hook_registered():
        return "missing"
    if guard_running() is False:
        return "not-running"
    now = time.time() if now is None else now
    seen = _read(token_dir(home) / SEEN_FILE)
    t = seen.get("time") if seen else None
    if not isinstance(t, (int, float)) or isinstance(t, bool) or not 0 <= now - t <= TTL_S + SKEW_S:
        return "not-seen"
    result, k = seen.get("result"), key(argv, cwd)
    if result == "not-plain":
        return "not-plain"
    if seen.get("key") != k:
        return "other-call"
    return {"not-confirmed": "not-confirmed", "issued": "used"}.get(result, "not-seen")


def refusal(step: str, cause: str = "not-seen") -> dict:
    return {"blocked": REFUSAL_HEAD.format(step=step) + " " + CAUSES.get(cause, CAUSES["not-seen"]),
            "how": REFUSAL_HOW.format(step=step.split()[0]), "cause": cause}


def engine_check(ns, argv, cwd: str | None = None) -> dict | None:
    """cli.main calls this after parsing: None = go ahead; else the refusal to print (exit 2), naming its cause. A
    step that is not lead-only never looks for a token."""
    step = lead_step_ns(ns)
    if step is None:
        return None
    cwd = os.getcwd() if cwd is None else cwd
    got = take(argv, cwd)
    return None if got == "ok" else refusal(step, diagnose(argv, cwd, got))


def doctor_check(home: Path | None = None) -> dict:
    """For `reel doctor`: the guard hook is registered for Bash and PowerShell, and a token round trip works in this
    engine home (issue, then take, with this process's session). {"ok", "registered", "round_trip", "fix"}; the round
    trip leaves nothing behind."""
    registered = hook_registered()
    try:
        argv = ["approve-plan", "--by", "editor", "--note", "reel doctor round trip " + os.urandom(6).hex()]
        here = str(token_dir(home).parent.parent)
        issue(argv, here, session=None, issuer="doctor", home=home)
        round_trip, error = take(argv, here, home=home) == "ok", ""
    except Exception as e:  # noqa: BLE001  reported in the fix line, never a crash of `reel doctor`
        round_trip, error = False, f"{type(e).__name__}: {e}"
    fix = None
    if not registered:
        fix = ("WhyNot Cut's guard hook is not in the plugin's hooks/hooks.json, so lead-only steps (approve-plan, "
               "handoff --delivered, ...) are refused: update or reinstall WhyNot Cut, then restart Claude Code.")
    elif not round_trip:
        fix = ("the engine home's run/lead-tokens folder cannot be written or read, so lead-only steps are refused"
               + (f" ({error})" if error else "") + ": check that the engine home is on a writable drive and not "
               "read-only, then run `reel doctor` again.")
    return {"ok": registered and round_trip, "registered": registered, "round_trip": round_trip, "fix": fix}
