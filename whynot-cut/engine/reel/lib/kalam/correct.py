# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
# Ported from the owner's Kalam engine (kalam/correct.py); see adobe/tools/README.md. Changes to the upstream file
# (portability audit §3.1/§5); the contract text, SCHEMA, MODEL, BATCH, CONTEXT, MIN_KEEP and the faithfulness gate are
# unchanged:
#   * `anthropic` is imported lazily, only by the API backend (the core runtime does not include it);
#   * temp folder prefix "wnc-kalam-cc-";
#   * find_claude_code uses the WhyNot Cut discovery rules (platform.claude_install_candidates): PATHEXT instead of
#     os.access(X_OK) on Windows, the `.cmd` shim last;
#   * a `.cmd` CLI is never run through cmd.exe with JSON on argv (platform.claude_command resolves it or refuses);
#   * cancel / timeout kills the CLI and what it started: the tree on Windows (lib/parallel.kill_tree, taskkill /T), the
#     CLI's own process group on POSIX (it is started in a new session and the group is killed);
#   * what lib/parallel tracks is a handle (_CliHandle) whose kill() also kills the CLI's process group on POSIX, so a
#     grandchild holding the pipes cannot keep a cancelled run waiting for CLI_TIMEOUT;
#   * a cancelled run (lib/parallel) starts no further batch or retry and ends with error "cancelled";
#   * find_claude_code searches every absolute PATH folder itself (platform.find_on_path): a planted claude.exe in the
#     current folder neither runs nor hides the real CLI (Task 10 re-review);
#   * a refused `.cmd` shim is the error code "cmd_shim_refused" with the help text in stats["how"] (make_client: the
#     notice of the same name, `notice_how` gives the text);
#   * subscription preflight (executor ruling, TOOLS-NOTE-claude-p-auth-sources): `claude -p` can bill an API key from the
#     user's settings env or apiKeyHelper even when our child env is clean, and the subscription login comes last in its
#     auth precedence. So once per job `claude --safe-mode auth status` runs (same env, neutral temp cwd, no prompt text) and
#     unless authMethod == "claude.ai" the backend does not start `claude -p`: error "subscription_not_active" (or
#     "auth_status_unavailable" when the check itself fails), a `how` in Arabic + English naming the method found, captions
#     keep their source text. Only authMethod / loggedIn are read; email, org and tokens are never kept, logged or shown;
#   * find_claude_code keeps only absolute paths: a CWD-relative claude.exe is never started (Task 10 review I1);
#   * RULE (owner: nothing paid): the subscription backend runs `claude -p` with an explicit environment that lacks
#     ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN and the provider switches CLAUDE_CODE_USE_BEDROCK, CLAUDE_CODE_USE_VERTEX and
#     ANTHROPIC_BASE_URL (API_BILLING_VARS; _child_env matches case-insensitively on Windows, exactly on POSIX), so it can
#     never fall into API billing or a paid provider / proxy silently. os.environ itself is never modified; the API backend (the `anthropic` client) keeps its key.
"""Correct caption phrases with Claude by the user's rules. Timecodes never leave this machine: only text is sent,
and the reply must have exactly one line per phrase or the source text is kept."""
import importlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import signal
from ..parallel import cancelled, kill_tree, track, untrack
from . import platform as _platform
from .similar import close as _close, tokens as _tokens

MODEL = "claude-opus-5-5"
BATCH = 60
CONTEXT = 3
MIN_KEEP = 0.6          # a line shorter than 60% of its source was shortened, not corrected
CLI_TIMEOUT = 900       # seconds one `claude -p` call may take
_HERE = Path(__file__).parent
DEFAULT_RULES = (_HERE / "default_rules.txt").read_text(encoding="utf-8")
DEFAULT_RULES_EN = (_HERE / "default_rules_en.txt").read_text(encoding="utf-8")


def default_rules(mode: str) -> str:
    """the user's Arabic rules for Arabic mode; a short language-neutral set for English and other languages"""
    return DEFAULT_RULES if mode == "ar" else DEFAULT_RULES_EN


