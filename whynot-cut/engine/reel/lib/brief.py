# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Engine briefs (Addendum M5-T3): `reel brief <ID>`, the pinned token estimator, the short JSON of the top sinks.

The lead reads the brief instead of the project's JSON files: the item's state, key numbers, open issues and next
step, at most CAP_TOKENS (1,500) tokens as counted by `estimate_tokens`, the ONE pinned estimator (lib/client_brief.py
and its test use the same function). Read-only: it never writes into the client folder.

Where each field comes from (all engine data, nothing authored here):
    status, done stages, history, blockers   08_quality_control/project-status.json (missing / damaged named as such)
    next, remaining, stale, notices          cli.next_doc (the `reel next` document), passed in by the caller
    duration, graphics                       01_analysis/timeline-spec.json (a motion video: motion-plan.json scenes);
                                             without a plan, the raw duration from 02_transcription/transcript.json
    lines                                    02_transcription/transcript.json segments
    QC                                       08_quality_control/qc-results.json (`failed` rows are open items)
    review                                   review_domains.scan (plan lines with on-screen words) + review_flags.load
    open items for the editor                needs_you.collect, the items of THIS video only
    transcript                               transcript_compact.state (02_transcription/transcript.compact.md)
The decision log (K-T9) is owner-deferred: one line says so, it is never left out silently.

