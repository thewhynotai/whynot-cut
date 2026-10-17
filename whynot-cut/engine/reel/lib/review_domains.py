# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Review domains (3.0 Phase 4 Task 50 = Addendum M1-T1): medical, religious, business and ai, as data.

The registry (config/review-domains/registry.json) lists the domains. A domain is one entry there plus its checker
guidance (skills/medical-accuracy/references/<reference>), its trigger lexicon (config/review-domains/<lexicon>) and its
eval cases (evals/review-<id>-<name>/case.yaml, flat like every eval case, `name:` = the folder): a new one needs no
engine change (`structure_problems()` names what an entry lacks). Data never weakens an existing guard: medical and ai
must stay in the registry, always on, and medical keeps `needs-doctor-approval` (ALWAYS_ON is also a floor in code).

Two sets, kept apart so the review key stays stable:
- the CLIENT SET = the profile's `review_domains` ∪ the legacy `domain` (medical/religious) ∪ the always-on domains
  (medical, ai). It changes only when the profile changes; `review_domain_key()` makes the canonical key T4.13 stores as
  review-flags.json's `domain` (M1-T2): ids lower-cased, trimmed, de-duplicated, checked against the registry, sorted by
  code point and joined with `+`. A profile with no `review_domains` keeps today's checks: general/medical → ai+medical,
  religious → ai+medical+religious. When both are present the legacy domain is kept too (adding `business` never drops
  a religious client's religious review; dropping religious means changing `domain`, which also relabels the glossary);
- DETECTED domains, per plan line: the lexicons run over the line's on-screen text and the transcript evidence the plan
  cites for it (`evidence`), plus the asset manifest's `ai_generated: true` for the files the line shows. A detected
  domain outside the client set becomes a REQUIRED flag for that line only, and only under `review_detect: review` (the
  default); `suggest` lists it, `off` turns detection off. Detection is a floor, never a ceiling: the reviewer may flag any
  line for any registry domain, and still reads every line (a hint is a pointer, never a filter). Events that show an
  AI-generated file are listed in `ai_assets` too when they have no on-screen words (no review line can name them).

Matching is deterministic. Both sides are normalised the same way: NFKC (presentation forms such as lam-alef, ﷺ),
no diacritics, tatweel or bidi controls, a zero-width space as a space, Arabic and Latin letters split apart («الـAI»),
one alef, ى→ي, ة→ه, Arabic-Indic digits as 0-9, ٪ as %. An Arabic term word also matches after a joined prefix
(و ف ب ل ك ال, the Egyptian بـ/هـ verb prefixes). A lexicon's `zones` (a verse between ﴿ ﴾, a quotation after «قال
تعالى») count for that lexicon's domain, and no other domain's words inside a CLOSED zone are reported, on screen or in
the speech's recitation of it (RECITED words in a row); an unclosed zone hides nothing. Known limit: a quotation after
a citation is taken as scripture, so a claim falsely put in the Prophet's mouth reaches the religious reviewer, not the
business one; only paired quotes («» “”) count, a straight " (its own closer, so never provably closed) hides nothing;
a nested quotation is hidden only up to the inner citation, and a gap outside the lexicon's connector words («في سورة
البقرة») is no quotation (both show more, never less). `reel review-scan` prints `scan()`; nothing here writes.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath

from .common import PLUGIN_DIR, Paths, load_config, read_json
from .errors import Guidance

REGISTRY_DIR = PLUGIN_DIR / "config" / "review-domains"
REFERENCES_DIR = PLUGIN_DIR / "skills" / "medical-accuracy" / "references"
EVALS_DIR = PLUGIN_DIR / "evals"                     # a domain's cases: evals/review-<id>-<name>/case.yaml
REGISTRY = "registry.json"
SCHEMA = 1
MODES = ("review", "suggest", "off")
ALWAYS_ON = ("ai", "medical")          # a floor, whatever the registry says: existing guards are never weakened by data
RECITED = 3                            # speech words in a row that repeat an on-screen verse count as its recitation
_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}")
NOTE = ("Hints point the reviewer at lines and domains; the reviewer still reads every line and may flag any line for "
        "any domain.")

# ---------------------------------------------------------------------------------------------- normalising
_DROP = re.compile("[\u0610-\u061a\u061c\u064b-\u065f\u0670\u06d6-\u06ed\u0640\u00ad\u200b-\u200f\u202a-\u202e"
                   "\u2066-\u2069\ufeff]")