CONTRACT = """
طريقة الرد:
- هتستلم JSON فيه "context_before" و"context_after" (للفهم بس، ما تصححهمش ولا ترجعهم) و"lines" (الجمل المطلوب تصحيحها).
- رجّع "lines" بنفس العدد بالظبط وبنفس الترتيب: كل عنصر هو نفس الجملة بعد التصحيح فقط.
- لو جملة مش محتاجة تعديل رجّعها زي ما هي.

علامات الكابشن (مهمة جدًا):
- حط علامة | في المكان اللي بتخلص فيه جملة أو وحدة معنى زي ما المتكلم بيقولها، عشان كل كابشن يبقى جملة كاملة على قد نبرة صوته.
  مثال: "الشغل الجامد | مش هيرقيك | لو ما حدش شايف إن انت جامد |"
- لو السطر بيخلص بجملة كاملة حط | في آخره. لو الجملة مكملة في السطر اللي بعده (المتكلم وقف في نصها) ما تحطش | في الآخر.
- الوحدة من 2 لـ 7 كلمات بالكتير. لو الجملة أطول قسّمها عند أقرب وقفة طبيعية في المعنى.
- ما تقسمش مصطلح ولا "الـ" عن الكلمة اللي بعدها، وما تحطش | جوه جملة قصيرة.
- أمثلة مظبوطة: "لو ما حدش شايف إن انت جامد |"، "حتى لو كنت بتقدم كل حاجة في معادها |"، "نتائجك كويسة | ومجتهد جدًا | وبتحط مجهود كبير قوي في الشغل |"، "لأن الترقية ما بتحصلش بس | على أساس المجهود اللي انت حاطه النهارده |"
- العلامة | بس هي المسموح بيها، وده مش بيعتبر تغيير في الكلام.
"""

SCHEMA = {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
          "required": ["lines"], "additionalProperties": False}


class _Text:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Reply:
    def __init__(self, text):
        self.content, self.stop_reason = [_Text(text)], "end_turn"


# the API keys, and the switches that route the call to Bedrock / Vertex / a proxy: all of them can bill something
# other than the user's subscription (executor ruling: nothing paid, ever silently)
API_BILLING_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                    "ANTHROPIC_BASE_URL")


def _child_env(environ=None, windows=None) -> dict:
    """a copy of the environment for the `claude -p` child WITHOUT the variables that would make the Claude Code CLI bill
    the API instead of the user's subscription (case-insensitive on Windows, where variable names are); the input is not
    modified"""
    environ = os.environ if environ is None else environ
    windows = _platform.is_windows() if windows is None else windows
    drop = {k.upper() for k in API_BILLING_VARS} if windows else set(API_BILLING_VARS)
    return {k: v for k, v in environ.items() if (k.upper() if windows else k) not in drop}


def _is_posix() -> bool:
    return os.name == "posix"


def _spawn_kwargs(posix=None) -> dict:
    """POSIX: the CLI leads its own session / process group, so a cancel can kill the group (what it started too)"""
    posix = _is_posix() if posix is None else posix
    return {"start_new_session": True} if posix else {}


def _kill_group(p, posix=None) -> None:
    posix = _is_posix() if posix is None else posix
    if posix:
        try:
            os.killpg(p.pid, getattr(signal, "SIGKILL", 9))
        except OSError:                          # the group is already gone (ProcessLookupError is an OSError)
            pass


def _kill_cli(p, posix=None) -> None:
    """kill the CLI and what it started: POSIX the process group, Windows the tree (taskkill /T in kill_tree)"""
    _kill_group(p, posix)
    kill_tree(p)


class _CliHandle:
    """what lib/parallel tracks for a running CLI: kill_tree(handle) polls it, and kills it with `.kill()`. On POSIX
    that must also reach the CLI's process group: a grandchild that inherited our pipes would otherwise keep
    communicate() waiting for the whole CLI_TIMEOUT after a cancel. (Windows: kill_tree uses `.pid` for taskkill /T.)"""

    def __init__(self, p):
        self.p = p
        self.pid = p.pid

    def poll(self):
        return self.p.poll()

    def kill(self):
        _kill_group(self.p)
        self.p.kill()