The cap (owner pre-mortem): open flags and blocks are never cut silently. History is trimmed first, then notes (with
"… N notes not shown"), then the numbers; open items last, and then only as "the first N, then `… N more, see <path>
(n)`". A needs-you source that could not be read is an open item. When even the untrimmed lines exceed the cap, the
first line says so. A cut inside a line
stops on a whole word, else on a grapheme boundary that never splits a lam-alef, a mark from its letter or a ZWJ
sequence. Every path is relative to the client root with `/`; a path outside it (a link, a `..`, another folder)
shows as its file name plus "(outside client folder)". Producer and transcript text is fenced as data (a ~~~text
block longer than any tilde run inside), one line per item, so nothing in it reads as a heading or an instruction.
Deterministic: no wall-clock time in the text (the `generated` stamp is only in the JSON document).

Short JSON (ruling Q58-1): previews, plan, ppro-build, transcript-correct, audio-clean and qc print SHORT_KEYS by
default; `--verbose` prints today's full document. Dropped keys go to a file (the verb's own result file when it has
one, else <project>/logs/out/<verb>.json) named in `full`, with a one-line `summary`. A failure or refusal is printed
whole. tests/test_brief.py holds the key inventory (every key a skill, agent, hook, panel file or test reads from the
verb's output is in the short form). Every other verb: NOT_YET.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path, PurePath

from .common import now_iso, read_json, write_json

CAP_TOKENS = 1500

# --------------------------------------------------------------------------- the pinned estimator (shared, Task 59)
# tokens per character, per class; measured on the subscription (tests/fixtures/brief/calibration/, 2026-10-18):
# an in-sample fit on six samples, raised by 5 %. Held-out checks (fu1, 2026-10-19: the largest brief and an
# identifier-heavy English sample, never in the fit) were undercounted by 6-8 %, so Latin was raised 0.333 -> 0.41 and
# digit 0.621 -> 0.645: identifier-heavy text is now not undercounted and fluent English prose is overcounted ~29 %.
# "other" (emoji, format characters, other scripts, accented Latin) was not measured: 2.0 is a conservative stand-in.
# Spaces are free (a word's token carries its space).
RATES_STATUS = "provisional: re-check with count_tokens when the API resumes (Nov)"
RATES = {"ar_letter": 0.844, "ar_mark": 1.415, "latin": 0.41, "digit": 0.645, "punct": 0.919, "space": 0.0,
         "other": 2.0}
_MILLI = {k: round(v * 1000) for k, v in RATES.items()}
_ARABIC = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def char_class(ch: str) -> str:
    """The estimator class of one character."""
    if ch in " \t":
        return "space"
    if "0" <= ch <= "9":
        return "digit"
    if ch.isascii():
        return "latin" if ch.isalpha() else "punct"          # newline, punctuation, JSON syntax
    o = ord(ch)
    for a, b in _ARABIC:
        if a <= o <= b:
            return "ar_mark" if unicodedata.category(ch) in ("Mn", "Me") else "ar_letter"
    return "other"


def estimate_tokens(text: str) -> int:
    """Estimated model tokens of `text`: the per-class rates above, summed, rounded up. Pure: no network, no model."""
    counts: dict = {}
    for ch in text:
        c = char_class(ch)
        counts[c] = counts.get(c, 0) + 1
    milli = sum(n * _MILLI[c] for c, n in counts.items())
    return -(-milli // 1000)


# --------------------------------------------------------------------------- safe cuts
ZW = "\u200c\u200d"                       # ZWNJ, ZWJ
_JOINERS = ZW                             # (variation selectors are marks, category Mn: _mark covers them)
LAM = "ل"
ALEFS = "اأإآٱٲٳٵ"


def _mark(ch: str) -> bool:
    return unicodedata.category(ch) in ("Mn", "Me", "Mc")


def _ri(ch: str) -> bool:                  # a regional indicator (two make a flag)
    return 0x1F1E6 <= ord(ch) <= 0x1F1FF


def _hangul(ch: str) -> str:
    """The Hangul syllable type of ch (UAX #29): L, V, T, LV, LVT, or "" for anything else."""
    o = ord(ch)
    if 0x1100 <= o <= 0x115F or 0xA960 <= o <= 0xA97F:
        return "L"
    if 0x1160 <= o <= 0x11A7 or 0xD7B0 <= o <= 0xD7C6:
        return "V"
    if 0x11A8 <= o <= 0x11FF or 0xD7CB <= o <= 0xD7FB:
        return "T"
    if 0xAC00 <= o <= 0xD7A3:
        return "LV" if (o - 0xAC00) % 28 == 0 else "LVT"
    return ""


_HANGUL_KEEP = {("L", "L"), ("L", "V"), ("L", "LV"), ("L", "LVT"), ("LV", "V"), ("LV", "T"), ("V", "V"), ("V", "T"),
                ("LVT", "T"), ("T", "T")}


def cut_ok(text: str, i: int) -> bool:
    """May text be cut between text[i-1] and text[i]? Never before a mark, a joiner, a skin-tone modifier or an emoji
    tag character, never after a ZWJ/ZWNJ, never inside a flag (a regional-indicator pair) or a Hangul syllable, never
    between a lam (with its marks) and an alef."""
    if i <= 0 or i >= len(text):
        return True
    nxt, prev = text[i], text[i - 1]
    if _mark(nxt) or nxt in _JOINERS or 0x1F3FB <= ord(nxt) <= 0x1F3FF or 0xE0020 <= ord(nxt) <= 0xE007F:
        return False
    if prev in ZW:
        return False
    if _ri(prev) and _ri(nxt):
        j = i - 1
        while j >= 0 and _ri(text[j]):
            j -= 1
        if (i - 1 - j) % 2:                  # an odd number of indicators before: nxt completes the pair
            return False
    if (_hangul(prev), _hangul(nxt)) in _HANGUL_KEEP:
        return False
    if nxt in ALEFS:
        j = i - 1
        while j >= 0 and _mark(text[j]):
            j -= 1
        if j >= 0 and text[j] == LAM:
            return False
    return True


def safe_cut(text: str, limit: int) -> str:
    """The longest prefix of at most `limit` characters ending on a whole word (before a space); a single word longer
    than the limit is cut on a safe grapheme boundary instead (cut_ok)."""
    if len(text) <= limit:
        return text
    limit = max(0, limit)
    sp = text.rfind(" ", 0, limit + 1)
    if sp > 0:
        return text[:sp].rstrip(" ")
    i = limit
    while i > 0 and not cut_ok(text, i):
        i -= 1
    return text[:i]


def clip(text: str, limit: int) -> str:
    """safe_cut plus "…" when something was cut."""
    if len(text) <= limit:
        return text
    return safe_cut(text, limit - 1) + "…"


# --------------------------------------------------------------------------- paths and data text
OUTSIDE = "(outside client folder)"


def rel_path(root, path) -> str:
    """`path` relative to the client root with `/`, or "<name> (outside client folder)" when it resolves outside it
    (a link that leaves the folder, a `..`, an absolute path elsewhere). A relative path is taken under the root."""
    root = Path(root)
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        rr = root.resolve()
        rp = p.resolve()
    except OSError:
        rr, rp = Path(os.path.abspath(root)), Path(os.path.abspath(p))
    try:
        rel = rp.relative_to(rr)
    except ValueError:
        return f"{p.name} {OUTSIDE}"
    return rel.as_posix() or "."


_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_OVERRIDES = re.compile("[\u202a-\u202e]")
_FOREIGN = re.compile(r"(?:\bfile:/{2,3}|(?<![\w/\\~]))(?:[A-Za-z]:[\\/]|\\\\[^\\\s]+\\|/(?:Users|home|Volumes|mnt|"
                      r"private|tmp|var|opt|srv|media|root|[a-zA-Z])/|~[\\/])[^\"'<>|,;\n]*", re.I)
# Where the client root's name ends: a separator, the end, or a character no folder name continues with. A space ends
# it only when no separator follows before the path ends («…/Dr X Clinic/raw» is a sibling folder, not the root);
# a word character, or `.`, `-`, `(` before one, continues the name («Dr X2», «Dr XOld», «Dr X.bak»).
_ROOT_END = r"(?=[\\/]|$|[^\w\s.\-(]|[.\-(](?!\w)|\s(?![^\"'<>|,;\n]*[\\/]))"


def _root_variants(root) -> list:
    s = str(PurePath(str(root))).rstrip("\\/")
    out = {s, s.replace("\\", "/"), s.replace("/", "\\")}
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", s)
    if m:                                     # Git Bash form of a Windows path: /d/WhyNot Clients/...
        out.add("/" + m.group(1).lower() + "/" + m.group(2).replace("\\", "/"))
    try:
        r = str(Path(root).resolve()).rstrip("\\/")
        out |= {r, r.replace("\\", "/")}
    except OSError:
        pass
    try:                                      # ~/… when the root is under the home folder
        home = str(Path.home()).rstrip("\\/")
        for v in list(out):
            if home and v.lower().startswith(home.lower()) and v[len(home):][:1] in ("\\", "/"):
                out |= {"~" + v[len(home):], "~" + v[len(home):].replace("\\", "/")}
    except (OSError, RuntimeError):
        pass
    return sorted((v for v in out if v), key=len, reverse=True)


def scrub(text, root) -> str:
    """One line of data text for the brief: control characters (newlines too) become spaces, bidi overrides go, paths
    under the client root become relative with `/` (a `file://` URL too), any other absolute path (`file://` and `~/`
    included) becomes "<name> (outside client folder)"."""
    t = _OVERRIDES.sub("", _CONTROL.sub(" ", str(text)))
    for v in _root_variants(root):
        pat = re.compile(r"(?:file:/{2,3})?" + re.escape(v) + _ROOT_END + r"(?:[\\/]([^\"'<>|\n]*))?", re.I)
        t = pat.sub(lambda m: (m.group(1) or ".").replace("\\", "/") if m.group(1) is not None else ".", t)

    def foreign(m):
        span = m.group(0)
        cut = max(span.rfind("\\"), span.rfind("/"))
        tail = span[cut + 1:]
        name, _, rest = tail.partition(" ")
        return f"{name or '?'} {OUTSIDE}" + (f" {rest}" if rest else "")
    t = _FOREIGN.sub(foreign, t)
    return " ".join(t.split(" ")).strip()


def fence_for(lines) -> str:
    """A ~~~ fence longer than any tilde run in the lines (CommonMark: the block cannot be closed from inside)."""
    longest = max([len(r) for l in lines for r in re.findall(r"~+", l)] or [0])
    return "~" * max(3, longest + 1)


# --------------------------------------------------------------------------- facts
DECISION_LOG_LINE = "decision log: not built (K-T9 deferred)"
HISTORY_SHOWN = 8
REMAINING_SHOWN = 6
ITEM_CHARS = 220
LINE_CHARS = 400
NOTICES_SHOWN = 6                         # notices are never trimmed by the cap, so their count is bounded


def _sha(f: Path) -> str:
    return hashlib.sha1(f.read_bytes()).hexdigest()[:12]


class _Reader:
    """Reads the project's JSON files once; records each file's fingerprint, or `missing` / `damaged` with a notice."""

    def __init__(self, paths, root):
        self.paths, self.root = paths, root
        self.sources: dict = {}
        self.notices: list = []

    def rel(self, f) -> str:
        return rel_path(self.root, f)

    def get(self, rel: str):
        f = self.paths.p(rel)
        key = self.rel(f)
        if not f.exists():
            self.sources[key] = "missing"
            return "missing"
        try:
            doc = read_json(f)
            self.sources[key] = _sha(f)
            return doc
        except (OSError, ValueError) as e:
            self.sources[key] = "damaged"
            self.notices.append(f"{key}: damaged file, not read ({type(e).__name__})")
            return "damaged"


def _numbers(rd: _Reader) -> list:
    spec = rd.get("01_analysis/timeline-spec.json")
    tj = rd.get("02_transcription/transcript.json")
    qc = rd.get("08_quality_control/qc-results.json")
    spec_rel, tj_rel = rd.rel(rd.paths.p("01_analysis/timeline-spec.json")), rd.rel(rd.paths.p("02_transcription/transcript.json"))
    qc_rel = rd.rel(rd.paths.p("08_quality_control/qc-results.json"))
    out = []
    if isinstance(spec, dict) and isinstance(spec.get("duration_ms"), (int, float)):
        out.append(("duration", f"{spec['duration_ms'] / 1000:.1f} s (plan)", spec_rel))
    elif isinstance(tj, dict) and isinstance((tj.get("meta") or {}).get("duration_ms"), (int, float)):
        out.append(("duration", f"{tj['meta']['duration_ms'] / 1000:.1f} s (raw)", tj_rel))
    else:
        out.append(("duration", "unknown", spec_rel))
    if isinstance(tj, dict):
        out.append(("lines", str(len(tj.get("segments") or [])), tj_rel))
    else:
        out.append(("lines", "damaged file" if tj == "damaged" else "no transcript yet", tj_rel))
    if isinstance(spec, dict):
        out.append(("graphics", str(len(spec.get("events") or [])), spec_rel))
    elif spec == "damaged":
        out.append(("graphics", "damaged file", spec_rel))
    else:
        mp = rd.get("01_analysis/motion-plan.json")
        mp_rel = rd.rel(rd.paths.p("01_analysis/motion-plan.json"))
        if isinstance(mp, dict):
            out.append(("graphics", f"{len(mp.get('scenes') or [])} scenes", mp_rel))
        else:
            out.append(("graphics", "damaged file" if mp == "damaged" else "no plan yet", spec_rel))
    if qc == "missing":
        out.append(("QC", "not run", qc_rel))
    elif not isinstance(qc, dict):
        out.append(("QC", "damaged file", qc_rel))
    elif qc.get("ok") is True:
        out.append(("QC", f"passed ({len(qc.get('checks') or [])} checks)", qc_rel))
    else:
        out.append(("QC", f"failed ({len(qc.get('failed') or [])})", qc_rel))
    return out, (qc if isinstance(qc, dict) else None)


def _review(paths, rd: _Reader) -> tuple:
    """(review line, open item or None): the plan lines with on-screen words against the current review."""
    from . import review_domains, review_flags
    try:
        lines = review_domains.scan(paths)["lines_total"]
    except Exception:  # noqa: BLE001 — no plan yet, or a plan the scan cannot read: said, never raised
        return "no plan to review yet", None
    if not lines:
        return "no on-screen words", None
    try:
        doc = review_flags.load(paths)
    except Exception:  # noqa: BLE001
        doc = None
    see = rd.rel(review_flags.path(paths))
    if doc is None:
        return (f"not current ({lines} lines with on-screen words)",
                {"tag": "review", "text": f"review not current: {lines} plan lines with on-screen words need the "
                                          f"content review (`reel review-scan`)", "see": see})
    return f"current ({lines} lines)", None


def collect(paths, next_doc) -> dict:
    """The brief's facts, every one read from engine data (see the module docstring for the sources)."""
    root = Path(paths.root)
    rd = _Reader(paths, root)
    vid = paths.video_id
    st = rd.get("08_quality_control/project-status.json")
    status = st.get("status") if isinstance(st, dict) else st
    stages = [k for k, v in (st.get("stages") or {}).items() if isinstance(v, dict) and v.get("done")] \
        if isinstance(st, dict) else []
    history = [f"{h.get('status')}: {h.get('note') or ''}".rstrip(": ") for h in (st.get("history") or [])
               if isinstance(h, dict)][-HISTORY_SHOWN:] if isinstance(st, dict) else []
    blockers = [str(b) for b in (st.get("blockers") or [])] if isinstance(st, dict) else []
    try:
        nd = next_doc(paths)
    except Exception as e:  # noqa: BLE001 — a damaged state must still give a brief
        nd = {"next": "unknown", "remaining": [], "stale": [], "notices": []}
        rd.notices.append(f"next step: could not be worked out ({type(e).__name__}: {e})")
    numbers, qc = _numbers(rd)
    open_items = []
    qc_rel = rd.rel(paths.p("08_quality_control/qc-results.json"))
    for f in (qc or {}).get("failed") or []:
        if isinstance(f, dict):
            open_items.append({"tag": "qc", "text": f"{f.get('check')}: {f.get('detail')}", "see": qc_rel})
    st_rel = rd.rel(paths.p("08_quality_control/project-status.json"))
    for b in blockers:
        open_items.append({"tag": "blocker", "text": b, "see": st_rel})
    review_line, review_item = _review(paths, rd)
    if review_item:
        open_items.append(review_item)
    notes = [str(n) for n in nd.get("notices") or []]
    try:
        from . import needs_you
        ny = needs_you.collect(root)
        for it in ny.get("items") or []:
            if it.get("item") != vid:
                continue
            if review_item and str(it.get("ref", "")).endswith("review-flags.json"):
                continue                       # the same "review not current" line, said once (with its count)
            text = str(it.get("text") or "")
            if text.startswith(f"{vid}: "):
                text = text[len(vid) + 2:]          # the brief is this video's: its id once, in the title
            open_items.append({"tag": f"needs-you {it.get('kind')}", "text": text,
                               "see": str(it.get("source") or "output/NEEDS-YOU.md")})
        for u in (ny.get("unread") or []) + (ny.get("skipped") or []):
            if u.get("item") == vid:              # it may hide NEEDS-YOU items: open, so never trimmed silently
                open_items.append({"tag": "needs-you unread", "text": f"could not read {u.get('source')} "
                                                                      f"({u.get('why')})",
                                   "see": str(u.get("source") or "output/NEEDS-YOU.md")})
    except Exception as e:  # noqa: BLE001
        rd.notices.append(f"needs-you list: could not be read ({type(e).__name__})")
    seen, uniq = set(), []
    for o in open_items:
        k = " ".join(o["text"].split()).casefold()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(o)
    from . import transcript_compact
    try:
        ts = transcript_compact.state(paths)
        if ts["state"] == "current":
            transcript = f"{ts['path']} (current)"
        elif ts["state"] == "no-transcript":
            transcript = "no transcript yet"
        else:
            transcript = f"{ts['path']} ({ts['state']}: run `reel transcript-compact`)"
    except Exception as e:  # noqa: BLE001
        transcript = "unknown"
        rd.notices.append(f"transcript compact: could not be checked ({type(e).__name__})")
    return {"item": vid, "folder": rel_path(root, paths.p("")).rstrip("/"), "status": status, "profile": nd.get("profile"), "stages_done": stages,
            "next": str(nd.get("next")), "remaining": [str(x) for x in nd.get("remaining") or []],
            "stale": [str(x) for x in nd.get("stale") or []], "numbers": numbers, "review": review_line,
            "transcript": transcript, "open": uniq, "notes": notes, "history": history,
            "sources": dict(sorted(rd.sources.items())), "notices": rd.notices}