_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ک": "ك", "ی": "ي", "٪": "%",
                      "٫": ".", "٬": ",", **{chr(0x660 + i): str(i) for i in range(10)},
                      **{chr(0x6f0 + i): str(i) for i in range(10)}})
_PREFIXES = ("و", "ف", "ب", "ل", "ك", "ا", "ي", "ت", "ن", "ه", "ال", "وال", "فال", "بال", "كال", "لل", "ولل", "وب", "ول",
             "فب", "فل", "هي", "هت", "هن", "بي", "بت", "بن", "وهي", "وهت", "وهن", "وبي", "وبت", "وبن")
_WORD = re.compile(r"\w+")
_GAPS = re.compile("[" + chr(0x200b) + chr(0x2060) + "]")        # zero-width space, word joiner: a word gap
_SCRIPTS = re.compile(r"(?<=[ء-ي])(?=[A-Za-z])|(?<=[A-Za-z])(?=[ء-ي])")    # «الـAI» → «ال AI»


def normalize(text: str) -> str:
    """The matching form of a text (lexicon terms and plan words alike); Latin case is kept (case rules need it)."""
    s = _GAPS.sub(" ", unicodedata.normalize("NFKC", str(text)))
    return _SCRIPTS.sub(" ", _DROP.sub("", s).translate(_MAP))


def _arabic(word: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in word)


def _candidates(token: str) -> set:
    """An Arabic token and what is left after one joined prefix (at least two letters)."""
    return {token} | {token[len(p):] for p in _PREFIXES if token.startswith(p) and len(token) - len(p) >= 2}


# ---------------------------------------------------------------------------------------------- registry
def _bad_registry(problem: str):
    return Guidance(f"the review-domain registry is not usable: {problem}",
                    "Fix config/review-domains/registry.json (schema 1: each domain has label, reference, lexicon, "
                    "approver, verdicts with ok, always_on), or reinstall the plugin",
                    where=str(REGISTRY_DIR / REGISTRY))


def _bilingual(v) -> bool:
    return isinstance(v, dict) and all(isinstance(v.get(k), str) and v[k].strip() for k in ("ar", "en"))


def registry() -> dict:
    """id -> entry, validated; read now (a registry edit needs no restart)."""
    doc = read_json(REGISTRY_DIR / REGISTRY)
    if not isinstance(doc, dict):
        raise _bad_registry("the file is missing or is not a JSON object")
    if doc.get("schema") != SCHEMA:
        raise _bad_registry(f"schema {doc.get('schema')!r} (this engine reads schema {SCHEMA})")
    doms = doc.get("domains")
    if not isinstance(doms, dict) or not doms:
        raise _bad_registry("`domains` is empty or not an object")
    for did, e in doms.items():
        if not isinstance(did, str) or not _ID.fullmatch(did):
            raise _bad_registry(f"domain id {did!r} must be lower-case letters, digits, - or _ (no +)")
        bad = []
        if not isinstance(e, dict):
            raise _bad_registry(f"{did} is not an object")
        for k in ("label", "approver"):
            if not _bilingual(e.get(k)):
                bad.append(f"`{k}` needs Arabic and English text")
        for k in ("reference", "lexicon"):
            v = e.get(k)
            if not isinstance(v, str) or not v.strip() or any(".." in P(v).parts or P(v).anchor
                                                               for P in (PureWindowsPath, PurePosixPath)):
                bad.append(f"`{k}` must be a relative file name")
        v = e.get("verdicts")
        if not (isinstance(v, list) and v and all(isinstance(x, str) and x for x in v) and len(set(v)) == len(v)
                and "ok" in v):
            bad.append("`verdicts` must be distinct names including ok")
        elif did == "medical" and "needs-doctor-approval" not in v:
            bad.append("medical keeps the verdict needs-doctor-approval (an existing guard)")
        if not isinstance(e.get("always_on"), bool):
            bad.append("`always_on` must be true or false")
        elif did in ALWAYS_ON and not e["always_on"]:
            bad.append(f"{did} review stays on for every client (an existing guard)")
        if bad:
            raise _bad_registry(f"{did}: " + "; ".join(bad))
    missing = [d for d in ALWAYS_ON if d not in doms]
    if missing:
        raise _bad_registry(f"{' and '.join(missing)} must stay in the registry (always-on review)")
    return doms