def _run_cli(args, stdin, cwd, timeout=None):
    if _platform.is_batch(args[0]):             # never cmd.exe with the caption JSON on argv (BatBadBut)
        raise _platform.CmdShimRefused(_platform.CMD_REFUSED)
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", cwd=cwd, env=_child_env(), **_spawn_kwargs())
    handle = track(_CliHandle(p))               # a cancelled parallel_map kills it (and, on POSIX, its group) too
    try:
        out, _err = p.communicate(stdin, timeout=CLI_TIMEOUT if timeout is None else timeout)
    except BaseException:                       # timeout, Ctrl+C, anything: the CLI and what it started die with us
        _kill_cli(p)
        try:
            p.communicate(timeout=5)
        except Exception:                       # noqa: BLE001  (reaping only)
            pass
        raise
    finally:
        untrack(handle)
    return p.returncode, out


def find_claude_code(env=None, home=None, windows=None):
    """the Claude Code CLI (uses the user's Claude subscription), or None. WhyNot Cut's discovery rules: $CLAUDE_CLI,
    PATH, the native / npm install paths, the desktop app's bundle; a file that can start (PATHEXT on Windows, the
    execute bit elsewhere); the `.cmd` shim only when nothing better exists."""
    env = dict(os.environ) if env is None else env
    windows = _platform.is_windows() if windows is None else windows
    home = Path.home() if home is None else Path(home)
    # absolute_only: shutil.which() also finds a claude.exe planted in the current folder on Windows (review I1)
    def path_which(name, path=None):             # not shutil.which: it searches the cwd first on Windows (planted files)
        return _platform.find_on_path(name, path, windows, env)

    found = [c for c in _platform.absolute_only(_platform.claude_install_candidates(
        env, home, windows, _platform.in_sandbox(env), which=path_which)) if _platform.runnable(c, env, windows)]
    found.sort(key=_platform.is_batch)           # stable: exe first, .cmd last
    return str(found[0]) if found else None


def _api_errors() -> tuple:
    """the API backend's exception classes, or () when `anthropic` is not installed (the core runtime has none)"""
    try:
        return (importlib.import_module("anthropic").APIError,)
    except ImportError:
        return ()


API_MISSING = ("The API backend needs the `anthropic` package, which the WhyNot Cut runtime does not include. "
               "Use the Claude subscription backend (settings backend = subscription) or install the package.")


AUTH_TIMEOUT = 60       # seconds `claude auth status` may take


class SubscriptionRefused(RuntimeError):
    """the subscription backend must not start `claude -p`; `code` is the stats error, str(e) / `how` the help text"""

    def __init__(self, code: str, how: str):
        super().__init__(how)
        self.code, self.how = code, how


def _run_auth_status(args, cwd):
    """`claude --safe-mode auth status` in `cwd`: the same stripped env and process handling as the -p child, no stdin"""
    return _run_cli(args, "", cwd, timeout=AUTH_TIMEOUT)


# authMethod (the six values of `claude auth status`) -> what to change, English / Arabic
_AUTH_SOURCES = {
    "api_key": ("an API key (billed per use)", "ANTHROPIC_API_KEY or the env block of a Claude settings.json",
                "مفتاح API (بيتحاسب بالاستخدام)", "ANTHROPIC_API_KEY أو env في settings.json بتاع Claude"),
    "api_key_helper": ("an API key from apiKeyHelper (billed per use)", "apiKeyHelper in a Claude settings.json",
                       "مفتاح API من apiKeyHelper (بيتحاسب بالاستخدام)", "apiKeyHelper في settings.json بتاع Claude"),
    "oauth_token": ("an OAuth token (CLAUDE_CODE_OAUTH_TOKEN)", "CLAUDE_CODE_OAUTH_TOKEN",
                    "OAuth token (CLAUDE_CODE_OAUTH_TOKEN)", "CLAUDE_CODE_OAUTH_TOKEN"),
    "third_party": ("a cloud provider or gateway (billed by that provider)",
                    "the cloud provider or gateway setting (CLAUDE_CODE_USE_BEDROCK / VERTEX / ANTHROPIC_BASE_URL, or settings.json)",
                    "مزوّد سحابي أو gateway (بيتحاسب من المزوّد)",
                    "إعداد المزوّد السحابي أو الـ gateway (CLAUDE_CODE_USE_BEDROCK / VERTEX / ANTHROPIC_BASE_URL أو settings.json)"),
}
_METHOD_OK = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")


