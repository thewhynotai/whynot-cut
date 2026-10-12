import json

import anthropic
import httpx2

from kalam.correct import correct


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resp:
    def __init__(self, lines, stop="end_turn"):
        self.content = [_Block(json.dumps({"lines": lines}, ensure_ascii=False))]
        self.stop_reason = stop


class FakeClient:
    """records requests; replies with a scripted list of line-lists (or exceptions)"""
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.beta = self
        self.messages = self

    def create(self, **kw):
        self.requests.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        if isinstance(r, _Resp):
            return r
        return _Resp(r)


SRC = ["صفتشو انجري انتم عارفين", "ان احنا ما فيش حاجة اسمها فراكشر", "عبارة عن سوفت ايش وانجري"]
FIXED = ["Soft Tissue Injury انتو عارفين", "إن احنا مفيش حاجة اسمها Fracture", "عبارة عن Soft Tissue Injury"]


def test_reply_with_same_count_is_used():
    c = FakeClient(FIXED)
    out, stats = correct(SRC, "rules", {}, "key", client=c)
    assert out == FIXED and stats["changed"] == 3 and stats["fallback"] == 0
    req = c.requests[0]
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req["betas"]
    assert req["output_config"]["format"]["type"] == "json_schema"


def test_wrong_count_is_retried_once_then_source_kept():
    c = FakeClient(FIXED[:2], FIXED[:2])
    out, stats = correct(SRC, "rules", {}, "key", client=c)
    assert out == SRC and len(c.requests) == 2 and stats["fallback"] == 3


def test_wrong_count_then_right_count_uses_retry():
    c = FakeClient(FIXED[:2], FIXED)
    out, _ = correct(SRC, "rules", {}, "key", client=c)
    assert out == FIXED


def test_shortened_line_falls_back_to_source():
    c = FakeClient([FIXED[0], "مفيش", FIXED[2]])
    out, stats = correct(SRC, "rules", {}, "key", client=c)
    assert out == [FIXED[0], SRC[1], FIXED[2]] and stats["fallback"] == 1


def test_connection_error_keeps_all_source():
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    out, stats = correct(SRC, "rules", {}, "key", client=FakeClient(err))
    assert out == SRC and stats["error"]


def test_refusal_keeps_source():
    out, stats = correct(SRC, "rules", {}, "key", client=FakeClient(_Resp(FIXED, stop="refusal")))
    assert out == SRC and stats["error"] == "refusal"


def test_no_key_and_no_client_returns_source():
    out, stats = correct(SRC, "rules", {}, "", client=None)
    assert out == SRC and stats["error"] == "no_api_key"


def test_long_input_is_batched_with_context_and_glossary():
    src = ["كلمة %d هنا" % i for i in range(130)]
    c = FakeClient(*[src[i:i + 60] for i in range(0, 130, 60)])
    out, stats = correct(src, "rules", {"Granudacyn": ["graniodasin"]}, "key", client=c)
    assert out == src and len(c.requests) == 3
    second = c.requests[1]["messages"][0]["content"]
    assert "كلمة 59 هنا" in second            # context from the previous batch
    assert "Granudacyn" in c.requests[0]["system"]


def test_default_rules_follow_the_mode():
    from kalam.correct import default_rules
    assert "الهمزات" in default_rules("ar")
    en = default_rules("en")
    assert "English" in en and "الهمزات" not in en
    assert default_rules("other") == en


# ---- Claude subscription backend (Claude Code CLI) ----
from kalam.correct import ClaudeCodeClient  # noqa: E402


def test_claude_code_client_runs_cli_safely_and_parses_structured_output():
    seen = {}

    def runner(args, stdin, cwd):
        seen.update(args=args, stdin=stdin, cwd=cwd,
                    system=open(args[args.index("--system-prompt-file") + 1], encoding="utf-8").read())
        return 0, json.dumps({"type": "result", "is_error": False, "structured_output": {"lines": FIXED}})

    out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner))
    assert out == FIXED and stats["error"] is None
    a = seen["args"]
    assert a[0] == "/x/claude" and "-p" in a and "--safe-mode" in a and "--no-session-persistence" in a
    assert a[a.index("--tools") + 1] == "" and a[a.index("--output-format") + 1] == "json"
    assert json.loads(a[a.index("--json-schema") + 1])["required"] == ["lines"]
    assert seen["system"].startswith("rules")
    assert json.loads(seen["stdin"])["lines"] == SRC        # the phrases go in on stdin, never on argv


def test_claude_code_client_error_keeps_source():
    def runner(args, stdin, cwd):
        return 1, json.dumps({"type": "result", "is_error": True, "result": "Not logged in"})
    out, stats = correct(SRC, "rules", {}, "", client=ClaudeCodeClient("/x/claude", runner=runner))
    assert out == SRC and "Not logged in" in stats["error"]


def test_make_client_defaults_to_subscription():
    from kalam.correct import make_client
    c, notice = make_client({}, finder=lambda: "/x/claude")
    assert isinstance(c, ClaudeCodeClient) and notice is None
    c, notice = make_client({"backend": "subscription"}, finder=lambda: None)
    assert c is None and notice == "claude_code_missing"
    c, notice = make_client({"backend": "api", "api_key": "k"}, finder=lambda: "/x/claude")
    assert c is None and notice is None


# ---- faithfulness gate: a correction may fix words, never rewrite, translate or add ----
from pathlib import Path  # noqa: E402

from kalam.correct import faithful  # noqa: E402

DEMO = Path(__file__).resolve().parents[3] / "demo"


def _srt_texts(p):
    return [" ".join(b.split("\n")[2:]) for b in p.read_text(encoding="utf-8").strip().split("\n\n")]


def test_every_user_approved_demo_correction_passes():
    raw, fixed = _srt_texts(DEMO / "sherif_raw_model.srt"), _srt_texts(DEMO / "sherif_corrected.srt")
    assert len(raw) == len(fixed) == 28
    bad = [(r, f) for r, f in zip(raw, fixed) if not faithful(r, f)]
    assert not bad, bad


def test_rewrite_translation_and_added_sentence_are_rejected():
    src = "ان احنا ما فيش حاجة اسمها فراكشر"
    assert not faithful(src, "إننا لا يوجد لدينا شيء يسمى الكسر")            # MSA rewrite, same length
    assert not faithful(src, "we do not have anything called a fracture")      # translation
    assert not faithful(src, src + " وده كلام مهم جدا لازم كله يعرفه كويس")    # added sentence
    assert not faithful("ده", "ده كلام مهم جدا جدا جدا")                       # short source, big growth


from kalam.correct import default_rules  # noqa: E402


def test_custom_rules_reach_every_mode():
    from kalam.correct import rules_for
    assert rules_for({"rules": "my english rules"}, "en") == "my english rules"
    assert rules_for({"rules": "قواعدي"}, "ar") == "قواعدي"
    assert rules_for({}, "en") == default_rules("en") and rules_for({"rules": "  "}, "ar") == default_rules("ar")


def test_unit_markers_pass_the_faithfulness_gate_and_fallbacks_are_reported():
    marked = ["Soft Tissue Injury | انتو عارفين |", "إن احنا مفيش حاجة اسمها Fracture", "مفيش"]
    out, stats = correct(SRC, "rules", {}, "key", client=FakeClient(marked))
    assert out[:2] == marked[:2] and out[2] == SRC[2]
    assert stats["kept_source"] == [2]


def test_contract_asks_for_meaning_unit_markers():
    c = FakeClient(FIXED)
    correct(SRC, "rules", {}, "key", client=c)
    assert "|" in c.requests[0]["system"]
