# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""One checklist per client of what only the editor can do (3.0 T4.7): `reel needs-you [--write]`.

The list is READ from the client's state and never stored anywhere else, so it is regenerated, idempotent and
byte-identical while nothing changed (no timestamps). `--write` puts it into output/ only, atomically:
    output/NEEDS-YOU.md     for the editor: Arabic first, then English, editor words, Latin runs inside Arabic lines
                            wrapped in FSI…PDI isolates, Markdown/HTML special characters escaped (nothing a producer
                            wrote can render as a link, an image or HTML)
    output/needs-you.json   the twin the panel reads (Phase 6), schemas/needs-you.schema.json, LF line ends
Never data/ or assets/ (an output/ that leads there through a link is refused, nothing written).

Two kinds of source:
  * Producers (the T4.7 contract): a state file holding `needs_you: [{kind, text, text_ar?, why, ref}]`; an empty list
    means nothing is needed, so the derived items that producer owns (PRODUCER_OWNS) are not added next to it.
    Registered: <project>/01_analysis/motion-plan.json (T4.6 music), output/from_website/current.json (Addendum J).
    A new producer is one line in PROJECT_PRODUCERS / CLIENT_PRODUCERS.
  * Derived from the state that exists today:
      pick      an episode with a validated reels plan and no reels picked yet (01_analysis/selection.json): picking
                is the editor's editorial choice, never automatic (a standing approval: auto never picks)
      words     a transcript the editor has not confirmed by ear: flagged (uncertain) words, then words under the
                profile's low_confidence_threshold (02_transcription/words.json + verification.json; only a check
                recorded `by: "editor"` is the editor's ear, an allow-list). A reel cut from an episode defers to its
                episode's item. Motion plans' `approvals` (numbers written from spoken words) too, one per scene
      verse     one line per recited-verse span of the timeline spec (manual verse, lib/manual_verse.py): WhyNot Cut
                never writes Quran text, the editor adds it by hand; the span's words are never quoted (nor listed
                under `words`). The item's `span` holds its times, cue and whether its end is a guess
      medical / religious / business / ai
                review-flags.json rows that are not `ok` (the CURRENT plan's review only: review_flags.load), and
                graphics with approval_required in the timeline spec (kind religious for a religious client); a
                graphic already flagged in the review is listed once, from the review. For a medical or religious
                client a review that is missing, stale or damaged while the plan has on-screen words is one line of
                its own ("the review is not current"): it never vanishes silently. A business or ai row names the
                approver from the review-domain registry; an unknown flag fails closed to medical
      music     a timeline spec whose music is not placed (unless the client's style says none); a motion plan with no
                music and no producer key
      fonts     no font files at all (discovery), or font files not installed (client_db typography.json)
      logo      no logo file (discovery role) and none classified as a logo (asset-manifest.json)
      final     a video that passed QC and is not delivered: the final mix and render are the editor's
      moved     an approval a client move voided on purpose (lib/client_move.py, executor ruling (c) on BL-14 Q1: the
                move points the files it hashes at the new folder), one per item and kind, until it holds again
A DELIVERED video adds nothing. Dedupe key: (source, kind, ref), first one wins. A state file that cannot be read is
named in `unread` (the list may be missing items); a producer item that cannot be shown in `skipped`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from .common import Context, Paths, check_project_id, read_json, use_context

KINDS = ("moved", "pick", "words", "verse", "medical", "religious", "business", "ai", "music", "fonts", "logo", "website",
         "final")
MD_REL = "output/NEEDS-YOU.md"
JSON_REL = "output/needs-you.json"
SCHEMA_VERSION = 1
MAX_TEXT, MAX_WHY, MAX_SNIPPET = 600, 1200, 120
SHOWN_WORDS = 8
FINAL_STATUSES = ("QC_PASSED", "READY_FOR_HUMAN_EDITOR")
BY_EAR = {"editor"}                    # the only `transcript-verify --by` that is the editor's own ear (allow-list)
TOP_FOLDERS = {"assets", "data", "output"}
PROJECT_PRODUCERS = ("01_analysis/motion-plan.json",)           # T4.6
CLIENT_PRODUCERS = ("output/from_website/current.json",)        # Addendum J (website run)
PRODUCER_OWNS = {"01_analysis/motion-plan.json": {"music"}}     # derived kinds the producer's key replaces
FSI, PDI = "⁨", "⁩"
_OVERRIDES = re.compile("[‪-‮]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_TOKEN = r"[A-Za-z0-9#](?:[A-Za-z0-9_./#'&+-]|:(?=[0-9]))*"
_LATIN_RUN = re.compile(_TOKEN + r"(?: (?=[A-Za-z0-9#])" + _TOKEN + r")*")

HEAD = {"pick": ("اختار الريلز", "Pick the reels"),
        "words":("كلمات تتأكد منها بالسمع", "Words to confirm by ear"),
        "verse": ("آيات يضيفها المونتير يدويًا", "Verses to add by hand"),
        "medical": ("موافقات طبية", "Medical approvals"),
        "religious": ("موافقات على المحتوى الديني", "Religious content approvals"),
        "business": ("موافقات على كلام البيزنس", "Business claims approvals"),
        "ai": ("موافقات على كلام الذكاء الاصطناعي", "AI claims approvals"),
        "music": ("الموسيقى", "Music"),
        "fonts": ("الخطوط", "Fonts"),
        "logo": ("اللوجو", "Logo"),
        "website": ("من موقع العميل", "From the client's website"),
        "final": ("المكس والرندر النهائي", "Final mix and render"),
        "moved": ("موافقات تتعمل تاني بعد نقل العميل", "Approvals to give again after the client moved")}


# --------------------------------------------------------------------------- small helpers
def _clip(s: str, n: int) -> str:
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def _tc(ms) -> str:
    ms = max(0, int(ms or 0))
    return f"{ms // 60000}:{ms // 1000 % 60:02d}"


def _ar_words(n: int) -> str:
    """«كلمة واحدة» / «كلمتين» / «3 كلمات» / «11 كلمة» (Arabic number agreement)."""
    return "كلمة واحدة" if n == 1 else "كلمتين" if n == 2 else f"{n} كلمات" if n <= 10 else f"{n} كلمة"


def _line(i: dict, text: str) -> str:
    """The item's text, named by its video, reel or episode when the producer did not say it."""
    t = clean(text)
    return t if not i["item"] or t.startswith(i["item"]) or i["item"] in t[:40] else f"{i['item']}: {t}"


def _sid(*parts) -> str:
    return hashlib.sha1("\n".join(map(str, parts)).encode("utf-8")).hexdigest()[:12]


def _is_path(ref: str) -> bool:
    return "/" in ref or ref in TOP_FOLDERS


def _font_hint() -> tuple[str, str]:
    from . import plat
    if plat.IS_WIN:
        return ("right-click each font file, then Install for all users",
                "كليك يمين على ملف الخط واختار Install for all users")
    if plat.IS_MAC:
        return "double-click each font file, then Install Font", "دبل كليك على ملف الخط واختار Install Font"
    return "copy the font files into your fonts folder", "انسخ ملفات الخط لفولدر الخطوط"


def _event_words(params) -> str:
    """The on-screen words of a compiled graphic, for the editor to recognise it (never the reviewer's text)."""
    out = []
    if isinstance(params, dict):
        for k in ("headline", "title", "text", "subtitle", "name", "label", "value", "caption", "quote"):
            v = params.get(k)
            if isinstance(v, (str, int, float)) and not isinstance(v, bool) and str(v).strip():
                out.append(str(v).strip())
        for it in params.get("items") or []:
            if isinstance(it, dict) and isinstance(it.get("text"), str) and it["text"].strip():
                out.append(it["text"].strip())
    return _clip(" / ".join(out), MAX_SNIPPET)


def clean(s: str) -> str:
    """One line, no bidi overrides (an isolate is fine)."""
    return _CONTROL.sub(" ", _OVERRIDES.sub("", str(s))).strip()


def md_escape(s: str) -> str:
    """Nothing renders as a link, an image, code or HTML: backslash-escape the Markdown specials, `<`/`>` as entities,
    and a `(` right after `]`."""
    s = s.replace("\\", "\\\\")
    for c in "`*_[]!|#~":
        s = s.replace(c, "\\" + c)
    return s.replace("<", "&lt;").replace(">", "&gt;").replace("\\](", "\\]\\(")


_URL = re.compile(r"(?:https?://|www\.)[^\s<>`\"'«»()\[\]]+", re.I)


def fmt(s: str, ar: bool) -> str:
    """One line of NEEDS-YOU.md: a bare web address becomes a code span (never an auto-link), everything else is
    escaped; Arabic lines also get their Latin runs isolated."""
    out, pos = [], 0
    for m in _URL.finditer(s):
        url = m.group(0).rstrip(".,;:!?")
        end = m.start() + len(url)
        part = s[pos:m.start()]
        out.append(md_escape(isolate(part) if ar else part))
        span = "`" + url + "`"
        out.append(FSI + span + PDI if ar else span)
        pos = end
    rest = s[pos:]
    out.append(md_escape(isolate(rest) if ar else rest))
    return "".join(out)


def isolate(s: str) -> str:
    """Latin runs (ids, times, folders, names) inside an Arabic line, each wrapped in FSI…PDI."""
    return _LATIN_RUN.sub(lambda m: FSI + m.group(0) + PDI, s)


# --------------------------------------------------------------------------- collecting
class _Collector:
    def __init__(self, root: Path, given: Path):
        self.root = root
        self.items, self.keys, self.unread, self.skipped = [], set(), [], []
        self._roots = {os.path.normcase(os.path.abspath(str(r))) for r in (root, given)}
        self._unread_keys = set()

    def rel(self, p: Path) -> str:
        return Path(p).relative_to(self.root).as_posix()

    @contextmanager
    def source(self, rel: str, item):
        """A source that cannot be read or has the wrong shape is named in `unread`, never fatal."""
        try:
            yield
        except Exception as e:  # noqa: BLE001 — damaged state: name it, keep the rest of the list
            if (rel, item) not in self._unread_keys:
                self._unread_keys.add((rel, item))
                self.unread.append({"source": rel, "item": item, "why": type(e).__name__})

    def add(self, kind, text, text_ar, why, why_ar, ref, item, source, span=None):
        key = (source, kind, ref)
        if key in self.keys:
            return
        self.keys.add(key)
        it = {"id": _sid(source, kind, ref), "kind": kind, "text": _clip(text, MAX_TEXT)}
        if text_ar:
            it["text_ar"] = _clip(text_ar, MAX_TEXT)
        it["why"] = _clip(why or "", MAX_WHY)
        if why_ar:
            it["why_ar"] = _clip(why_ar, MAX_WHY)
        it["ref"] = ref
        if _is_path(ref):
            it["ref_exists"] = (self.root / ref).exists()
        it["item"], it["source"] = item, source
        if span is not None:                                 # a verse line: its times, cue and guessed end (the panel)
            it["span"] = span
        self.items.append(it)

    def norm_ref(self, ref) -> str | None:
        """A client-root-relative path with forward slashes, or a plan id; None when it leaves the client folder."""
        if not isinstance(ref, str):
            return None
        s = ref.strip().replace("\\", "/")
        if not s or _CONTROL.search(s) or len(s) > 400:
            return None
        if s.startswith("/") or re.match(r"^[A-Za-z]:", s):            # absolute: only inside the client folder
            a = os.path.abspath(s.replace("/", os.sep))
            na = os.path.normcase(a)
            for r in self._roots:
                if na == r:
                    return None
                if na.startswith(r.rstrip(os.sep) + os.sep):
                    s = a[len(r.rstrip(os.sep)) + 1:].replace(os.sep, "/")
                    break
            else:
                return None
        parts = [x for x in s.split("/") if x not in ("", ".")]
        if not parts or ".." in parts:
            return None
        return "/".join(parts)

    def producer(self, path: Path, item) -> bool:
        """The contract's `needs_you` list of one state file; True when the file has the key (even empty)."""
        if not path.exists():
            return False
        src = self.rel(path)
        has = False
        with self.source(src, item):
            doc = read_json(path)
            if not isinstance(doc, dict) or "needs_you" not in doc:
                return False
            has = True
            lst = doc["needs_you"]
            if not isinstance(lst, list):
                self.skipped.append({"source": src, "item": item, "why": "the list of needs is not a list"})
                return True
            for n in lst:
                why = self._bad(n)
                if why:
                    self.skipped.append({"source": src, "item": item, "why": why})
                    continue
                ref = self.norm_ref(n["ref"])
                if ref is None:
                    self.skipped.append({"source": src, "item": item, "why": f"ref outside the client folder: "
                                                                               f"{_clip(n['ref'], 120)}"})
                    continue
                self.add(n["kind"], n["text"], n.get("text_ar"), n.get("why", ""), n.get("why_ar"), ref, item, src)
        return has

    @staticmethod
    def _bad(n) -> str | None:
        if not isinstance(n, dict):
            return f"an item that is not an object ({type(n).__name__})"
        if n.get("kind") not in KINDS:
            return f"unknown kind {_clip(repr(n.get('kind')), 60)}"
        if not isinstance(n.get("text"), str) or not n["text"].strip():
            return f"{n['kind']}: no text"
        for k in ("text_ar", "why_ar"):
            if k in n and (not isinstance(n[k], str) or not n[k].strip()):
                return f"{n['kind']}: {k} is not text"
        if not isinstance(n.get("why", ""), str):
            return f"{n['kind']}: why is not text"
        if not isinstance(n.get("ref"), str) or not n["ref"].strip():
            return f"{n['kind']}: no ref"
        return None


def _children(folder: Path, kind: str) -> list[str]:
    if not folder.is_dir():
        return []
    out = []
    for d in sorted(folder.iterdir(), key=lambda x: x.name):
        if not d.is_dir() or d.name.startswith((".", "_")):
            continue
        try:
            check_project_id(d.name, kind, strict=kind == "episode id")
        except Exception:  # noqa: BLE001 — not a project folder the engine made
            continue
        out.append(d.name)
    return out


class _Config:
    """The client's settings the derivations read, once (defaults when the profile cannot be read)."""

    def __init__(self, c: _Collector):
        from .common import content_domain, load_config
        self.threshold, self.no_music, self.domain = 0.5, False, "general"
        self.verse = {"religious": False, "phrases": [], "warnings": []}
        with c.source("output/client_database/reel-profile", None):
            t = load_config("transcription.json").get("low_confidence_threshold", 0.5)
            self.threshold = float(t) if isinstance(t, (int, float)) and not isinstance(t, bool) else 0.5
            m = load_config("style.json").get("music")
            self.no_music = isinstance(m, str) and m.strip().lower().startswith("none")
            self.domain = content_domain()
            from . import manual_verse
            self.verse = manual_verse.config(load_config("profile.json"))

    @property
    def approval_kind(self) -> str:
        return "religious" if self.domain == "religious" else "medical"


def _words(c: _Collector, cfg: _Config, p: Paths, item: str, label: tuple[str, str]) -> bool:
    """True when this transcript has words for the editor to confirm by ear (an item was added)."""
    wf = p.p("02_transcription/words.json")
    if not wf.exists():
        return False
    src = c.rel(wf)
    added = False
    with c.source(src, item):
        data = wf.read_bytes()
        doc = json.loads(data.decode("utf-8-sig"))
        words = doc["words"]
        if not isinstance(words, list):
            raise TypeError("words is not a list")
        vf = p.p("02_transcription/verification.json")
        ver = None
        if vf.exists():
            with c.source(c.rel(vf), item):
                ver = read_json(vf)
        current = isinstance(ver, dict) and ver.get("verified") is True \
            and ver.get("words_sha1") in (None, hashlib.sha1(data).hexdigest())
        if current and str(ver.get("by") or "").strip().lower() in BY_EAR:
            return False
        # a check recorded by someone else (auto, delegated, Claude, an agent) is not the editor's ear, and the engine
        # already treats it as checked: those words may be on a graphic, so the "why" says so instead of "they stay off"
        flagged = [w for w in words if isinstance(w, dict) and w.get("flagged")]
        low = [w for w in words if isinstance(w, dict) and not w.get("flagged")
               and isinstance(w.get("probability"), (int, float)) and not isinstance(w.get("probability"), bool)
               and w["probability"] < cfg.threshold]
        todo = [w for w in flagged + low if isinstance(w.get("word"), str) and w["word"].strip()]
        verse = _verse_ranges(p, words, cfg)          # manual verse: a recited verse's words are never quoted here
        if verse:
            from .manual_verse import overlaps
            todo = [w for w in todo if not (isinstance(w.get("start_ms"), (int, float))
                                            and isinstance(w.get("end_ms"), (int, float))
                                            and overlaps(w["start_ms"], w["end_ms"], verse))]
        from .safety.risk_words import needs_you_order    # K-T1: risk first (behind its switch)
        todo = needs_you_order(todo, p)
        if not todo:
            return False
        n, shown = len(todo), todo[:SHOWN_WORDS]
        en = ", ".join(f"«{w['word'].strip()}» at {_tc(w.get('start_ms'))}" for w in shown)
        ar = "، ".join(f"«{w['word'].strip()}» عند {_tc(w.get('start_ms'))}" for w in shown)
        more_en = f", and {n - len(shown)} more" if n > len(shown) else ""
        more_ar = f"، و{n - len(shown)} كمان" if n > len(shown) else ""
        c.add("words",
              f"{label[1]}: listen to {n} word{'s' if n != 1 else ''} and tell Claude if "
              f"{'they are' if n != 1 else 'it is'} right: {en}{more_en}",
              f"{label[0]}: اسمع {_ar_words(n)} وقول لـ Claude لو مكتوبة صح: {ar}{more_ar}",
              *(("The transcription was not sure of these words. Someone other than you checked them, so they may "
                 "already be on a graphic: listen before the video goes out.",
                 "التفريغ مكانش متأكد من الكلمات دي، واللي راجعها مش إنت، فممكن تكون ظهرت على الجرافيك: اسمعها قبل "
                 "ما الفيديو يطلع.") if current else
                ("The transcription was not sure of these words. They stay off the graphics until you confirm them "
                 "by ear.",
                 "التفريغ مكانش متأكد من الكلمات دي، ومش هتظهر على الجرافيك لحد ما تتأكد منها بالسمع.")),
              c.rel(p.p("02_transcription/subtitle-review.md")), item, src)
        added = True
    return added


def _verse_ranges(p: Paths, words: list, cfg: "_Config") -> list:
    """Manual verse: the source ranges of this transcript's recited verses: the compiled plan's (the story-editor's
    overrides included) when there is one, else what lib/manual_verse finds in the words (an episode, or a clip not
    planned yet). [] when none (or the plan cannot be read: its own line says so)."""
    from . import manual_verse
    sp = p.p("01_analysis/timeline-spec.json")
    if sp.exists():
        try:
            spec = read_json(sp)
            if isinstance(spec, dict) and spec.get("events") is not None:
                return [(s["src_start_ms"], s["src_end_ms"]) for s in spec.get("manual_verse") or []
                        if isinstance(s, dict)]
        except Exception:  # noqa: BLE001 — named in `unread` by the timeline-spec's own read
            pass
    return [(s["src_start_ms"], s["src_end_ms"]) for s in manual_verse.detect(words, cfg.verse)]


VERSE_WHY = ("WhyNot Cut never writes Quran text: the captions stay empty there and a marker on the timeline shows the "
             "place.",
             "WhyNot Cut عمره ما بيكتب نص قرآن: الكابشن فاضي في المكان ده، وفي ماركر على التايملاين بيوضّح مكانه.")


def _verses(c: _Collector, spec: dict, vid: str, src: str):
    """Manual verse: one line per recited-verse span of the compiled plan: its timecodes and cue, the fixed line,
    whether its end is a guess. Never the span's words."""
    from . import manual_verse as mv
    for s in spec.get("manual_verse") or []:
        if not isinstance(s, dict) or not isinstance(s.get("id"), str):
            continue
        tc, tc2, stc, stc2 = (_tc(s.get(k)) for k in ("start_ms", "end_ms", "src_start_ms", "src_end_ms"))
        cue_ar, cue_en = clean(s.get("cue_ar") or mv.label(s.get("cue"))), clean(s.get("cue_en") or
                                                                                   mv.label(s.get("cue"), "en"))
        guessed = s.get("guessed_end") is True
        ar = (f"{vid}: آية مقروءة عند {tc}–{tc2} على التايملاين ({cue_ar}، في المصدر {stc}–{stc2}): {mv.LINE_AR}"
              + ("؛ ونهاية الآية متخمّنة (وقفنا بعد 12 ثانية)، فحدّد نهايتها بالسمع" if guessed else ""))
        en = (f"{vid}: a recited verse at {tc}-{tc2} on the timeline ({cue_en}; source {stc}-{stc2}): {mv.LINE_EN}"
              + ("; the end of the verse is a guess (cut at 12 s): find the real end by ear" if guessed else ""))
        span = {"start_ms": int(s.get("start_ms") or 0), "end_ms": int(s.get("end_ms") or 0),
                "src_start_ms": int(s.get("src_start_ms") or 0), "src_end_ms": int(s.get("src_end_ms") or 0),
                "cue_ar": cue_ar, "cue_en": cue_en, "guessed_end": guessed}
        c.add("verse", en, ar, *VERSE_WHY, s["id"], vid, src, span=span)


APPROVER = {"medical": ("the doctor's approval", "موافقة طبية"),
            "religious": ("the speaker's approval", "موافقة صاحب المحتوى")}
NEVER_AUTO = {"medical": ("Health claims on screen are never approved automatically.",
                          "الكلام الطبي اللي على الشاشة عمره ما بيتوافق عليه تلقائي."),
              "religious": ("Religious content on screen is never approved automatically.",
                            "المحتوى الديني اللي على الشاشة عمره ما بيتوافق عليه تلقائي."),
              "business": ("Business claims on screen are never approved automatically.",
                           "كلام البيزنس اللي على الشاشة عمره ما بيتوافق عليه تلقائي."),
              "ai": ("AI claims and disclosures on screen are never approved automatically.",
                     "الكلام عن الذكاء الاصطناعي والإفصاح عنه على الشاشة عمره ما بيتوافق عليه تلقائي.")}
REGISTRY_KINDS = ("business", "ai")       # review domains whose approver comes from the registry (review_domains)


def _review_kind(flag) -> tuple[str, tuple[str, str], bool]:
    """(kind, (approver en, approver ar), unknown) of a review row's flag. medical / religious as before; business and
    ai with the approver the review-domain registry names; anything else (or a registry that cannot be read) fails
    closed to medical, the strictest approval, with `unknown` set so the line says why."""
    if flag in APPROVER:
        return flag, APPROVER[flag], False
    if flag in REGISTRY_KINDS:
        try:
            from . import review_domains
            a = review_domains.registry()[flag]["approver"]
            if isinstance(a.get("en"), str) and isinstance(a.get("ar"), str) and a["en"].strip() and a["ar"].strip():
                return flag, (f"the approval of {clean(a['en'])}", f"موافقة {clean(a['ar'])}"), False
        except Exception:  # noqa: BLE001 — fail closed below
            pass
        return "medical", APPROVER["medical"], False
    return "medical", APPROVER["medical"], True


def _review_rows(p: Paths) -> list[dict] | None:
    """The current review's rows that are not `ok`; None when there is no current review (missing, of an older
    plan, or damaged)."""
    from . import review_flags
    doc = review_flags.load(p)
    return None if doc is None else [it for it in doc.get("items", []) if it.get("verdict") != "ok"]


NOT_CURRENT = {"medical": ("the medical review of the words on screen is missing or not current: Claude reviews them "
                           "again before you approve anything",
                           "مراجعة الكلام الطبي اللي على الشاشة مش موجودة أو مش محدّثة: Claude يراجعه تاني قبل ما "
                           "توافق على أي حاجة"),
               "religious": ("the religious review of the words on screen is missing or not current: Claude reviews "
                             "them again before you approve anything",
                             "مراجعة المحتوى الديني اللي على الشاشة مش موجودة أو مش محدّثة: Claude يراجعه تاني قبل "
                             "ما توافق على أي حاجة")}


def _approvals(c: _Collector, cfg: _Config, p: Paths, item: str, spec: dict | None, plan_src: str | None = None,
               has_words: bool = False):
    rf = p.p("review-flags.json")
    flagged_events = set()
    current = False
    if rf.exists():
        src = c.rel(rf)
        with c.source(src, item):
            read_json(rf)                                  # unreadable -> named in `unread` (and not current below)
            rows = _review_rows(p)
            current = rows is not None
            for it in rows or []:
                kind, (who_en, who_ar), unknown = _review_kind(it["flag"])
                gid, tc, words = it["event_id"], _tc(round(float(it.get("start_s") or 0) * 1000)), it.get("text", "")
                flagged_events.add(gid)
                v = it.get("verdict")
                if v == "reword-to-match":
                    en = f"{item}: graphic {gid} at {tc} does not match what was said: approve new wording for «{words}»"
                    ar = f"{item}: الجرافيك {gid} عند {tc} مش مطابق للكلام: وافق على صياغة جديدة بدل «{words}»"
                elif v == "remove":
                    en = f"{item}: the review advises removing graphic {gid} at {tc} («{words}»): confirm"
                    ar = f"{item}: المراجعة بتنصح بشيل الجرافيك {gid} عند {tc} («{words}»): أكّد"
                else:
                    en = f"{item}: graphic {gid} at {tc} needs {who_en}: «{words}»"
                    ar = f"{item}: الجرافيك {gid} عند {tc} محتاج {who_ar}: «{words}»"
                reason = clean(it.get("reason") or "")
                why_en, why_ar = NEVER_AUTO[kind]
                if unknown:
                    f = _clip(clean(it["flag"]), 60)
                    why_en += (f" The review used a review type WhyNot Cut does not know ({f}), so it needs the "
                               "strictest approval.")
                    why_ar += f" المراجعة استخدمت نوع مراجعة WhyNot Cut ما يعرفوش ({f})، فمحتاج أشد موافقة."
                c.add(kind, en, ar, why_en + (f" Review note: {reason}" if reason else ""),
                      why_ar + (f" ملاحظة المراجعة: {reason}" if reason else ""), gid, item, src)
    if cfg.domain in ("medical", "religious") and has_words and plan_src and not current:
        en, ar = NOT_CURRENT[cfg.domain]
        c.add(cfg.domain, f"{item}: {en}", f"{item}: {ar}", *NEVER_AUTO[cfg.domain], c.rel(rf), item, plan_src)
    if spec is not None:
        src = c.rel(p.p("01_analysis/timeline-spec.json"))
        kind = cfg.approval_kind
        who_en, who_ar = APPROVER[kind]
        for e in spec.get("events") or []:
            if not isinstance(e, dict) or not e.get("approval_required") or e.get("event_id") in flagged_events:
                continue
            gid, tc, words = str(e.get("event_id")), _tc(e.get("start_ms")), _event_words(e.get("params"))
            c.add(kind, f"{item}: graphic {gid} at {tc} needs {who_en}: «{words}»",
                  f"{item}: الجرافيك {gid} عند {tc} محتاج {who_ar}: «{words}»", *NEVER_AUTO[kind], gid, item, src)


def _numbers(c: _Collector, plan: dict, item: str, src: str):
    """A motion plan's `approvals`: numbers written from the spoken words, one item per scene."""
    by_scene: dict = {}
    for a in plan.get("approvals") or []:
        if isinstance(a, str) and a.strip():
            m = re.match(r"^\s*([A-Za-z0-9_-]+)\s*:", a)
            by_scene.setdefault(m.group(1) if m else "plan", []).append(clean(a))
    for sid, lines in by_scene.items():
        ref = sid if sid != "plan" else f"output/projects/{item}/01_analysis/motion-plan.md"
        txt = "; ".join(lines)
        c.add("words", f"{item}: confirm by ear: {txt}", f"{item}: اتأكد بالسمع: {txt}",
              "Numbers on screen are written from the spoken words; check them before posting.",
              "الأرقام اللي على الشاشة مكتوبة من الكلام المسموع؛ راجعها قبل النشر.", ref, item, src)


def _project(c: _Collector, cfg: _Config, vid: str, episode_words: set):
    p = Paths(c.root, vid)
    status, src_doc = None, {}
    sf = p.p("08_quality_control/project-status.json")
    if sf.exists():
        with c.source(c.rel(sf), vid):
            st = read_json(sf)
            status = st.get("status") if isinstance(st, dict) else None
    if status == "DELIVERED":
        return
    srcf = p.p("00_inputs/source.json")
    if srcf.exists():
        with c.source(c.rel(srcf), vid):
            d = read_json(srcf)
            src_doc = d if isinstance(d, dict) else {}
    motion = src_doc.get("kind") == "motion_reel"
    if not (src_doc.get("kind") == "episode_reel" and src_doc.get("episode_id") in episode_words):
        _words(c, cfg, p, vid, (vid, vid))
    owned = set()
    for rel in PROJECT_PRODUCERS:
        if c.producer(p.p(rel), vid):
            owned |= PRODUCER_OWNS.get(rel, set())
    spec, plan_src, has_words = None, None, False
    if motion:
        mf = p.p("01_analysis/motion-plan.json")
        if mf.exists():
            src = c.rel(mf)
            with c.source(src, vid):
                plan = read_json(mf)
                if not isinstance(plan, dict):
                    raise TypeError("the motion plan is not an object")
                plan_src = src
                has_words = any(isinstance(e, dict) and isinstance(e.get("text"), str) and e["text"].strip()
                                for sc in plan.get("scenes") or [] if isinstance(sc, dict)
                                for e in sc.get("elements") or [])
                _numbers(c, plan, vid, src)
                if "music" not in owned and not (plan.get("audio") or {}).get("music"):
                    c.add("music", f"{vid}: add a licensed music track in After Effects",
                          f"{vid}: ضيف موسيقى مرخّصة في After Effects",
                          "WhyNot Cut never adds music without a licence.",
                          "WhyNot Cut عمره ما بيحط موسيقى من غير ترخيص.", "data/Music", vid, src)
    else:
        sp = p.p("01_analysis/timeline-spec.json")
        if sp.exists():
            src = c.rel(sp)
            with c.source(src, vid):
                spec = read_json(sp)
                if not isinstance(spec, dict) or not isinstance(spec.get("events", []), list):
                    spec = None
                    raise TypeError("the timeline spec has the wrong shape")
                plan_src = src
                has_words = any(isinstance(e, dict) and _event_words(e.get("params")) for e in spec.get("events") or [])
                _verses(c, spec, vid, src)
                music = spec.get("music") if isinstance(spec.get("music"), dict) else {}
                if music.get("status") != "PLACED" and not cfg.no_music and "music" not in owned:
                    c.add("music", f"{vid}: add a licensed music track (the timeline has markers where it goes)",
                          f"{vid}: ضيف موسيقى مرخّصة (في علامات على التايملاين لمكانها)",
                          "WhyNot Cut never adds music without a licence.",
                          "WhyNot Cut عمره ما بيحط موسيقى من غير ترخيص.", "data/Music", vid, src)
    _approvals(c, cfg, p, vid, spec, plan_src, has_words)
    if status in FINAL_STATUSES:
        ho = p.p("09_handoff/README.md")
        ref = c.rel(ho) if ho.exists() else f"output/projects/{vid}"
        if motion:
            en, ar = (f"{vid}: final look in After Effects, then render and export for posting",
                      f"{vid}: الشكل النهائي في After Effects، وبعدين الرندر والتصدير للنشر")
        else:
            en, ar = (f"{vid}: final mix, polish and render in Premiere",
                      f"{vid}: المكس النهائي واللمسات الأخيرة والرندر في Premiere")
        c.add("final", en, ar, "WhyNot Cut builds the edit; the final video is yours to finish.",
              "WhyNot Cut بيجهّز المونتاج؛ الفيديو النهائي بتاعك إنت تخلّصه.", ref, vid, c.rel(sf))


def _pick(c: _Collector, ep: Paths, item: str):
    """An episode whose reels plan is validated and none of whose reels has been picked yet (selection.json)."""
    vf = ep.p("01_analysis/reels-plan-validated.json")
    if not vf.exists():
        return
    src = c.rel(vf)
    sf = ep.p("01_analysis/selection.json")
    with c.source(src, item):
        read_json(vf)
        if sf.exists():
            with c.source(c.rel(sf), item):
                sel = read_json(sf)
                hist = sel.get("history") if isinstance(sel, dict) else None
                if any(isinstance(h, dict) and h.get("picked") for h in hist or []):
                    return
        c.add("pick", f"Episode {item}: pick the reels you want from the reels plan",
              f"حلقة {item}: اختار الريلز اللي عايزها من خطة الريلز",
              "Picking the reels is your editorial choice; it is never done automatically.",
              "اختيار الريلز قرارك إنت، وعمره ما بيتعمل تلقائي.",
              c.rel(ep.p("01_analysis/reels-plan.md")), item, src)


def _brand(c: _Collector):
    """Fonts and logo, for the whole client."""
    root = c.root
    invf = root / "output/discovery/input-inventory.json"
    typf = root / "output/client_database/branding/typography.json"
    manf = root / "output/client_database/asset-manifest.json"
    man = None
    if manf.exists():
        with c.source(c.rel(manf), None):
            man = read_json(manf)
    if invf.exists():
        src = c.rel(invf)
        with c.source(src, None):
            inv = read_json(invf)
            files = [f for f in (inv.get("files") or []) if isinstance(f, dict)]
            if not any(f.get("kind") == "font" for f in files):
                c.add("fonts", "Add the brand fonts to the assets/Fonts folder (none were found)",
                      "ضيف خطوط البراند في فولدر assets/Fonts (ملقيناش أي خط)",
                      "The graphics use a fallback font until the brand fonts are there.",
                      "الجرافيك هيستخدم خط بديل لحد ما خطوط البراند تكون موجودة.", "assets/Fonts", None, src)
            logos = isinstance(man, dict) and any(isinstance(a, dict) and a.get("category") == "logo"
                                                  for a in man.get("assets") or [])
            if not logos and not any(f.get("role") == "logo" for f in files):
                c.add("logo", "Add the logo to the assets/Logo folder (a PNG with a transparent background is best)",
                      "ضيف اللوجو في فولدر assets/Logo (الأفضل PNG بخلفية شفافة)",
                      "The brand cards and the logo ending need it.",
                      "كروت البراند والنهاية باللوجو محتاجينه.", "assets/Logo", None, src)
    if typf.exists():
        src = c.rel(typf)
        with c.source(src, None):
            typ = read_json(typf)
            missing = typ.get("missing_or_uninstalled") or []
            if not isinstance(missing, list):
                raise TypeError("missing_or_uninstalled is not a list")
            hint_en, hint_ar = _font_hint()
            for f in missing:
                if not isinstance(f, str) or not f.strip():
                    continue
                name = Path(f.replace("\\", "/")).name
                ref = c.norm_ref(f) or "assets/Fonts"
                c.add("fonts", f"Install the font {name} on this computer: {hint_en}",
                      f"نزّل الخط {name} على الجهاز ده: {hint_ar}",
                      "Premiere and After Effects show another font until it is installed.",
                      "Premiere و After Effects هيعرضوا خط تاني لحد ما الخط يتنزّل.", ref, None, src)


def _moved(c: _Collector):
    """The approvals a client move voided on purpose (client_move.VOIDED_REL), each until it holds again."""
    from .client_move import VOIDED_REL, still_void
    f = c.root / VOIDED_REL
    if not f.exists():
        return
    src = c.rel(f)
    with c.source(src, None):
        for v in still_void(c.root):
            c.add("moved", v["text"], v["text_ar"], v["why"], v["why_ar"], v["file"], v["item"], src)


def collect(root, profile: str | None = None) -> dict:
    """The client's checklist (the document of schemas/needs-you.schema.json). Reads only; never raises on damaged
    state (named in `unread` / `skipped`)."""
    given = Path(root).expanduser()
    real = given.resolve()
    c = _Collector(real, given)
    with use_context(Context(real, profile)):
        cfg = _Config(c)
        for rel in CLIENT_PRODUCERS:
            c.producer(real / rel, None)
        _moved(c)
        _brand(c)
        episode_words = set()
        for ep in _children(real / "output" / "episodes", "episode id"):
            from .episode import EpisodePaths
            ep_paths = EpisodePaths(real, ep)
            _pick(c, ep_paths, ep)
            if _words(c, cfg, ep_paths, ep, (f"حلقة {ep}", f"Episode {ep}")):
                episode_words.add(ep)
        for vid in _children(real / "output" / "projects", "video id"):
            _project(c, cfg, vid, episode_words)
    order = {k: i for i, k in enumerate(KINDS)}
    items = sorted(c.items, key=lambda i: (order[i["kind"]], i["item"] is not None, i["item"] or ""))
    counts = {k: n for k in KINDS for n in [sum(1 for i in items if i["kind"] == k)] if n}
    return {"schema_version": SCHEMA_VERSION, "client": given.name or real.name, "items": items, "counts": counts,
            "total": len(items), "unread": c.unread, "skipped": c.skipped}


# --------------------------------------------------------------------------- the Markdown
def _labels(doc: dict) -> tuple[list[str], list[str]]:
    ar, en = [], []
    for u in doc["unread"] + doc["skipped"]:
        a, e = (u["item"], u["item"]) if u["item"] else ("ملفات العميل العامة (البراند والموقع)",
                                                         "the client's own files (brand, website)")
        if e not in en:
            ar.append(a)
            en.append(e)
    return ar, en


def render_md(doc: dict) -> str:
    """NEEDS-YOU.md: Arabic first, then English; one section per kind in a fixed order; no timestamps."""
    client = clean(doc.get("client") or "")
    L = ["# مطلوب منك", "", fmt("القائمة دي بيكتبها WhyNot Cut من جديد من حالة الشغل كل مرة.", True), "",
         fmt("العميل: " + client, True), ""]
    items = doc["items"]
    if not items:
        L += ["لا شيء مطلوب منك الآن.", ""]
    for k in KINDS:
        group = [i for i in items if i["kind"] == k]
        if group:
            L += [f"## {HEAD[k][0]}", ""]
            for i in group:
                L.append("- " + fmt(_line(i, i.get("text_ar") or i["text"]), True))
                why = clean(i.get("why_ar") or i.get("why") or "")
                if why:
                    L.append("  " + fmt(why, True))
            L.append("")
    ar_l, en_l = _labels(doc)
    if ar_l:
        L += ["## ملفات ما اتقرتش", "",
              fmt("في ملفات ما قدرناش نقراها، فالقائمة دي ممكن تكون ناقصة. اطلب من Claude يراجع: "
                  + "، ".join(clean(x) for x in ar_l), True), ""]
    L += ["---", "", "# Needs you", "", "WhyNot Cut rewrites this list from the current state of the work each time.",
          "", fmt("Client: " + client, False), ""]
    if not items:
        L += ["Nothing needs you right now.", ""]
    for k in KINDS:
        group = [i for i in items if i["kind"] == k]
        if group:
            L += [f"## {HEAD[k][1]}", ""]
            for i in group:
                L.append("- " + fmt(_line(i, i["text"]), False))
                why = clean(i.get("why") or "")
                if why:
                    L.append("  " + fmt(why, False))
            L.append("")
    if en_l:
        L += ["## Files that could not be read", "",
              fmt("Some files could not be read, so this list may be missing items. Ask Claude to check: "
                  + ", ".join(clean(x) for x in en_l) + ".", False), ""]
    return "\n".join(L).rstrip("\n") + "\n"


# --------------------------------------------------------------------------- writing
def _inside(path: str, folder: str) -> bool:
    a, b = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(folder))
    return a == b or a.startswith(b.rstrip(os.sep) + os.sep)


def _put(path: Path, data: bytes) -> bool:
    """Atomic replace (a temp file next to it, then os.replace, retried while a reader holds it on Windows); nothing
    is written when the bytes are already there. True when the file changed."""
    try:
        if path.is_file() and path.read_bytes() == data:
            return False
    except OSError:
        pass
    tmp = path.with_name(f".{path.name}.{os.getpid()}-{secrets.token_hex(4)}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        for k in range(50):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if k == 49:
                    raise
                time.sleep(0.01)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return True


def write(root, profile: str | None = None) -> dict:
    """Write output/needs-you.json then output/NEEDS-YOU.md (each atomic, untouched when unchanged). Refused, with
    nothing written: not a client folder, an output/ that leads into data/ or assets/, or a document that does not
    match its schema."""
    from .errors import Guidance
    from . import schemas
    root = Path(root).expanduser()
    if not ((root / "assets").is_dir() and (root / "data").is_dir()):
        raise Guidance(f"{root} is not a client folder: it needs assets/ and data/ (nothing was written)",
                       "Pass --root the client folder itself (the one that holds assets/ and data/).", where=str(root))
    doc = collect(root, profile)
    errs = schemas.validate(doc, "needs-you")
    if errs:
        raise Guidance("the checklist came out malformed, so nothing was written: " + "; ".join(
            f"{e['path'] or '/'}: {e['msg']}" for e in errs[:5]),
            "Report this to The Why Not AI with output/logs/pipeline.log; the earlier list (if any) is unchanged.",
            where=str(root / JSON_REL))
    md = render_md(doc).encode("utf-8")
    js = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    out_dir, jpath, mpath = root / "output", root / JSON_REL, root / MD_REL
    for t in (out_dir, jpath, mpath):
        for name in ("data", "assets"):
            if _inside(str(t), str(root / name)):
                raise Guidance(f"{t} leads into the client's {name}/ through a link: WhyNot Cut never writes there "
                               "(nothing was written)",
                               "Remove that link (only the link itself, never what it points to), then run it again.",
                               where=str(t))
    out_dir.mkdir(exist_ok=True)
    changed = _put(jpath, js)
    changed = _put(mpath, md) or changed
    return dict(doc, ok=True, written=True, unchanged=not changed, files={"md": str(mpath), "json": str(jpath)})
