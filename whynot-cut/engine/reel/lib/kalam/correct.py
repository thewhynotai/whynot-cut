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
#   * cancel / timeout kills the CLI's process tree (lib/parallel.kill_tree).
"""Correct caption phrases with Claude by the user's rules. Timecodes never leave this machine: only text is sent,
and the reply must have exactly one line per phrase or the source text is kept."""
import importlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..parallel import kill_tree, track, untrack
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


def _run_cli(args, stdin, cwd):
    if _platform.is_batch(args[0]):             # never cmd.exe with the caption JSON on argv (BatBadBut)
        raise RuntimeError(_platform.CMD_REFUSED)
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", cwd=cwd)
    track(p)                                    # a cancelled parallel_map kills it too
    try:
        out, _err = p.communicate(stdin, timeout=CLI_TIMEOUT)
    except BaseException:                       # timeout, Ctrl+C, anything: the CLI and what it started die with us
        kill_tree(p)
        try:
            p.communicate(timeout=5)
        except Exception:                       # noqa: BLE001  (reaping only)
            pass
        raise
    finally:
        untrack(p)
    return p.returncode, out


def find_claude_code(env=None, home=None, windows=None):
    """the Claude Code CLI (uses the user's Claude subscription), or None. WhyNot Cut's discovery rules: $CLAUDE_CLI,
    PATH, the native / npm install paths, the desktop app's bundle; a file that can start (PATHEXT on Windows, the
    execute bit elsewhere); the `.cmd` shim only when nothing better exists."""
    env = dict(os.environ) if env is None else env
    windows = _platform.is_windows() if windows is None else windows
    home = Path.home() if home is None else Path(home)
    found = [c for c in _platform.claude_install_candidates(env, home, windows, _platform.in_sandbox(env))
             if _platform.runnable(c, env, windows)]
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


class ClaudeCodeClient:
    """Same call shape as the API client, but runs `claude -p` on the user's Claude subscription.
    --safe-mode: no plugins, hooks, MCP or CLAUDE.md; --tools "": text only; phrases go in on stdin."""

    def __init__(self, exe: str, runner=None, model: str = "opus"):
        self.exe, self.runner, self.model = exe, runner or _run_cli, model
        self.beta = self
        self.messages = self

    def create(self, **kw):
        schema = kw["output_config"]["format"]["schema"]
        effort = kw["output_config"].get("effort", "medium")
        cmd = _platform.claude_command(self.exe)    # a .cmd shim is resolved or refused (RuntimeError), never run by cmd.exe
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


def make_client(settings: dict, finder=find_claude_code):
    """correction backend: "subscription" (default, Claude Code CLI) or "api" (key). -> (client or None, notice)"""
    if settings.get("backend", "subscription") == "api":
        return None, None
    exe = finder()
    return (ClaudeCodeClient(exe), None) if exe else (None, "claude_code_missing")


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
        lines = phrases[i:i + BATCH]
        before, after = phrases[max(0, i - CONTEXT):i], phrases[i + BATCH:i + BATCH + CONTEXT]
        reply = None
        try:
            for _ in range(2):   # one retry when the count is wrong
                reply = _ask(client, system, before, lines, after, effort)
                if len(reply) == len(lines):
                    break
        except ((RuntimeError, ValueError, StopIteration, KeyError) + _api_errors()) as e:
            stats["error"] = str(e) if isinstance(e, RuntimeError) else type(e).__name__
            reply = None
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