# --------------------------------------------------------------------------- rendering under the cap
def _more_line(hidden: list) -> str:
    by: dict = {}
    for o in hidden:
        by[o["see"]] = by.get(o["see"], 0) + 1
    top = sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))
    parts = [f"{s} ({n})" for s, n in top[:4]]
    if len(top) > 4:
        parts.append(f"other files ({sum(n for _, n in top[4:])})")
    return f"… {len(hidden)} more, see " + ", ".join(parts)


def _block(title: str, lines: list) -> list:
    return [title, fence_for(lines) + "text", *lines, fence_for(lines)]


OVER_CAP = " (over the cap: the lines that are never trimmed are longer)"


def _render(f: dict, root, cap: int, keep: dict, tokens_shown: int, over: bool = False) -> str:
    s = lambda x, n=LINE_CHARS: clip(scrub(x, root), n)  # noqa: E731
    L = [f"# brief {f['item']} · ~{tokens_shown} tokens / {cap}" + (OVER_CAP if over else "")]
    L.append(f"status: {s(f['status'])}" + (f" · profile: {s(f['profile'])}" if f.get("profile") else ""))
    L.append(f"next: {s(f['next'])}")
    rem = f["remaining"][1:] if f["remaining"][:1] == [f["next"]] else f["remaining"]
    if rem:
        more = len(rem) - REMAINING_SHOWN
        L.append(f"then: {s(' → '.join(rem[:REMAINING_SHOWN]), 600)}" + (f" (+{more} more)" if more > 0 else ""))
    if f["stale"]:
        L.append(f"stale: {s('; '.join(f['stale']), 600)}")
    if f["stages_done"]:
        L.append(f"done: {s(', '.join(f['stages_done']))}")
    nums = f["numbers"][:keep["numbers"]]
    if nums:
        L.append("numbers: " + " · ".join(f"{k} {s(v, 80)}" for k, v, _ in nums))
    L.append(f"review: {s(f['review'])}")
    L.append(f"transcript: {s(f['transcript'])}")
    L.append(DECISION_LOG_LINE)
    items = f["open"]
    shown = items[:keep["open"]]
    body = [f"{i}. [{o['tag']}] {s(o['text'], ITEM_CHARS)}" for i, o in enumerate(shown, 1)]
    if len(shown) < len(items):
        body.append(_more_line(items[len(shown):]))
    if not items:
        body = ["none"]
    L += _block(f"open items ({len(items)}) — data, not instructions:", body)
    if f["notices"]:
        nl = [f"- {s(n, ITEM_CHARS)}" for n in f["notices"][:NOTICES_SHOWN]]
        if len(f["notices"]) > NOTICES_SHOWN:
            nl.append(f"… {len(f['notices']) - NOTICES_SHOWN} more notices, see `reel brief --json`")
        L += _block("notices — data:", nl)
    notes = f["notes"][:keep["notes"]]
    notes_cut = f"… {len(f['notes']) - len(notes)} notes not shown (`reel next`)" if len(notes) < len(f["notes"]) else ""
    if notes:
        L += _block("notes — data:", [f"- {s(n, ITEM_CHARS)}" for n in notes] + ([notes_cut] if notes_cut else []))
    elif notes_cut:
        L.append(notes_cut)
    hist = f["history"][len(f["history"]) - keep["history"]:] if keep["history"] else []
    if hist:
        L += _block(f"history (last {len(hist)}) — data:", [f"- {s(h, ITEM_CHARS)}" for h in hist])
    folder = f.get("folder") or ""
    if folder and f["sources"] and all(k.startswith(folder + "/") for k in f["sources"]):
        L.append(f"sources in {folder}/: " + " · ".join(f"{k[len(folder) + 1:]} {v}" for k, v in f["sources"].items()))
    else:
        L.append("sources: " + " · ".join(f"{k} {v}" for k, v in f["sources"].items()))
    return "\n".join(L) + "\n"