def lexicon(domain: str) -> dict:
    """A domain's trigger lexicon, validated (rules: terms or a pattern; optional supporting rules and zones)."""
    entry = registry().get(domain)
    if entry is None:
        raise Guidance(f"{domain!r} is not a review domain", f"Use one of: {', '.join(sorted(registry()))}")
    f = REGISTRY_DIR / entry["lexicon"]
    doc = read_json(f)
    where = str(f)
    how = "Fix the lexicon file (schema 1: rules with an id and terms or a pattern), or reinstall the plugin"
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise Guidance(f"the {domain} trigger lexicon is missing or not schema {SCHEMA}", how, where=where)
    for part in ("rules", "supporting"):
        rules = doc.get(part, [])
        if not isinstance(rules, list) or (part == "rules" and not rules):
            raise Guidance(f"the {domain} lexicon's `{part}` is not a list of rules", how, where=where)
        for r in rules:
            ok = isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"]
            if ok and "pattern" in r:
                try:
                    re.compile(r["pattern"])
                except (re.error, TypeError):
                    ok = False
            elif ok:
                ok = isinstance(r.get("terms"), list) and all(isinstance(t, str) and _WORD.search(t)
                                                              for t in r["terms"])
            if not ok:
                raise Guidance(f"the {domain} lexicon has a bad rule: {str(r)[:120]}", how, where=where)
    for z in doc.get("zones", []):
        if not (isinstance(z, dict) and isinstance(z.get("id"), str) and
                ((isinstance(z.get("open"), str) and isinstance(z.get("close"), str) and z["open"] and z["close"]) or
                 (isinstance(z.get("after"), list) and isinstance(z.get("quotes"), list) and
                  all(isinstance(q, str) and len(q) == 2 for q in z["quotes"])))):
            raise Guidance(f"the {domain} lexicon has a bad zone: {str(z)[:120]}", how, where=where)
    return doc


def structure_problems() -> list:
    """What each registry entry lacks: its checker guidance, its lexicon or an eval case (`[]` = complete)."""
    out = []
    for did, e in sorted(registry().items()):
        ref = REFERENCES_DIR / e["reference"]
        if not ref.is_file():
            out.append({"domain": did, "missing": "reference", "path": ref.as_posix()})
        try:
            lexicon(did)
        except (Guidance, ValueError):
            out.append({"domain": did, "missing": "lexicon", "path": (REGISTRY_DIR / e["lexicon"]).as_posix()})
        if not any(_eval_case(p) for p in sorted(EVALS_DIR.glob(f"review-{did}-*/case.yaml"))):
            out.append({"domain": did, "missing": "eval",
                        "path": (EVALS_DIR / f"review-{did}-*" / "case.yaml").as_posix()})
    return out


def _eval_case(f: Path) -> bool:
    """A case file the eval runner reads: flat under evals/ (tests/test_evals.py) and named after its folder."""
    try:
        text = f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return re.search(rf"(?m)^name:\s*['\"]?{re.escape(f.parent.name)}['\"]?\s*$", text) is not None


# ---------------------------------------------------------------------------------------------- client set and key
def _canon(ids, reg: dict, where: str) -> list:
    if isinstance(ids, (str, bytes)) or not isinstance(ids, (list, tuple, set, frozenset)):
        raise Guidance(f"{where} must be a list of review domains, got {ids!r}",
                       f"Use a list such as [\"business\"]; the domains are: {', '.join(sorted(reg))}")
    out = set()
    for x in ids:
        d = x.strip().lower() if isinstance(x, str) else None
        if not d or d not in reg:
            raise Guidance(f"{where} names {x!r}, which is not a review domain",
                           f"Use only: {', '.join(sorted(reg))} (a new domain is added to the registry first)")
        out.add(d)
    return sorted(out)


def review_domain_key(ids) -> str:
    """The canonical key of a client set: `ai+business+medical` (M1-T2). Unknown ids are refused, never mapped."""
    got = _canon(ids, registry(), "the review-domain list")
    if not got:
        raise Guidance("the review-domain list is empty", "Pass the client set (it always holds the always-on domains)")
    return "+".join(got)


def _profile(profile) -> dict:
    p = load_config("profile.json") if profile is None else profile
    return p if isinstance(p, dict) else {}


