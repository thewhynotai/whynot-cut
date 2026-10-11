"""Podcast mode: the REELS PLAN of an episode (validation, sentence snapping, candidate previews) and Gate 0 (the editor
picks reels; each picked reel becomes an ordinary clip project cut from a window of the episode file).

Input (authored by the episode-analyst): output/episodes/<EP>/01_analysis/reels-plan.json
Outputs: 01_analysis/reels-plan-validated.json, reels-plan.md, reels-plan-validation.json
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .common import fmt_ts, load_config, now_iso, read_json, write_json, write_text

PUNCT_END = re.compile(r"[.?!؟…۔]\s*$")
SCORE_KEYS = ("hook", "standalone", "payoff", "ending")
RID = re.compile(r"^R\d+$")


def recipes() -> dict:
    return load_config("recipes.json").get("types", {})


def content_types() -> list[str]:
    return list(recipes())


def type_label(t: str, lang: str = "ar") -> str:
    lab = recipes().get(t, {}).get("label", {})
    return lab.get(lang) or lab.get("en") or t


# --------------------------------------------------------------------------- snapping
def boundary_words(words: list, gap_ms: int = 300) -> tuple[set, set]:
    """Indices of words that can START a reel (segment start, after a sentence end, after a pause) and that can END
    one (segment end, sentence-final punctuation, before a pause)."""
    n = len(words)
    starts, ends = set(), set()
    for i, w in enumerate(words):
        prev = words[i - 1] if i else None
        nxt = words[i + 1] if i + 1 < n else None
        if prev is None or prev.get("segment_id") != w.get("segment_id") or PUNCT_END.search(prev["word"] or "") \
                or w["start_ms"] - prev["end_ms"] >= gap_ms:
            starts.add(i)
        if nxt is None or nxt.get("segment_id") != w.get("segment_id") or PUNCT_END.search(w["word"] or "") \
                or nxt["start_ms"] - w["end_ms"] >= gap_ms:
            ends.add(i)
    return starts, ends


def _nearest(idx: list, key, t: int) -> int | None:
    return min(idx, key=lambda i: (abs(key(i) - t), i)) if idx else None


def snap_in(words: list, t_ms: int, cfg: dict) -> int:
    """In-point at the nearest sentence-like word start within ±search (else the nearest word), minus a short lead-in
    that never reaches back into the previous word. Never below 0."""
    if not words:
        return max(0, int(t_ms))
    sc = cfg.get("snap", {})
    search, lead = sc.get("search_ms", 1500), sc.get("lead_in_ms", 120)
    starts, _ = boundary_words(words, sc.get("gap_ms", 300))
    near = [i for i in range(len(words)) if abs(words[i]["start_ms"] - t_ms) <= search]
    i = _nearest([k for k in near if k in starts], lambda k: words[k]["start_ms"], t_ms)
    if i is None:
        i = _nearest(near or list(range(len(words))), lambda k: words[k]["start_ms"], t_ms)
    w = words[i]
    floor = words[i - 1]["end_ms"] + 20 if i else 0
    return max(0, min(w["start_ms"], max(w["start_ms"] - lead, floor)))


def snap_out(words: list, t_ms: int, cfg: dict, total_ms: int) -> int:
    """Out-point at the nearest sentence-like word end within ±search (else the nearest word), plus a short tail that
    never reaches into the next word. Never beyond the episode."""
    if not words:
        return min(int(t_ms), total_ms)
    sc = cfg.get("snap", {})
    search, tail = sc.get("search_ms", 1500), sc.get("tail_ms", 250)
    _, ends = boundary_words(words, sc.get("gap_ms", 300))
    near = [i for i in range(len(words)) if abs(words[i]["end_ms"] - t_ms) <= search]
    i = _nearest([k for k in near if k in ends], lambda k: words[k]["end_ms"], t_ms)
    if i is None:
        i = _nearest(near or list(range(len(words))), lambda k: words[k]["end_ms"], t_ms)
    w = words[i]
    ceil = words[i + 1]["start_ms"] - 20 if i + 1 < len(words) else total_ms
    return min(total_ms, max(w["end_ms"], min(w["end_ms"] + tail, ceil)))


def _tokens(words: list) -> list[tuple[str, int]]:
    from .plan import norm
    return [(t, i) for i, w in enumerate(words) for t in norm(w["word"]).split()]


def find_evidence(words: list, text: str, near_ms: int, tol_ms: int, anchor: str = "start") -> bool:
    """True when the words of `text` (Arabic-normalised: hamza forms, ta marbuta, ya, tashkeel, punctuation) occur in a
    row in the transcript, with their first word starting (anchor 'start') or last word ending ('end') within tol_ms."""
    from .plan import norm
    want = norm(text or "").split()
    if not want:
        return False
    toks = _tokens(words)
    seq = [t for t, _ in toks]
    n = len(want)
    for k in range(len(seq) - n + 1):
        if seq[k:k + n] == want:
            t = words[toks[k][1]]["start_ms"] if anchor == "start" else words[toks[k + n - 1][1]]["end_ms"]
            if abs(t - near_ms) <= tol_ms:
                return True
    return False


# --------------------------------------------------------------------------- validation
def validate_topics(topics: list, total_ms: int, min_ms: int = 10000) -> list[str]:
    """Problems with a topic map (also the YouTube chapters): sorted, non-overlapping, >= 10 s each, first at the start."""
    from .plan import to_ms
    probs, prev_end = [], None
    for k, t in enumerate(topics):
        try:
            a, b = to_ms(t["start"]), to_ms(t["end"])
        except Exception:  # noqa: BLE001
            probs.append(f"topic {t.get('id', k + 1)}: start/end missing or unreadable")
            continue
        if k == 0 and a > 5000:
            probs.append(f"topic {t.get('id', 1)} starts at {fmt_ts(a, '.')}: the first topic must start at 00:00")
        if b - a < min_ms:
            probs.append(f"topic {t.get('id', k + 1)} is {(b - a) / 1000:.1f} s (chapters must be >= 10 s)")
        if prev_end is not None and a < prev_end - 40:
            probs.append(f"topic {t.get('id', k + 1)} overlaps or is out of order")
        if b > total_ms + 1000:
            probs.append(f"topic {t.get('id', k + 1)} ends after the episode")
        if not str(t.get("title", "")).strip():
            probs.append(f"topic {t.get('id', k + 1)} has no title")
        prev_end = b
    return probs


def reels_plan_fingerprint(ep) -> str:
    h = hashlib.sha1()
    for rel in ("01_analysis/reels-plan.json", "02_transcription/words.json"):
        f = ep.p(rel)
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()[:16]


def compile_reels_plan(ep) -> dict:
    from .episode import podcast_cfg
    from .plan import norm, to_ms
    plan = read_json(ep.p("01_analysis/reels-plan.json"))
    if not plan:
        raise SystemExit("01_analysis/reels-plan.json missing — the episode-analyst authors it (see episode-craft)")
    wj = read_json(ep.p("02_transcription/words.json"))
    tj = read_json(ep.p("02_transcription/transcript.json"))
    if not wj or not tj:
        raise SystemExit(f"episode transcript missing — run `reel episode-transcribe --episode {ep.episode_id}`")
    words, total = wj["words"], int(tj["meta"]["duration_ms"])
    cfg = podcast_cfg()
    dur_cfg, tol = cfg["reel_duration_s"], cfg["snap"].get("evidence_tol_ms", 3000)
    types = content_types()
    info = read_json(ep.p("00_inputs/episode.json"), {}) or {}
    avoid = [a for a in (info.get("sheet", {}) or {}).get("avoid") or [] if str(a).strip()]
    if isinstance(avoid, str):
        avoid = [avoid]
    people = (read_json(ep.p("01_analysis/speakers.json"), {}) or {}).get("people") or {}
    errors, warnings, out, seen = [], [], [], set()
    for c in plan.get("candidates", []):
        cid = str(c.get("id") or "")
        err0 = len(errors)
        if not RID.match(cid) or cid in seen:
            errors.append(f"candidate id {cid!r} missing, duplicate or not like R01")
        seen.add(cid)
        try:
            s_ms, e_ms = to_ms(c["start"]), to_ms(c["end"])
        except Exception:  # noqa: BLE001
            errors.append(f"{cid}: start/end missing or unreadable")
            continue
        if not (0 <= s_ms < e_ms <= total + 40):
            errors.append(f"{cid}: {fmt_ts(s_ms, '.')}–{fmt_ts(e_ms, '.')} is empty or outside the episode ({fmt_ts(total, '.')})")
            continue
        if c.get("type") not in types:
            errors.append(f"{cid}: type {c.get('type')!r} is not one of {types}")
        if c.get("secondary_type") and c["secondary_type"] not in types:
            errors.append(f"{cid}: secondary_type {c['secondary_type']!r} is not one of {types}")
        for key, at, anchor in (("evidence", s_ms, "start"), ("end_evidence", e_ms, "end")):
            if not str(c.get(key) or "").strip():
                errors.append(f"{cid}: {key} missing (copy the first/last words exactly from the transcript)")
            elif not find_evidence(words, c[key], at, tol, anchor):
                errors.append(f"{cid}: {key} not found verbatim within ±{tol / 1000:.0f} s of {fmt_ts(at, '.')}: {c[key]!r}")
        score = c.get("score") or {}
        bad = [k for k in SCORE_KEYS if not isinstance(score.get(k), int) or not 1 <= score[k] <= 10]
        if bad:
            errors.append(f"{cid}: score needs integers 1-10 for {', '.join(bad)}")
        in_ms, out_ms = snap_in(words, s_ms, cfg), snap_out(words, e_ms, cfg, total)
        if out_ms <= in_ms:
            errors.append(f"{cid}: snapped range is empty ({fmt_ts(in_ms, '.')}–{fmt_ts(out_ms, '.')})")
        d = (out_ms - in_ms) / 1000
        if d < dur_cfg["hard_min"] or d > dur_cfg["hard_max"]:
            errors.append(f"{cid}: duration {d:.1f} s outside {dur_cfg['hard_min']}-{dur_cfg['hard_max']} s")
        elif d < dur_cfg["min"] or d > dur_cfg["max"]:
            warnings.append(f"{cid}: duration {d:.1f} s outside the usual {dur_cfg['min']}-{dur_cfg['max']} s")
        cw = []
        if c.get("needs_context") and not str(c.get("context_line") or "").strip():
            cw.append("needs_context without a context_line (the context_card text)")
        unknown = [s for s in c.get("speakers") or [] if people and s not in people]
        if unknown:
            cw.append(f"speakers {unknown} not in speakers.json people {list(people)}")
        inside = [w for w in words if w["start_ms"] >= in_ms - 50 and w["end_ms"] <= out_ms + 50]
        text = norm(" ".join(w["word"] for w in inside))
        hits = [a for a in avoid if norm(str(a)) and re.search(rf"(^| ){re.escape(norm(str(a)))}( |$)", text)]
        if hits:
            cw.append(f"mentions topics the sheet says to avoid: {hits} (selection needs --confirm-avoid {cid})")
        warnings += [f"{cid}: {x}" for x in cw]
        total_score = round(sum(score.get(k, 0) for k in SCORE_KEYS) / len(SCORE_KEYS), 1) if not bad else 0.0
        out.append(dict(c, in_ms=in_ms, out_ms=out_ms, duration_ms=out_ms - in_ms, total=total_score,
                        type_label=type_label(c.get("type", "")), avoid_hits=hits, warnings=cw,
                        excerpt_start=" ".join(w["word"] for w in inside[:12]),
                        excerpt_end=" ".join(w["word"] for w in inside[-12:]), words=len(inside),
                        ok=len(errors) == err0))
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            ov = min(a["out_ms"], b["out_ms"]) - max(a["in_ms"], b["in_ms"])
            short = min(a["duration_ms"], b["duration_ms"]) or 1
            if ov > cfg.get("max_overlap_ratio", 0.5) * short:
                warnings.append(f"{a['id']} and {b['id']} overlap by {ov / 1000:.1f} s ({ov / short:.0%} of the shorter)")
    hours = total / 3_600_000
    if hours >= 0.25:
        lo, hi = cfg["candidates_per_hour"]["min"] * hours, cfg["candidates_per_hour"]["max"] * hours
        if len(out) < int(lo) or len(out) > int(hi + 0.999):
            warnings.append(f"{len(out)} candidates for a {total / 60000:.0f}-min episode (expected about "
                            f"{int(lo)}-{int(hi + 0.999)})")
    topics = (read_json(ep.p("01_analysis/topics.json"), {}) or {}).get("topics")
    if topics:
        warnings += [f"topics: {p}" for p in validate_topics(topics, total)]
    out.sort(key=lambda c: (-c["total"], c["in_ms"]))
    ok = not errors
    res = {"generated": now_iso(), "episode_id": ep.episode_id, "ok": ok, "errors": errors, "warnings": warnings,
           "duration_ms": total, "fingerprint": reels_plan_fingerprint(ep), "candidates": out}
    write_json(ep.p("01_analysis/reels-plan-validation.json"), {k: res[k] for k in ("generated", "ok", "errors", "warnings")})
    if ok:
        write_json(ep.p("01_analysis/reels-plan-validated.json"), res)
        write_reels_plan_md(ep, res)
    else:
        ep.p("01_analysis/reels-plan-validated.json").unlink(missing_ok=True)
    return res


def write_reels_plan_md(ep, res: dict) -> Path:
    L = [f"# Reels plan — {ep.episode_id} (Gate 0: the editor picks)", "",
         f"Episode {fmt_ts(res['duration_ms'], '.')} · {len(res['candidates'])} candidates · validated {res['generated']}", "",
         "| # | Score | Type | In → Out | Dur | Title | Hook | Flags | Preview |", "|---|---|---|---|---|---|---|---|---|"]
    for c in res["candidates"]:
        flags = []
        if c.get("needs_context"):
            flags.append("needs context")
        if c.get("avoid_hits"):
            flags.append("AVOID: " + ", ".join(c["avoid_hits"]))
        if c.get("risks"):
            flags.append("risks: " + "; ".join(map(str, c["risks"]))[:60])
        prev = ep.p(f"03_candidates/{c['id']}.mp4")
        L.append(f"| {c['id']} | {c['total']} | {c.get('type')} ({c.get('type_label')}) | {fmt_ts(c['in_ms'], '.')} → "
                 f"{fmt_ts(c['out_ms'], '.')} | {c['duration_ms'] / 1000:.0f} s | {str(c.get('title', ''))[:50]} | "
                 f"{str(c.get('hook_text') or c.get('hook_quote') or '')[:60]} | {'; '.join(flags) or '—'} | "
                 f"{prev.name if prev.exists() else '—'} |")
    L += ["", "## Details", ""]
    for c in res["candidates"]:
        sc = c.get("score") or {}
        L += [f"### {c['id']} · {c.get('title', '')}",
              f"- Type: {c.get('type')} ({c.get('type_label')})" + (f", also {c['secondary_type']}" if c.get("secondary_type") else ""),
              f"- Score {c['total']}: hook {sc.get('hook')}, standalone {sc.get('standalone')}, payoff {sc.get('payoff')}, "
              f"ending {sc.get('ending')}",
              f"- Why: {c.get('why', '')}",
              f"- Opens with: «{c.get('excerpt_start', '')}»",
              f"- Ends with: «{c.get('excerpt_end', '')}»"]
        if c.get("needs_context"):
            L.append(f"- Context card: {c.get('context_line') or '(missing)'}")
        L += [f"- Note: {w}" for w in c.get("warnings", [])] + [""]
    if res["warnings"]:
        L += ["## Warnings", ""] + [f"- {w}" for w in res["warnings"]] + [""]
    L += ["**To choose:** tell the lead which reels to make (e.g. \"R01, R03; R03 start at 12:04\"). Nothing is cut "
          "until you pick (`reel reels-select --by editor`)."]
    return write_text(ep.p("01_analysis/reels-plan.md"), "\n".join(L) + "\n")