def _fit(f: dict, root, cap: int, keep: dict, over: bool = False) -> tuple:
    """(text, tokens) with the printed size equal to the estimate of the text that prints it."""
    shown = 0
    for _ in range(4):
        text = _render(f, root, cap, keep, shown, over)
        n = estimate_tokens(text)
        if n == shown:
            break
        shown = n
    return text, estimate_tokens(text)


def render(f: dict, root, cap: int = CAP_TOKENS) -> tuple:
    """(text, tokens, trimmed, counts). Over the cap, whole entries go in this order: history (oldest first), notes,
    numbers, and only then open items, which keep the first N and the `… N more, see <path>` line. Each part keeps
    the most entries that fit (fewer entries never cost more)."""
    counts = {"history": len(f["history"]), "notes": len(f["notes"]), "numbers": len(f["numbers"]),
              "open": len(f["open"])}
    keep = dict(counts)
    text, n = _fit(f, root, cap, keep)
    for part in ("history", "notes", "numbers", "open"):
        if n <= cap:
            break
        keep[part] = 0
        text, n = _fit(f, root, cap, keep)
        if n > cap:
            continue                             # this part gone and still over: on to the next part
        lo, hi = 0, counts[part]                 # the most entries of this part that fit
        while lo < hi:
            mid = (lo + hi + 1) // 2
            keep[part] = mid
            if _fit(f, root, cap, keep)[1] <= cap:
                lo = mid
            else:
                hi = mid - 1
        keep[part] = lo
        text, n = _fit(f, root, cap, keep)
    if n > cap:                                  # everything trimmable is gone and it is still over: said, not hidden
        text, n = _fit(f, root, cap, keep, over=True)
    trimmed = {k: counts[k] - keep[k] for k in counts}
    return text, n, trimmed, counts