def client_set(profile: dict | None = None) -> tuple:
    """The profile's domains ∪ the legacy `domain` ∪ the always-on ones, sorted. Refuses an unknown id, naming it."""
    reg = registry()
    p = _profile(profile)
    ids: list = []
    if p.get("review_domains") is not None:
        ids += _canon(p["review_domains"], reg, "profile.json `review_domains`")
    legacy = p.get("domain")
    if isinstance(legacy, str) and legacy.strip().lower() in reg:
        ids.append(legacy.strip().lower())
    ids += [d for d, e in reg.items() if e["always_on"]] + list(ALWAYS_ON)
    return tuple(sorted(set(ids)))


def detect_mode(profile: dict | None = None) -> str:
    """profile.json `review_detect`: review (default) | suggest | off."""
    v = _profile(profile).get("review_detect")
    if v is None:
        return "review"
    m = v.strip().lower() if isinstance(v, str) else None
    if m not in MODES:
        raise Guidance(f"profile.json `review_detect` is {v!r}", "Use review (the default), suggest or off")
    return m


# ---------------------------------------------------------------------------------------------- matching
def _term_words(term: str, case: bool) -> list:
    out = []
    for w in re.findall(r"\w+\*?", normalize(term)):
        stem = w.endswith("*")
        w = w.rstrip("*")
        ar = _arabic(w)
        out.append((w if (case or ar) else w.casefold(), stem, ar))
    return out


def _compile_rules(rules: list) -> list:
    out = []
    for r in rules:
        if "pattern" in r:
            out.append((r["id"], re.compile(r["pattern"], re.IGNORECASE if "i" in str(r.get("flags", "")) else 0),
                        None, False))
        else:
            case = bool(r.get("case"))
            out.append((r["id"], None, [_term_words(t, case) for t in r["terms"]], case))
    return out


def _zone_finder(zones: list):
    """norm -> [(start, end, zone id, closed)]. A zone left open (no closing bracket or quote) still counts for its
    domain, but hides nothing: an unclosed ﴿ must never swallow a price after it."""
    brackets, quoted = [], []
    for z in zones:
        if "after" in z:
            phrases = "|".join(re.escape(normalize(a)) for a in z["after"])
            opens = "".join(re.escape(q[0]) for q in z["quotes"])
            between = "|".join(re.escape(normalize(b)) for b in sorted(z.get("between", []), key=len, reverse=True))
            gap = rf"(?:\s+(?:{between})){{0,2}}" if between else ""
            quoted.append((z["id"], re.compile(rf"(?:{phrases}){gap}\s*[:،,]?\s*([{opens}])"),
                           {q[0]: q[1] for q in z["quotes"]}))
        else:
            brackets.append((z["id"], normalize(z["open"]), normalize(z["close"])))

    def find(norm: str) -> list:
        spans = []
        for zid, opener, closer in brackets:
            i = norm.find(opener)
            while i >= 0:
                j = norm.find(closer, i + len(opener))
                k = norm.find(opener, i + len(opener))
                if j < 0 or 0 <= k < j:          # never closed, or opened again first: this one is left open
                    spans.append((i, len(norm) if j < 0 else k, zid, False))
                    i = k
                    continue
                spans.append((i, j + len(closer), zid, True))
                i = norm.find(opener, j + len(closer))
        for zid, pat, closers in quoted:
            starts = [m for m in pat.finditer(norm)]
            for n, m in enumerate(starts):
                q = m.start(1)
                j = norm.find(closers[m.group(1)], q + 1)
                k = norm.find(m.group(1), q + 1)
                nxt = starts[n + 1].start() if n + 1 < len(starts) else -1
                stop = min(x for x in (k, nxt, len(norm)) if x >= 0)
                spans.append((q, j + 1, zid, True) if 0 <= j < stop else (q, stop, zid, False))
        return spans
    return find


def matchers() -> list:
    """Every registry domain's compiled lexicon: (domain, rules, supporting, zone finder). Built once per scan."""
    out = []
    for did in sorted(registry()):
        lex = lexicon(did)
        out.append((did, _compile_rules(lex["rules"]), _compile_rules(lex.get("supporting", [])),
                    _zone_finder(lex.get("zones", []))))
    return out


def _word_ok(tok: str, word: str, stem: bool, ar: bool, case: bool) -> bool:
    if ar:
        return any(c == word or (stem and c.startswith(word)) for c in _candidates(tok))
    t = tok if case else tok.casefold()
    return t == word or (stem and t.startswith(word))