def _not_active_how(method: str) -> str:
    if method == "none":
        return ("Claude is not logged in. WhyNot Kalam only uses your Claude subscription: run /login in Claude Code, "
                "or turn Kalam correction off.\n"
                "Claude مش مسجّل دخول. WhyNot Kalam بيستخدم اشتراك Claude بس: اعمل /login في Claude Code، "
                "أو اقفل تصحيح Kalam.")
    if method in _AUTH_SOURCES:
        what, source, what_ar, source_ar = _AUTH_SOURCES[method]
        label = "%s [%s]" % (what, method)
        return ("Claude is set to use %s. WhyNot Kalam only uses your Claude subscription: remove %s, "
                "or turn Kalam correction off.\n"
                "Claude متظبط على %s [%s]. WhyNot Kalam بيستخدم اشتراك Claude بس: شيل %s، أو اقفل تصحيح Kalam."
                % (label, source, what_ar, method, source_ar))
    shown = method if _METHOD_OK.match(method or "") else "unknown"
    return ("Claude is set to use an unexpected sign-in method (%s). WhyNot Kalam only uses your Claude subscription "
            "(claude.ai): change Claude Code back to your subscription with /login, or turn Kalam correction off.\n"
            "طريقة تسجيل الدخول في Claude غير متوقعة (%s). WhyNot Kalam بيستخدم اشتراك Claude (claude.ai) بس: "
            "ارجع للاشتراك بـ /login، أو اقفل تصحيح Kalam." % (shown, shown))


_AUTH_UNAVAILABLE = ("WhyNot Kalam could not check how Claude Code signs in (`claude auth status` is missing, failed or did "
                     "not answer), so it will not start Claude: it only uses your Claude subscription and never bills "
                     "anything silently. Update Claude Code, or turn Kalam correction off.\n"
                     "WhyNot Kalam مقدرش يتأكد Claude Code بيسجّل دخول إزاي (`claude auth status` مش موجود أو فشل)، "
                     "فمش هيشغّل Claude: بيستخدم اشتراكك بس ومش بيحاسب حاجة من غير ما تعرف. حدّث Claude Code أو اقفل تصحيح Kalam.")


def check_subscription(exe, auth_runner=None) -> str:
    """Run `claude --safe-mode auth status` once (the same env as the -p child, a neutral temp cwd, no prompt text).
    -> "claude.ai"; raises SubscriptionRefused("subscription_not_active", how) for any other sign-in method and
    SubscriptionRefused("auth_status_unavailable", how) when the answer cannot be trusted. Only `authMethod` and
    `loggedIn` are read: nothing else of the answer is kept, so no email / org / token can leak from here."""
    cmd = _platform.claude_command(exe)         # a .cmd shim is resolved or refused (CmdShimRefused), as for -p
    runner = auth_runner or _run_auth_status
    with tempfile.TemporaryDirectory(prefix="wnc-kalam-cc-") as d:
        try:
            _code, out = runner(cmd + ["--safe-mode", "auth", "status"], d)
            data = json.loads(out)
        except (OSError, ValueError, subprocess.SubprocessError):
            raise SubscriptionRefused("auth_status_unavailable", _AUTH_UNAVAILABLE) from None
    method = data.get("authMethod") if isinstance(data, dict) else None
    if not isinstance(method, str) or not method:
        raise SubscriptionRefused("auth_status_unavailable", _AUTH_UNAVAILABLE)
    if method == "claude.ai" and data.get("loggedIn") is False:
        method = "none"
    if method != "claude.ai":
        raise SubscriptionRefused("subscription_not_active", _not_active_how(method))
    return method