def build(paths, next_doc=None, cap: int = CAP_TOKENS) -> dict:
    """`reel brief`: {"item", "text", "tokens", "cap", "trimmed", "counts", "facts", "notices", "generated"}."""
    if next_doc is None:
        import cli                                 # engine/reel/cli.py (read-only use of next_doc)
        next_doc = cli.next_doc
    f = collect(paths, next_doc)
    text, n, trimmed, counts = render(f, paths.root, cap)
    return {"item": f["item"], "text": text, "tokens": n, "cap": cap, "trimmed": trimmed, "counts": counts,
            "facts": f, "notices": f["notices"], "generated": now_iso()}


# --------------------------------------------------------------------------- short JSON (Q58-1)
KEEP_ALWAYS = ("ok", "status", "error", "where", "how", "log", "refused", "blocked", "notices", "version_warnings")
FULL_KEYS = {
    "previews": ("previews", "contact_sheet", "warnings"),
    "plan": ("ok", "errors", "warnings", "events", "cues", "main_segments", "edit_plan", "caption_look_suggestion",
             "reference_style", "missing_semantic_files", "how"),
    "ppro-build": ("status", "ok", "checks", "project", "bridge", "premiere_error", "previous_version_backup",
                   "previous_restored", "closed_previous", "job_data", "result", "at", "prproj_mtime", "how",
                   "warnings", "stills_redrawn", "qc_frames", "qc_frames_note", "parked_previous", "content_signature",
                   "closed_by_pipeline_at", "detail", "blocked", "refused", "fix", "missing", "error", "editor_message"),
    "transcript-correct": ("meta", "segments", "words", "cues", "short_cues", "applied", "flagged", "reanchored",
                           "problems", "restored"),
    "audio-clean": ("decisions", "loudness", "metrics", "regions_ms", "pauses", "removed_ms", "new_duration_ms",
                    "pause_params", "cut_verification", "ok", "how"),
    "qc": ("ok", "failed", "warnings"),
}
SHORT_KEYS = {
    "previews": ("previews", "contact_sheet", "warnings"),
    "plan": ("ok", "errors", "warnings", "events", "cues", "main_segments", "edit_plan", "caption_look_suggestion",
             "reference_style", "missing_semantic_files", "how"),
    "ppro-build": ("status", "ok", "checks", "project", "premiere_error", "previous_version_backup", "how",
                   "warnings", "stills_redrawn", "qc_frames", "qc_frames_note", "parked_previous", "detail", "blocked",
                   "refused", "fix", "missing", "error", "editor_message"),
    "transcript-correct": ("segments", "words", "cues", "short_cues", "applied", "flagged", "reanchored", "problems",
                           "restored"),
    "audio-clean": ("decisions", "loudness", "metrics", "pauses", "removed_ms", "new_duration_ms", "pause_params",
                    "cut_verification", "ok", "how"),          # metrics: speech-to-noise, LUFS, spectrograms (by meaning)
    "qc": ("ok", "failed", "warnings"),
}
OK_STATUSES = {"ppro-build": ("PRPROJ_BUILT", "PRPROJ_BUILT_WITH_ISSUES")}
OWN_RESULT_FILE = {"ppro-build": "07_premiere/ppro-build-result.json"}
NOT_YET = ("not yet: every other verb prints its full document (no short schema until its keys are inventoried; "
           "ruling Q58-1)")