def _rule_hits(norm: str, tokens: list, rules: list) -> list:
    hits = []
    for rid, pat, terms, case in rules:
        if pat is not None:
            hits += [(m.start(), m.end(), rid) for m in pat.finditer(norm) if m.group(0).strip()]
            continue
        for words in terms:
            n = len(words)
            for i in range(len(tokens) - n + 1):
                if all(_word_ok(tokens[i + k][0], *words[k], case) for k in range(n)):
                    hits.append((tokens[i][1], tokens[i + n - 1][2], rid))
    return hits


def _recited(tokens: list, words: dict) -> list:
    """[(start, end, owner)]: runs of speech words that repeat an on-screen zone's words (a recited verse): at least
    RECITED words in a row, or the whole evidence."""
    out = []
    for owner, ws in sorted(words.items()):
        run: list = []
        for t in tokens + [None]:
            if t is not None and t[0] in ws:
                run.append(t)
                continue
            if run and (len(run) >= RECITED or len(run) == len(tokens)):
                out.append((run[0][1], run[-1][2], owner))
            run = []
    return out


def _detect(text: str, ms: list, recited_words: dict | None = None):
    """{domain: [(start, end, rule, words)]} and the closed-zone words per owning domain. `recited_words` (owner ->
    words, from the screen's zones) hides another domain's hit inside the speech's recitation of that zone."""
    norm = normalize(text)
    tokens = [(m.group(0), m.start(), m.end()) for m in _WORD.finditer(norm)]
    zones, zone_words = [], {}
    for did, _r, _s, find in ms:
        for a, b, zid, closed in find(norm):
            zones.append((a, b, did, zid, closed))
            if closed:
                zone_words.setdefault(did, set()).update(_WORD.findall(norm[a:b]))
    hide = [(a, b, owner) for a, b, owner, _z, closed in zones if closed] + _recited(tokens, recited_words or {})
    out: dict = {}
    for did, rules, supporting, _f in ms:
        def keep(h):
            return not any(za <= h[0] and h[1] <= zb for za, zb, owner in hide if owner != did)
        hits = [h for h in _rule_hits(norm, tokens, rules) if keep(h)]
        hits += [(a, b, zid) for a, b, owner, zid, _c in zones if owner == did]
        if hits:
            hits += [h for h in _rule_hits(norm, tokens, supporting) if keep(h)]
            seen, rows = set(), []
            for a, b, rid in sorted(hits, key=lambda h: (h[0], h[1], h[2])):
                words = norm[a:b].strip()
                if (rid, words) not in seen:
                    seen.add((rid, words))
                    rows.append((a, b, rid, words))
            out[did] = rows
    return out, zone_words


def detect(text: str, ms: list | None = None) -> dict:
    """{domain: [{"rule", "match"}]} for one text, in text order (match = the normalised words that hit)."""
    found, _z = _detect(text, ms if ms is not None else matchers())
    return {d: [{"rule": r, "match": w} for _a, _b, r, w in rows] for d, rows in sorted(found.items())}


# ---------------------------------------------------------------------------------------------- the plan
def _plan_events(paths: Paths, kind: str) -> dict:
    """event id -> the compiled event (a clip) or scene (a motion video), for its evidence and the files it shows."""
    from .review_flags import MOTION_PLAN, TIMELINE_SPEC
    from .stamps import read_compiled
    doc = read_compiled(paths.p(TIMELINE_SPEC if kind == "timeline" else MOTION_PLAN)) or {}
    out: dict = {}
    for e in doc.get("events" if kind == "timeline" else "scenes") or []:
        eid = (e.get("event_id") if kind == "timeline" else e.get("id")) if isinstance(e, dict) else None
        if isinstance(eid, str) and eid and eid not in out:
            out[eid] = e
    return out


def _shown_files(e: dict) -> list:
    """The files one event shows: a graphic's image or B-roll video, a motion scene's image elements."""
    params = e.get("params") if isinstance(e.get("params"), dict) else {}
    files = [params[k] for k in ("image", "video") if isinstance(params.get(k), str)]
    files += [el["path"] for el in e.get("elements") or []
              if isinstance(el, dict) and el.get("kind") == "image" and isinstance(el.get("path"), str)]
    return files


def _real(p: Path) -> str:
    r = str(Path(p).resolve())
    return r.casefold() if sys.platform == "win32" else r