def correction_line(exe, auth_runner=None) -> dict:
    """the doctor's "Kalam correction" line: {ok, line, authMethod | code, how}; nothing else of `auth status`"""
    if not exe:
        return {"ok": False, "code": "claude_code_missing",
                "line": "subscription: Claude Code not found (install it, or turn Kalam correction off)"}
    try:
        check_subscription(exe, auth_runner)
    except SubscriptionRefused as e:
        return {"ok": False, "code": e.code, "how": e.how, "line": e.how}
    except _platform.CmdShimRefused as e:
        return {"ok": False, "code": e.code, "how": str(e), "line": str(e)}
    return {"ok": True, "authMethod": "claude.ai", "line": "subscription (claude.ai) \u2713"}


class ClaudeCodeClient:
    """Same call shape as the API client, but runs `claude -p` on the user's Claude subscription.
    --safe-mode: no plugins, hooks, MCP or CLAUDE.md; --tools "": text only; phrases go in on stdin."""

    def __init__(self, exe: str, runner=None, model: str = "opus", auth_runner=None):
        self.exe, self.runner, self.model = exe, runner or _run_cli, model
        self.auth_runner = auth_runner
        self._auth = None            # the preflight answer for this job: True, or the SubscriptionRefused to raise again
        self.beta = self
        self.messages = self

    def _ensure_subscription(self):
        """once per job (this client lives for one job): refuse unless Claude Code signs in with the subscription"""
        if self._auth is None:
            try:
                check_subscription(self.exe, self.auth_runner)
                self._auth = True
            except SubscriptionRefused as e:
                self._auth = e
        if self._auth is not True:
            raise self._auth

    def create(self, **kw):
        schema = kw["output_config"]["format"]["schema"]
        effort = kw["output_config"].get("effort", "medium")
        cmd = _platform.claude_command(self.exe)    # a .cmd shim is resolved or refused (RuntimeError), never run by cmd.exe
        self._ensure_subscription()
        with tempfile.TemporaryDirectory(prefix="wnc-kalam-cc-") as d:
            sp = os.path.join(d, "system.txt")
            with open(sp, "w", encoding="utf-8") as f:
                f.write(kw["system"])
            args = cmd + ["-p", "--safe-mode", "--tools", "", "--disallowedTools", "mcp__*", "--no-session-persistence",
                    "--model", self.model, "--effort", effort, "--system-prompt-file", sp,
                    "--output-format", "json", "--json-schema", json.dumps(schema), "--max-turns", "3"]
            code, out = self.runner(args, kw["messages"][0]["content"], d)
        try:
            data = json.loads(out)
        except ValueError:
            raise RuntimeError("Claude Code: %s" % (out.strip()[-300:] or "exit %d" % code))
        if data.get("is_error") or code != 0 or "structured_output" not in data:
            raise RuntimeError("Claude Code: %s" % str(data.get("result") or data.get("subtype") or code)[:300])
        return _Reply(json.dumps(data["structured_output"], ensure_ascii=False))


def rules_for(settings: dict, mode: str) -> str:
    """the rules the panel sent for the current mode, else the default for that mode"""
    r = settings.get("rules") or ""
    return r if r.strip() else default_rules(mode)


class _Notice(str):
    """a notice code that also carries its help text (`.how`)"""
    how = None


def notice_how(notice):
    """the help text that goes with a make_client notice, or None"""
    return getattr(notice, "how", None)


def make_client(settings: dict, finder=find_claude_code):
    """correction backend: "subscription" (default, Claude Code CLI) or "api" (key). -> (client or None, notice)
    notices: "claude_code_missing", "cmd_shim_refused" (an npm .cmd shim that cannot be run safely; notice_how(notice)
    is the way out)"""
    if settings.get("backend", "subscription") == "api":
        return None, None
    exe = finder()
    if not exe:
        return None, "claude_code_missing"
    if _platform.is_batch(exe):
        try:
            _platform.claude_command(exe)
        except _platform.CmdShimRefused as e:
            notice = _Notice(e.code)
            notice.how = str(e)
            return None, notice
    return ClaudeCodeClient(exe), None


def _system(rules: str, glossary: dict) -> str:
    s = (rules or DEFAULT_RULES).strip() + "\n" + CONTRACT
    if glossary:
        terms = "\n".join("- %s ← %s" % (k, "، ".join(v)) for k, v in glossary.items())
        s += "\nمصطلحات العميل (الصح ← الأشكال الغلط اللي ممكن تطلع):\n" + terms + "\n"
    return s