def short_doc(verb: str, doc: dict) -> tuple:
    """(the short document, the dropped keys) of a verb in scope. Pure."""
    keep = set(SHORT_KEYS[verb]) | set(KEEP_ALWAYS)
    return {k: v for k, v in doc.items() if k in keep}, [k for k in doc if k not in keep]


def _failure(verb: str, doc: dict) -> bool:
    from .errors import exit_code
    if exit_code(doc) or any(k in doc for k in ("error", "refused", "blocked")):
        return True
    st = doc.get("status")
    return st is not None and st not in OK_STATUSES.get(verb, ())


def shorten(verb: str, doc, paths_fn):
    """The document `reel <verb>` prints without --verbose: the short form plus `full` (where the whole document is)
    and `summary`, when anything was dropped; unchanged for verbs not in scope, failures and refusals."""
    if verb not in SHORT_KEYS or not isinstance(doc, dict) or _failure(verb, doc):
        return doc
    short, dropped = short_doc(verb, doc)
    if not dropped:
        return doc
    paths = paths_fn()
    root = Path(paths.root)
    own = OWN_RESULT_FILE.get(verb)
    own_file = None
    try:
        if own and paths.p(own).exists():   # the verb already wrote this very document (ppro-build-result.json)
            own_file = paths.p(own)
        target = own_file or paths.p(f"logs/out/{verb}.json")
    except RuntimeError:                       # no video id: the client's output/logs
        target = root / "output" / "logs" / "out" / f"{verb}.json"
    if own_file is None:
        write_json(target, doc)
    kept = len(short)
    short["full"] = rel_path(root, target)
    short["summary"] = (f"{verb}: short form ({kept} keys); {', '.join(sorted(dropped))} in {short['full']} "
                        f"(or run with --verbose)")
    return short