def _ai_files(paths: Paths, events: dict) -> dict:
    """event id -> the files it shows that the asset manifest marks `ai_generated: true` (M4), in plan order. A file
    matches by its client-relative path, or by the real path of the asset or of its display copy."""
    man = read_json(paths.client_db / "asset-manifest.json", {}) or {}
    gen: set = set()
    for a in man.get("assets") or []:
        if isinstance(a, dict) and isinstance(a.get("rel"), str) and a.get("ai_generated") is True:
            gen.add(a["rel"])
            gen.update(_real(paths.root / f) for f in (a["rel"], a.get("display_derivative")) if isinstance(f, str) and f)
    out: dict = {}
    for eid, e in events.items():
        files = [f for f in _shown_files(e) if f in gen or _real(paths.root / f) in gen]
        if files:
            out[eid] = list(dict.fromkeys(files))
    return out


def line_requirements(paths: Paths, kind: str, index: dict, cs: tuple | None = None, mode: str | None = None):
    """(lines, ai_assets) for a plan the caller already read (review-flags passes its own `_current` result, so the
    check and the write see one plan). Each line: event_id, text, evidence, start_s, end_s, detected, extra, required,
    suggested. `ai_assets` lists every event that shows an AI-generated file, with or without on-screen words (`line`
    false: no review-flags row can name it today; the disclosure check covers it, M1-T2/M1-T4)."""
    cs = client_set() if cs is None else cs
    mode = detect_mode() if mode is None else mode
    events = _plan_events(paths, kind)
    ai_files = _ai_files(paths, events)
    ms = matchers() if mode != "off" else []
    lines = []
    for eid, line in index.items():
        if not line["text"]:
            continue
        ev = events.get(eid, {}).get("evidence")
        ev = ev if isinstance(ev, str) and ev.strip() else None
        detected: dict = {}
        if mode != "off":
            screen, zone_words = _detect(line["text"], ms)
            speech = _detect(ev, ms, zone_words)[0] if ev else {}
            for src, found in (("screen", screen), ("speech", speech)):
                for d, rows in found.items():
                    detected.setdefault(d, []).extend({"rule": r, "match": w, "in": src} for _a, _b, r, w in rows)
            for f in ai_files.get(eid, []):
                detected.setdefault("ai", []).append({"rule": "ai-generated-asset", "match": f, "in": "asset"})
        detected = {d: detected[d] for d in sorted(detected)}
        extra = sorted(set(detected) - set(cs))
        lines.append({"event_id": eid, "text": line["text"], "evidence": ev, "start_s": line["start_s"],
                      "end_s": line["end_s"], "detected": detected, "extra": extra,
                      "required": sorted(set(cs) | set(extra if mode == "review" else [])),
                      "suggested": extra if mode == "suggest" else []})
    texts = {x["event_id"] for x in lines}
    assets = [{"event_id": eid, "file": f, "line": eid in texts} for eid, fs in ai_files.items() for f in fs]
    return lines, assets


def scan(paths: Paths) -> dict:
    """`reel review-scan`: per plan line with on-screen text, the domains whose triggers hit and why, and the flags the
    reviewer must cover on it; plus every AI-generated file the plan shows. Deterministic and read-only."""
    from .review_flags import _current
    cs = client_set()
    key = review_domain_key(cs)
    mode = detect_mode()
    try:
        kind, index, fp = _current(paths)
    except Guidance as g:                 # the same refusals as review-flags, with this command's next step
        raise Guidance(g.error, g.how.replace("send the review again", "run `reel review-scan` again"),
                       g.where) from None
    lines, assets = line_requirements(paths, kind, index, cs, mode)
    return {"schema": SCHEMA, "plan_kind": kind, "plan_fingerprint": fp, "key": key, "client_set": list(cs),
            "review_detect": mode, "lines_total": len(lines), "lines": lines, "ai_assets": assets, "note": NOTE}


def required_flags(paths: Paths) -> dict:
    """event id -> the flags a review must cover on that line (the client set + its detected required domains)."""
    return {x["event_id"]: x["required"] for x in scan(paths)["lines"]}


def review_domains_detected(paths: Paths) -> dict:
    """event id -> the domains detected in that line (whatever the client set), for the reviewer's hints."""
    return {x["event_id"]: sorted(x["detected"]) for x in scan(paths)["lines"]}