def _ask(client, system: str, before: list, lines: list, after: list, effort: str):
    payload = json.dumps({"context_before": before, "lines": lines, "context_after": after}, ensure_ascii=False)
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=16000, system=system,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": payload}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("refusal")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["lines"]


# ---- faithfulness: corrections may fix spelling and turn transliterated terms into English, nothing more ----
def _covered(tokens: list, other: list) -> float:
    if not tokens:
        return 1.0
    joined = other + [a + b for a, b in zip(other, other[1:])]       # "سوفت ايش" may become one word
    hit = sum(1 for t in tokens if t in ("ال", "وال", "بال", "فال", "لل") or any(_close(t, o) for o in joined))
    return hit / float(len(tokens))


def faithful(src: str, out: str) -> bool:
    """True when `out` is a correction of `src`, not a rewrite, translation, summary or addition"""
    if len(out) > 1.6 * len(src) + 12:
        return False
    ts, to = _tokens(src), _tokens(out)
    return _covered(to, ts) >= 0.6 and _covered(ts, to) >= 0.6


def _keep_or_source(src: str, out) -> tuple:
    out = out.strip() if isinstance(out, str) else ""
    plain = " ".join(out.replace("|", " ").split())        # unit markers are not part of the words
    if not plain or (len(src) >= 8 and len(plain) < MIN_KEEP * len(src)) or not faithful(src, plain):
        return src, True
    return out, False


def correct(phrases: list, rules: str, glossary: dict, api_key: str, client=None, effort: str = "medium"):
    stats = {"sent": len(phrases), "changed": 0, "fallback": 0, "error": None, "kept_source": []}
    if client is None:
        if not api_key:
            stats["error"] = "no_api_key"
            stats["kept_source"] = list(range(len(phrases)))
            return list(phrases), stats
        try:
            client = importlib.import_module("anthropic").Anthropic(api_key=api_key, max_retries=3)
        except ImportError:
            stats["error"], stats["how"] = "anthropic_missing", API_MISSING
            stats["kept_source"] = list(range(len(phrases)))
            return list(phrases), stats
    system = _system(rules, glossary)
    out = []
    for i in range(0, len(phrases), BATCH):
        if cancelled():                          # the run was cancelled: no new batch, the rest keeps its source text
            stats["error"] = "cancelled"
            stats["kept_source"].extend(range(i, len(phrases)))
            stats["fallback"] += len(phrases) - i
            out.extend(phrases[i:])
            break
        lines = phrases[i:i + BATCH]
        before, after = phrases[max(0, i - CONTEXT):i], phrases[i + BATCH:i + BATCH + CONTEXT]
        reply = None
        try:
            for attempt in range(2):   # one retry when the count is wrong
                if attempt and cancelled():      # a cancel between the attempts: no second request / process
                    break
                reply = _ask(client, system, before, lines, after, effort)
                if len(reply) == len(lines):
                    break
        except ((RuntimeError, ValueError, StopIteration, KeyError) + _api_errors()) as e:
            if cancelled():                      # a CLI killed by the cancel is not "exit 1"
                stats["error"] = "cancelled"
            elif isinstance(e, (_platform.CmdShimRefused, SubscriptionRefused)):
                stats["error"], stats["how"] = e.code, str(e)
            else:
                stats["error"] = str(e) if isinstance(e, RuntimeError) else type(e).__name__
            reply = None
        if cancelled() and (reply is None or len(reply) != len(lines)):
            stats["error"] = "cancelled"
        if reply is None or len(reply) != len(lines):
            stats["kept_source"].extend(range(i, i + len(lines)))
            out.extend(lines)
            stats["fallback"] += len(lines)
            continue
        for k, (src, r) in enumerate(zip(lines, reply)):
            line, fell_back = _keep_or_source(src, r)
            if fell_back:
                stats["kept_source"].append(i + k)
            stats["fallback"] += fell_back
            stats["changed"] += (not fell_back) and line != src
            out.append(line)
    return out, stats
