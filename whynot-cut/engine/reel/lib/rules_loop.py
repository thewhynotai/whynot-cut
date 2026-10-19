# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The learning loop (3.0 Phase 4 T4.3): the editor's recurring feedback becomes the client's standing rules.

Files (all inside the client folder; nothing is written through a link):
    output/projects/<ID>/01_analysis/revision-notes.json   the comments of each revise round, written by `record`
    output/client_database/reel-profile/rules.json         the client's rules: active, replaced, removed (the registry)
    output/client_database/reel-profile/notes.md           the prose Claude reads: a marked block made from the registry
    output/client_database/reel-profile/style.json         T4.2's knobs, set only through style_knobs' own checks

How a comment is read. The revise skill labels every comment it records with an intent, because the engine cannot
tell that «الكابشن صغير», «كبّر الخط» and "captions too small" say the same thing:
    {"knob": "<a T4.2 knob>", "direction": "up|down|on|off|value", "value": ...}   or
    {"topic": "<stable English key>", "area": "<one of AREAS>", "direction": "on|off" (when it can be reversed)}
`record` refuses a comment without a label, and a notes-only label without its area. Area "process" (who reviews,
approves, checks, receives or publishes the video, disclaimers, claims kept against a flag) is never a rule.
Comments are grouped by that label; a comment without one is never counted (it is listed under `warnings`).
A group becomes a proposal when it was said on two or more videos, or once with a standing word ("always", "never",
«دايماً», «أبداً»; not «مش دايماً»). A comment for this clip only (scope "this_clip", «في الفيديو ده بس») never counts.
Two groups that set the same knob (or topic) differently are a conflict: both are shown, the editor picks one.

What a rule can never do: switch off or weaken the medical or religious review, the approval gates, the K1 safety
switches or the QC. Such a comment is never proposed; it is listed under `refused` with a plain sentence, and `add`
refuses it. Only the four T4.2 knobs ever reach style.json; any other label goes to notes.md only.

`record`, `add`, `dismiss` and `remove` are the lead's: the guard lets only the main conversation run them. Every
comment keeps its `source` (comment | review_list | hand_edit) so the V1 cut-review list and Premiere hand edits can feed the same
grouping later.
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from . import linksafe, style_knobs
from .common import CLIENT_PROFILE_REL, check_project_id, file_locked, frame_size_of, now_iso
from .errors import FileFormatError, Guidance

NOTES_REL = "01_analysis/revision-notes.json"
RULES_FILE = "rules.json"
NOTES_MD = "notes.md"
SOURCES = ("comment", "review_list", "hand_edit")
SCOPES = ("standing", "this_clip")
DIRECTIONS = ("up", "down", "on", "off", "value")
STEP = 1.15                                   # "bigger captions" with no number: the current size x 1.15
MAX_TEXT = 2000
BLOCK_START = "<!-- whynot-cut:client-rules:start (written by `reel rules`; change them with `reel rules`) -->"
BLOCK_END = "<!-- whynot-cut:client-rules:end -->"
_MARK_START = "<!-- whynot-cut:client-rules:start"
SCHEMA = 1

# ---------------------------------------------------------------------------------------------------- text reading
_MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
                       "’": "'", "‘": "'", "`": "'"})
_PUNCT = re.compile(r"[^\w\s']+")


def norm(text: str) -> str:
    """Matching form: NFKC, Arabic marks and tatweel removed, letter forms folded (أ→ا, ى→ي, ة→ه), lower case,
    punctuation to spaces, single spaces. Never shown; the stored comment keeps the editor's own text."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = _MARKS.sub("", s).replace("بدأ", "بدء")         # «ابدأ / يبدأ» (start) never folds into «ابدا» (never)
    s = s.translate(_FOLD).lower()
    return " ".join(_PUNCT.sub(" ", s).replace("_", " ").split())


def _has(s: str, words) -> bool:
    """Whether any of `words` (already in norm() form) occurs in s as whole words (a glued و/ف/ب/ل/ك, «ال», «لل»,
    «وال», «بال» before an Arabic word counts: «لمراجعه», «للدكتور», «والموافقه»)."""
    for w in words:
        if re.search(r"(?<![\w])(?:وال|بال|فال|كال|لل|ال|[وفبلك])?" + re.escape(w) + r"(?![\w])", s):
            return True
    return False


_STANDING = ("always", "never", "every time", "every video", "every reel", "all videos", "all the videos",
             "from now on", "going forward", "in every video", "each time",
             "دايما", "دائما", "ابدا", "ولا مره", "كل مره", "كل فيديو", "كل الفيديوهات", "علي طول", "على طول", "بعد كده",
             "بعد كدا", "من هنا ورايح", "من النهارده", "في كل الفيديوهات", "في كل فيديو")
_NOT_STANDING = ("not always", "not every time", "not necessarily", "doesn't always", "doesnt always",
                 "don't always", "dont always", "isn't always", "isnt always", "not every", "not all",
                 "never mind", "not each",
                 "مش دايما", "مش دائما", "مش كل مره", "مش لازم دايما", "مش شرط", "مش ابدا", "ليس دايما", "ليس دائما",
                 "مو دايما", "مش على طول", "مش علي طول", "مش كل", "مش في كل", "مش لازم كل")
_THIS_CLIP = ("this video only", "only this video", "only in this video", "just this video", "just this one",
              "this one only", "this clip only", "only this clip", "only in this clip", "just for this video",
              "only for this video", "only here", "just here", "only this time", "just this time", "this time only",
              "just once", "only once",
              "في الفيديو ده بس", "الفيديو ده بس", "في الفيديو دا بس", "الفيديو دا بس", "المره دي بس", "هنا بس",
              "في الكليب ده بس", "الكليب ده بس", "في الريل ده بس", "الريل ده بس", "للفيديو ده بس", "لهذا الفيديو فقط",
              "في هذا الفيديو فقط", "مره واحده بس", "المره دي وبس", "في الفيديو ده وبس", "في الفيديو دا وبس",
              "الفيديو ده وبس", "الفيديو دا وبس", "هنا وبس", "لمره واحده")


_ALONG = re.compile(r"(?<!\w)(?:على|علي) طول (?=ال)")


def standing_word(text: str) -> bool:
    """A standing word ("always", «دايماً», «أبداً», "from now on") that is not negated («مش دايماً», "not always").
    «على طول الجملة» (along the sentence) is not «على طول» (always)."""
    s = _ALONG.sub("طول ", norm(text))
    if _has(s, [norm(w) for w in _NOT_STANDING]):
        return False
    return _has(s, [norm(w) for w in _STANDING])


_FREQUENCY = re.compile(r"(?<!\w)once (?:a|an|per|every|each)(?!\w)|(?<!\w)مره (?:في|كل)(?!\w)")


def this_clip_only(text: str) -> bool:
    """"for this video only" and its forms; "only once a week" / «مرة في الأسبوع» is a frequency, never this clip."""
    s = norm(text)
    return _has(_FREQUENCY.sub(" ", s), [norm(w) for w in _THIS_CLIP])


# ---- safety: a rule may never weaken a review, an approval gate, a K1 switch or the QC (owner upgrade 6)
# The class, not a list of bad sentences: a client rule is a style or content choice and never needs to speak about
# the review process at all. So (1) a comment that names the review, an approval, the QC, a disclaimer, a fact check
# or a K1 switch is never a rule, in either direction ("never skip the review" too: it always runs anyway); (2) one
# that names the doctor or the sheikh together with a word that drops them (skip, without, «من غير», «مش لازم») is
# refused unless it is plainly about a style element (music, captions, the name card...) and does not say who sees or
# gets the video; (3) publishing "automatically / straight away / without ..." is refused. The engine's gates do not
# read notes.md either: this keeps the brief the story-editor follows free of such lines.
_PROCESS = ("review", "reviews", "reviewer", "reviewers", "reviewed", "reviewing", "approval", "approvals", "approve",
            "approves", "approved", "approving", "auto approve", "qc", "quality check", "quality checks",
            "quality control", "fact check", "fact checks", "fact checking", "fact checked", "disclaimer",
            "disclaimers", "sign off", "signoff", "k1", "safety switch", "safety switches", "safety check",
            "safety checks", "verification", "checker", "review flags", "medical flags",
            "مراجعه", "مراجعته", "مراجعتها", "يراجع", "يراجعه", "يراجعها", "تراجعه", "تراجعها", "نراجع", "نراجعه",
            "راجعه", "موافقه", "موافقته", "موافقتها", "يوافق عليه", "يوافق عليها", "توافق عليه", "توافق عليها",
            "اعتماد", "اعتمده", "اعتمدها", "يعتمده", "يعتمدها", "مراجعه الجوده", "فحص الجوده", "مراقبه الجوده",
            "تنويه", "اخلاء مسؤوليه", "اخلاء المسؤوليه", "اخلاء مسئوليه", "تدقيق",
            "consult your doctor", "consult a doctor", "ask your doctor", "see your doctor", "health claim",
            "health claims", "medical claim", "medical claims", "flagged", "the flags", "استشر طبيبك",
            "استشير الدكتور", "استشير دكتورك", "استشر الطبيب", "ارجع للدكتور", "ارجع لدكتورك", "اسال دكتورك",
            "ادعاء طبي", "ادعاءات طبيه", "فلاجز", "فلاج", "الفلاجات")
# a person or a check that a "drop" word may remove: refused unless the comment is plainly about a style element
_PERSON = ("doctor", "doctors", "doc", "dr", "physician", "medic", "medical", "sheikh", "shaykh", "scholar",
           "religious", "check", "checks", "checking", "flag", "flags",
           "دكتور", "دكتوره", "طبيب", "طبيبه", "شيخ", "د", "طبي", "طبيه", "شرعي", "شرعيه", "فحص", "الفحص الطبي")
_DROP = ("skip", "skips", "skipping", "without", "no", "no need", "stop", "remove", "drop", "bypass", "ignore", "leave out",
         "cut out", "turn off", "switch off", "disable", "anymore", "any more", "soften", "tone down",
         "من غير", "بدون", "دون", "بلاش", "شيل", "الغي", "مش محتاج", "مش محتاجين", "مش محتاجه", "مش لازم", "لا داعي",
         "لا حاجه", "مالوش لازمه", "ملوش لازمه", "مالهاش لازمه", "سيبك من", "تجاهل", "اتجاهل", "تخطي", "تخطى",
         "اتخطي", "تجاوز", "متستناش", "ماتستناش", "خفف", "قلل")
_SEES = ("see", "sees", "seeing", "look at", "looks at", "send", "sends", "sending", "sent", "watch", "watches",
         "looking", "looking at", "checking", "reviewing", "approving", "seeing", "watching",
         "wait for", "waiting for", "يشوف", "تشوف", "يشوفه", "تشوفه", "يشوفها", "تشوفها", "يبص", "تبص", "نبعت",
         "نبعته", "يتبعت", "ابعت", "ابعته", "تبعت", "يتفرج", "تتفرج", "نوري", "نوريه", "يطلع", "تستني", "نستني",
         "يستني", "استني")
_STYLE = ("music", "song", "caption", "captions", "subtitle", "subtitles", "font", "colour", "color", "logo", "sound",
          "sfx", "card", "name card", "graphic", "graphics", "transition", "transitions", "broll", "b roll", "zoom",
          "background", "name", "title", "intro", "outro", "voice", "mic", "sentence", "pause", "pauses", "um",
          "ums", "uh", "head", "face", "crop", "dua", "phone", "number", "frame", "shot", "angle", "cut", "jump cut",
          "mouth", "jargon", "terms", "term", "on screen", "slow mo", "slowmo", "slow motion", "jump cuts", "filter",
          "filters", "hand", "hands", "cough", "coughs", "sneeze", "sneezes", "yawn", "yawns", "drinks", "eats",
          "مؤثرات", "مؤثر", "مصطلحات", "مصطلح", "زووم", "ايد", "ايده", "ايديه", "كحه", "عطسه", "بيشرب", "بياكل",
          "بيعطس", "فلتر",
          "موسيقى", "موسيقي", "مزيكا", "كابشن", "خط", "لون", "لوجو", "صوت", "كارت", "جرافيك", "ترانزيشن", "زوم",
          "خلفيه", "اسم", "اسمه", "اسمها", "عنوان", "تايتل", "مقدمه", "انترو", "جمله", "سكته", "همهمه", "وش",
          "وشه", "راس", "صوره", "كادر", "دعاء", "بي رول", "تليفون", "رقم", "زاويه", "لقطه")
# "show the clip to the doctor", "show the doctor the text": who gets to see it (a send/see verb)
_SHOW_TO = re.compile(r"(?<!\w)show(?:ing|s)?\b.{0,40}?\bto (?:the |our |your )?(?:doctor|doc|dr|sheikh|shaykh|scholar)"
                      r"(?!\w)|(?<!\w)(?:run|runs|running|pass|passes|passing)\b.{0,40}?\bby (?:the |our |your )?"
                      r"(?:doctor|doc|dr|sheikh|shaykh|scholar)(?!\w)|(?<!\w)show(?:ing|s)? (?:the |our )?(?:doctor|doc|dr|sheikh|shaykh)(?:'s)? "
                      r"(?:the|it|this|that|these|those|them|a|an|anything|everything)(?!\w)")
# "the doctor eating", "the sheikh yawning": what is on screen (a style choice), unless the verb is seeing or checking
_ON_SCREEN = re.compile(r"(?<!\w)(?:doctor|sheikh|shaykh|dr)(?:'s)? (?!(?:looking|checking|reviewing|approving|"
                        r"seeing|watching|signing)\b)\w+ing(?!\w)")
_PUBLISH = ("publish", "publishes", "publishing", "published", "post it", "auto post", "upload it", "go live",
            "goes live", "deliver", "delivers", "delivery", "send it to the client", "send to the client",
            "straight to the client", "to the client",
            "انشر", "ينشر", "ننشر", "نشر", "يتنشر", "تتنشر", "انشره", "ننشره", "سلم", "سلمه", "سلمها", "نسلم",
            "يتسلم", "للعميل", "نزله", "نزلها", "ارفعه", "ارفعها", "يترفع")
_AUTO = ("auto", "automatic", "automatically", "straight", "straight away", "directly", "immediately", "right away",
         "as soon as", "once it renders", "every time it renders", "without", "skip", "without waiting",
         "اوتوماتيك", "تلقائي", "تلقائيا", "مباشره", "على طول", "علي طول", "علطول", "فورا", "اول ما", "من غير",
         "بدون", "دون", "متستناش", "ماتستناش")
_SAFE_PHRASES = ("safe zone", "safe zones", "safety zone", "safety zones", "safe area", "منطقه الامان",
                 "review section", "review part", "review clip", "review clips", "patient review", "patient reviews",
                 "customer review", "customer reviews")
_GUARDED_KEYS = re.compile(r"(?:^|[_\-\s.])(reviews?|reviewers?|approv\w*|qc|disclaimers?|k_?t\d+|kt\d+|k1|"
                           r"verify|verification|fact_?check\w*|sign_?off|safety_?(?:switch|check)\w*|deliver\w*|"
                           r"publish\w*)(?:$|[_\-\s.])", re.I)
_GUARDED_KEY_PAIRS = re.compile(r"auto.?publish|publish.?(?:direct|straight|auto)|skip.?(?:doctor|sheikh|review)|"
                                r"no.?(?:doctor|sheikh|review)|without.?(?:doctor|sheikh|review)|bypass|go.?live|"
                                r"send.?(?:direct|straight)|to.?client", re.I)


# ---- S1-T4.3 round 2 (review b399ed2 P1-1; ruling: accept the over-block and widen it): a notes-only rule becomes
# a line in the brief the agents read, so its words may not NAME any object a gate protects, in any direction or
# phrasing: a reviewer (doctor, sheikh, scholar), a review / approval / OK / waiting for someone, the QC, a
# disclaimer or warning line, a claim, numbers or doses, verses / hadith / religious rulings, retakes and pre-ticks,
# quoting word for word, flags, publishing. These are the nouns, not the verbs that drop them, so a new way of saying
# "skip it" still names the thing it skips. Over-blocking is the accepted failure: a refused style comment is still
# done by hand for its video. The four T4.2 knob rules are exempt: their rule sets only that knob and the brief shows
# the knob's own summary, never the comment's words.
# English stems match at a word start (any ending), Franco-Arabic ones anywhere; short ones only as whole words.
_OBJ_EN = re.compile(
    r"(?<![a-z0-9])(?:doctor|physician|medic|pharmac|nurse|sheik|shaykh|scholar|imam|mufti|cleric|reviewer|review|"
    r"approv|sign ?off|permission|consent|confirm|verif|check(?!list)|quality|disclaim|consult|warning|caution|caveat|"
    r"claim|number|numer|dose|dosage|dosing|milligram|percent|statistic|verse|ayah|ayat|quran|qur'an|koran|mushaf|"
    r"surah|hadith|hadeeth|sunnah|fatwa|scriptur|religio|sharia|retake|re take|pre ?tick|tick|pre ?select|verbatim|"
    r"quot|transcri|paraphras|flag|needs you|publish|upload|go live|deliver|schedul|gate|safety|compliance|legal|"
    r"lawyer|audit)"
    r"|raj3|raga3|waf2|ra2am|ar2am"                # Franco-Arabic stems, inside a word (moraga3a, mwaf2a)
    r"|(?<![a-z0-9])(?:dr|doc|qc|mg|k1|aya|sura|she5|shei5|stats?)(?![a-z0-9])"
    r"|(?<![a-z0-9])k ?t ?\d|(?<![a-z0-9])(?:my|your|his|her|their|the|an) ok(?![a-z0-9])"
    r"|(?<![a-z0-9])(?:ask|asking|asked|wait|waiting|waited)(?: for)? (?:me|us|him|her|them|my|our|your)(?![a-z])"
    r"|(?<![a-z0-9])(?:word for word|as said|as spoken|as transcribed|go ahead|green ?light)(?![a-z0-9])")
# Arabic stems (norm() form) match anywhere inside a word, so a glued prefix or suffix never hides them
# («لمراجعتي», «موافقتي», «اعتمدها», «متعلمش»); words that are also ordinary style words match whole only.
_OBJ_AR_IN = ("دكتور", "دكاتره", "طبيب", "اطباء", "صيدل", "ممرض", "شيخ", "مشايخ", "مفتي", "راجع", "مراجع", "وافق",
              "اعتمد", "اعتماد", "استاذن", "اذن", "سالني", "تسال", "سالك", "رايي", "رايك", "ستني", "ستنا", "كيو سي",
              "كيوسي", "كواليتي", "فحص", "تشيك", "تدقيق", "تحقق", "تاكد", "تنويه", "تنبيه", "تحذير", "اخلاء", "مسؤوليه",
              "مسئوليه", "استشر", "استشير", "استشار", "ادعاء", "رقم", "ارقام", "جرعه", "جرعات", "مليجرام", "ملجم",
              "مئوي", "في الميه", "احصائ", "ايات", "الايه", "قران", "قرءان", "مصحف", "سوره", "احاديث", "فتوي", "فتاوي",
              "شرعي", "شريعه", "تفسير", "تلاوه", "تجويد", "النبي", "الرسول", "صلي الله", "اعاده", "اعادات", "ريتيك",
              "علم", "علامه", "اقتباس", "حرفي", "اتقال", "طابق", "فلاج", "نشر", "منشور", "بوابه", "قانون", "محامي")
_OBJ_AR_WORD = ("د", "الحديث", "حديث شريف", "حديث نبوي", "طبي", "طبيه", "ديني", "دينيه", "صح", "تيك", "شيك", "سنه النبي", "على طول من غير")


def names_a_safety_object(text: str) -> bool:
    """Whether a comment names anything a gate protects (see above). On norm() text; the safe-zone layout words
    are removed first."""
    s = _ALONG.sub("طول ", norm(text))
    for phrase in _SAFE_PHRASES:
        s = re.sub(r"(?<!\w)" + re.escape(norm(phrase)) + r"(?!\w)", " ", s)
    s = re.sub(r"(?<!\w)تيك توك(?!\w)|tik ?tok", " ", s)       # the platform, not a tick
    if _OBJ_EN.search(s):
        return True
    if any(norm(w) in s for w in _OBJ_AR_IN):
        return True
    return _has(s, [norm(w) for w in _OBJ_AR_WORD])


def weakens_safety(text: str = "", intent: dict | None = None) -> bool:
    """Whether a comment or its label touches the review, an approval gate, the QC, a disclaimer or a K1 switch
    (any direction), drops the doctor / sheikh, or publishes without them («من غير مراجعة الدكتور», "skip the doctor",
    "always auto-publish", topic auto_approve, knob k_t5_...). Such a comment never becomes a rule. Unless the label
    is one of the four allowlisted knobs, naming any gate's object at all is enough (names_a_safety_object)."""
    intent = intent if isinstance(intent, dict) else {}
    if not _knob(intent.get("knob")) and (names_a_safety_object(text) or names_a_safety_object(
            " ".join(str(intent.get(k) or "") for k in ("topic", "knob")))):
        return True
    if intent.get("area") == PROCESS_AREA:
        return True
    for key in (intent.get("knob"), intent.get("topic")):
        if isinstance(key, str) and key.strip():
            k = key.strip()
            if k not in style_knobs.DEFAULTS and k not in style_knobs.ALIASES and (
                    _GUARDED_KEYS.search(f"_{k}_") or _GUARDED_KEY_PAIRS.search(k)):
                return True
    s = _ALONG.sub("طول ", norm(text))
    for phrase in _SAFE_PHRASES:                       # the platform safe zones are a layout word, not a safety gate
        s = re.sub(r"(?<!\w)" + re.escape(norm(phrase)) + r"(?!\w)", " ", s)
    if not s.strip():
        return False
    w = lambda ws: _has(s, [norm(x) for x in ws])        # noqa: E731
    if w(_PROCESS):
        return True
    dropped = w(_DROP) or _negated(s)
    sees = w(_SEES) or bool(_SHOW_TO.search(s))
    on_screen = w(_STYLE) or bool(_ON_SCREEN.search(s))
    if w(_PERSON) and dropped and (sees or not on_screen):
        return True
    return w(_PUBLISH) and (w(_AUTO) or dropped)


REFUSED_AR = ("الملاحظة دي بتلمس حاجة المراجعة بتحميها (الدكتور أو الشيخ، الموافقة، الـ QC، التنبيهات، الأرقام، الآيات، "
              "الإعادات، الاقتباس الحرفي أو النشر)، فمش هتبقى قاعدة ثابتة: المراجعة الطبية والدينية وبوابات الموافقة "
              "والـ QC بتفضل شغالة زي ما هي دايماً. لو هي طلب شكل بس، اتعمل في الفيديو ده بإيدك.")
REFUSED_EN = ("This touches something the review protects (the doctor or sheikh, an approval, the QC, a disclaimer, "
              "numbers, verses, retakes, quoting word for word or publishing), so it can never become a standing rule: "
              "the medical and religious review, the approvals and the QC always run as they are. If it is only a "
              "style request, it is done by hand in this video.")


# ---- S1-T4.3 final round (executor ruling after review 3b4ec0e, option A): STRUCTURED preferences only. A learned
# preference is {area, phrase id} from the engine's own vocabulary (config/defaults/preference-phrases.json, read from
# the plugin only: a client folder cannot override it). The lead picks the phrase id when it labels a comment; the
# brief prints the ENGINE's phrase, never the editor's words, so no wording can carry a gate change into it. A wish
# with no phrase (or a phrase of another area) is never a rule: --propose lists a recurring one under `by_hand`.
PHRASES_FILE = "preference-phrases.json"
_PHRASE_ID = re.compile(r"[a-z][a-z0-9_]{1,40}")
_PHRASE_BAD = re.compile(r"[{}<>`\n\r]|<!--|-->")
PHRASE_MAX = 160
BY_HAND_AR = "اتقال في {n} فيديوهات: طبّقه يدوي في كل فيديو"
BY_HAND_EN = "said on {n} videos: apply by hand per video"
_VOCAB: dict = {}


def phrases() -> dict:
    """{area: {phrase id: {"group", "en", "ar"}}}, checked once: known areas only (never process / other_style), ids
    and groups short lower-case keys, both texts present, at most PHRASE_MAX characters, one line, no format field,
    markup or comment marker. A damaged vocabulary is a plugin bug: Guidance, nothing is learned."""
    if _VOCAB:
        return _VOCAB
    from .common import CONFIG_DIR, read_json
    path = CONFIG_DIR / PHRASES_FILE
    try:
        doc = read_json(path, None)
    except FileFormatError:
        doc = None
    areas = (doc or {}).get("areas") if isinstance(doc, dict) and doc.get("schema") == 1 else None
    if not isinstance(areas, dict):
        raise Guidance(f"{path}: the preference vocabulary is missing or damaged", "reinstall the plugin",
                       where=str(path))
    out = {}
    for area, items in areas.items():
        if area not in AREAS or area in (PROCESS_AREA, "other_style") or not isinstance(items, dict):
            raise Guidance(f"{path}: area {area!r} cannot hold preferences", "reinstall the plugin", where=str(path))
        for pid, ph in items.items():
            ok = (isinstance(pid, str) and _PHRASE_ID.fullmatch(pid) and isinstance(ph, dict)
                  and isinstance(ph.get("group"), str) and _PHRASE_ID.fullmatch(ph["group"])
                  and all(isinstance(ph.get(k), str) and 0 < len(ph[k]) <= PHRASE_MAX
                          and not _PHRASE_BAD.search(ph[k]) for k in ("en", "ar")))
            if not ok:
                raise Guidance(f"{path}: phrase {area}.{pid} is not a valid entry", "reinstall the plugin",
                               where=str(path))
        out[area] = {pid: {k: items[pid][k] for k in ("group", "en", "ar")} for pid in items}
    _VOCAB.update(out)
    return _VOCAB


def phrase_of(label) -> tuple[str, str] | None:
    """(area, phrase id) when the label names a phrase of ITS OWN area in the vocabulary, else None."""
    if not isinstance(label, dict):
        return None
    area, pid = label.get("area"), label.get("phrase")
    if isinstance(area, str) and isinstance(pid, str) and pid in phrases().get(area, {}):
        return area, pid
    return None


def _notes_only(label) -> bool:
    """A label that is not one of the four T4.2 knobs (its rule would be a preference in the brief)."""
    return not _knob((label or {}).get("knob"))


# ---- the keyword reader: a label read from the words (a helper; history() never counts an unlabelled comment)
_CAPTION = ("caption", "captions", "subtitle", "subtitles", "font", "text size", "الكابشن", "كابشن", "الكابشنز",
            "الخط", "خط", "الترجمه", "الكلام اللي على الشاشه")
_BIGGER = ("bigger", "larger", "increase", "too small", "is small", "are small", "so small", "very small",
           "كبر", "كبري", "كبروا", "اكبر", "صغير", "صغيره", "صغيرين", "مش باين", "مش واضح")
_SMALLER = ("smaller", "reduce", "too big", "too large", "is big", "are big", "so big", "huge",
            "صغر", "صغري", "صغروا", "اصغر", "كبير", "كبيره", "كبيرين")
_SOUND = ("sound", "sfx", "click", "whoosh", "swoosh", "pop", "صوت", "الصوت", "التكه", "الصوت بتاع")
_TITLE = ("title", "hook title", "hook", "عنوان", "العنوان", "الهوك", "هوك", "التايتل")
_MUTE = ("no", "without", "remove", "mute", "kill", "drop", "من غير", "بدون", "بلاش", "شيل", "الغي", "اقفل")
_HOOK = ("hook", "hook title", "الهوك", "هوك", "عنوان الهوك")
_SHOW = ("keep", "show", "leave", "سيب", "خلي", "اظهر", "ظاهر", "يفضل")
_HIDE = ("hide", "remove", "drop", "اخفي", "شيل", "يختفي", "بلاش")
_HIGHLIGHT = ("highlight", "highlight colour", "highlight color", "لون التمييز", "التمييز", "الهايلايت", "هايلايت")
_HEX = re.compile(r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")


_NEGATION = re.compile(r"(?<![\w'])(?:not|no longer|never|dont|don't|doesnt|doesn't|isnt|isn't|arent|aren't|"
                       r"wasnt|wasn't|shouldnt|shouldn't|[وف]?مش|مو|[وف]?ما|[وف]?لا|ليس|مب|مش هو|بلاش)(?![\w'])|"
                       r"\w+n't(?![\w'])|"
                       r"(?<!\w)[وف]?م\w{2,}ش(?!\w)")


def _negated(s: str) -> bool:
    """A negation anywhere in the (norm()) comment: «مش», «ما … ش», «متكبرش», "not", "don't", "never"."""
    return bool(_NEGATION.search(s))


def read_intent(text: str) -> dict | None:
    """A label for an old comment that has none, from its words; None when no T4.2 knob is clearly meant. A negated
    comment («الكابشن مش صغير», "not too small") is never read as a knob: its words then group as they are."""
    s = norm(text)
    w = lambda ws: _has(s, [norm(x) for x in ws])        # noqa: E731
    if w(_HIGHLIGHT):
        m = _HEX.search(str(text))
        return {"knob": "highlight_colour", "direction": "value", "value": m.group(0)} if m else None
    if w(_SOUND) and w(_TITLE) and w(_MUTE):              # the negation IS the meaning here («من غير صوت»)
        return {"knob": "hook_title_sfx", "direction": "off"}
    if _negated(s):
        return None
    if w(_CAPTION) and w(_HOOK) and not w(_SOUND):
        if w(_HIDE):
            return {"knob": "captions_during_hook", "direction": "off"}
        if w(_SHOW):
            return {"knob": "captions_during_hook", "direction": "on"}
    if w(_CAPTION):
        up, down = w(_BIGGER), w(_SMALLER)
        if up != down:
            return {"knob": "caption_size_px", "direction": "up" if up else "down"}
    return None


# ---------------------------------------------------------------------------------------------------- the knobs
def _knob(name) -> str | None:
    if not isinstance(name, str):
        return None
    name = style_knobs.ALIASES.get(name.strip(), name.strip())
    return name if name in style_knobs.DEFAULTS else None


AREAS = ("captions", "music", "sound", "graphics", "cards", "cuts", "pacing", "hook", "ending", "broll", "colour",
         "fonts", "framing", "transitions", "wording", "logo", "thumbnail", "publish_text", "other_style", "process")
PROCESS_AREA = "process"     # who reviews, approves, checks, receives or publishes the video, and when: never a rule
_ALLOWED = {"caption_size_px": ("up", "down", "value"), "captions_during_hook": ("on", "off", "value"),
            "hook_title_sfx": ("on", "off", "value"), "highlight_colour": ("value",)}


def _parse(knob: str, value, frame_w: int):
    """A knob value through T4.2's own checks (style_knobs raises its ValueError subclass with the reason)."""
    return {"caption_size_px": lambda v: style_knobs._size(v, frame_w),
            "captions_during_hook": style_knobs._hook_mode,
            "hook_title_sfx": style_knobs._bool,
            "highlight_colour": style_knobs._policy}[knob](value)


def _onoff(knob: str, direction: str):
    if knob == "captions_during_hook":
        return "show" if direction == "on" else "hide"
    return direction == "on"


def check_intent(intent) -> dict | None:
    """A clean copy of a label, or Guidance naming what is wrong. An unknown knob name is kept: it goes to notes.md."""
    if intent is None:
        return None
    if not isinstance(intent, dict):
        raise Guidance("an intent label must be a JSON object", 'use {"knob": "caption_size_px", "direction": "up"} '
                       'or {"topic": "glass_only_at_end"}')
    out = {}
    knob, topic = intent.get("knob"), intent.get("topic")
    if (knob is None) == (topic is None):
        raise Guidance("an intent label needs exactly one of `knob` or `topic`",
                       'use {"knob": "<style knob>", "direction": "up|down|on|off|value"} or {"topic": "<key>"}')
    key = knob if knob is not None else topic
    if not isinstance(key, str) or not key.strip() or len(key) > 80:
        raise Guidance(f"intent {'knob' if knob is not None else 'topic'} {key!r} must be a short name",
                       "use a short, stable English key such as \"glass_only_at_end\"")
    direction = intent.get("direction")
    if direction is not None and direction not in DIRECTIONS:
        raise Guidance(f"intent direction {direction!r} is not one of {', '.join(DIRECTIONS)}",
                       "use up, down, on, off or value")
    real = _knob(knob) if knob is not None else None
    if knob is not None:
        out["knob"] = real or knob.strip()
        if real:
            if direction is None:
                raise Guidance(f"intent knob {real!r} needs a direction",
                               f"use one of {', '.join(_ALLOWED[real])}")
            if direction not in _ALLOWED[real]:
                raise Guidance(f"knob {real!r} cannot go {direction!r}", f"use one of {', '.join(_ALLOWED[real])}")
            if direction == "value":
                if "value" not in intent:
                    raise Guidance(f"intent knob {real!r} with direction value needs a `value`",
                                   'add "value", e.g. 72, "show", false or "#FFCC00"')
                try:
                    if real == "caption_size_px":       # the range depends on the frame: checked again by `add`
                        v = intent["value"]
                        if isinstance(v, bool) or not isinstance(v, (int, float)) or not (
                                float(v).is_integer() and 0 < v < 10000):
                            raise ValueError("must be a whole number of pixels")
                        out["value"] = int(v)
                    else:
                        out["value"] = _parse(real, intent["value"], 1080)
                except ValueError as e:
                    raise Guidance(f"intent value {intent['value']!r} for {real}: {e}",
                                   "use a value `reel plan` accepts (client-craft lists them)") from None
    else:
        out["topic"] = topic.strip()
    if not real:                                   # a note for notes.md: it names its area from the closed list
        area = intent.get("area")
        if area not in AREAS:
            raise Guidance(f"intent {'topic' if knob is None else 'knob'} {key!r} needs an `area` from the list "
                           f"({', '.join(AREAS)}), not {area!r}",
                           f'add "area": e.g. "music"; "{PROCESS_AREA}" for who reviews, approves, checks, receives or '
                           "publishes the video and when (never a rule)")
        out["area"] = area
    if direction is not None:
        out["direction"] = direction
    if knob is None and "value" in intent:
        raise Guidance("a topic label has no value", "put the detail in the comment text")
    if "phrase" in intent:
        ph = intent["phrase"]
        if knob is not None or not isinstance(ph, str) or not _PHRASE_ID.fullmatch(ph):
            raise Guidance(f"intent phrase {ph!r} is not a phrase id", "use a topic label with an id from "
                           "`reel rules --phrases` for its area, e.g. {\"topic\": \"music_low\", \"area\": "
                           "\"music\", \"phrase\": \"low_under_speech\"}")
        out["phrase"] = ph
    return out


# ---------------------------------------------------------------------------------------------------- paths
def _profile(root: Path) -> Path:
    return Path(root) / CLIENT_PROFILE_REL


def notes_path(root: Path, video_id: str) -> Path:
    check_project_id(video_id)
    return Path(root) / "output" / "projects" / video_id / NOTES_REL


def _read_doc(path: Path, root: Path, within: str, default):
    """A JSON object file read only when no link sits on the way (linksafe.confine); FileFormatError when damaged."""
    real = linksafe.confine(path, root, within)
    if not real.exists():
        return copy.deepcopy(default)
    from .common import read_json
    data = read_json(real)
    if not isinstance(data, dict):
        raise FileFormatError(path, 1, 1, f"must be a JSON object, it holds {type(data).__name__}")
    return data


def _bytes(doc) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def seal_of(rules: list, dismissed: list | None = None) -> str:
    """sha256 of the canonical rule rows (and, once the editor dismissed a proposal, of the dismissals too): `reel
    rules` stores it in rules.json, and every read checks it, so a row added, removed, changed or re-activated by hand
    is caught (not a secret: it catches edits, it is no signature)."""
    body = {"rules": rules, "dismissed": dismissed} if dismissed else rules
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _registry_bytes(reg: dict) -> bytes:
    out = {k: v for k, v in reg.items() if k != "seal"}
    out["schema"] = SCHEMA
    if not out.get("dismissed"):
        out.pop("dismissed", None)
    out["seal"] = seal_of(out["rules"], out.get("dismissed"))
    return _bytes(out)


TAMPERED_AR = ("ملف قواعد العميل اتغيّر بإيد مش من `reel rules`، فمش هيتقري ولا هيتطبّق منه حاجة لحد ما يتصلّح. "
               "الموافقات والمراجعة والـ QC شغالين زي ما هم.")


def _damaged(path, e) -> Guidance:
    return Guidance(f"{path} cannot be read: {e}", "fix or remove that file by hand (nothing was written)",
                    where=str(path))


# ---------------------------------------------------------------------------------------------------- record
def record(root, video_id: str, items) -> dict:
    """Append the revise round's comments to this video's revision-notes.json. Each item: {"text": "...",
    "intent": {...} (the skill's label), "scope": "standing"|"this_clip" (optional), "source": "comment" (default)}.
    An exact repeat (same text and label) is not stored twice. Refuses the whole batch, writing nothing, on any bad
    item."""
    root = Path(root).expanduser().resolve()
    if isinstance(items, dict):
        items = items.get("comments", items.get("items"))
    if not isinstance(items, list) or not items:
        raise Guidance("no comments to record", 'send a JSON list such as [{"text": "الكابشن صغير", "intent": '
                       '{"knob": "caption_size_px", "direction": "up"}}]')
    clean = []
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            raise Guidance(f"comment {i} is not a JSON object", 'use {"text": "...", "intent": {...}}')
        text = it.get("text")
        if not isinstance(text, str) or not text.strip():
            raise Guidance(f"comment {i} has no text", "send the editor's own words in `text`")
        if len(text) > MAX_TEXT:
            raise Guidance(f"comment {i} is longer than {MAX_TEXT} characters", "send one comment per item")
        scope = it.get("scope")
        if scope is not None and scope not in SCOPES:
            raise Guidance(f"comment {i}: scope {scope!r} is not standing or this_clip",
                           "leave it out, or use \"standing\" (the editor said always/never) or \"this_clip\"")
        source = it.get("source", "comment")
        if source not in SOURCES:
            raise Guidance(f"comment {i}: source {source!r} is not one of {', '.join(SOURCES)}",
                           "leave it out for an editor comment")
        try:
            intent = check_intent(it.get("intent"))
        except Guidance as g:
            raise Guidance(f"comment {i}: {g.error}", g.how) from None
        if intent is None:
            raise Guidance(f"comment {i} has no intent label",
                           'label it by its meaning: {"knob": "caption_size_px", "direction": "up"} for a style knob, '
                           'else {"topic": "<short stable English key>"} (revise skill step 3)')
        e = {"text": text.strip(), "source": source}
        if intent:
            e["intent"] = intent
        if scope:
            e["scope"] = scope
        clean.append(e)
    path = notes_path(root, video_id)
    within = f"output/projects/{video_id}"
    project = linksafe.confine(root / within, root)
    if not project.is_dir():
        raise Guidance(f"there is no video {video_id} in this client (output/projects/{video_id})",
                       "check the --video-id (`reel status` lists the client's videos); nothing was written")
    linksafe.makedirs(path.parent, root, within)
    added, skipped = [], 0
    with file_locked(path):
        try:
            doc = _read_doc(path, root, within, {"schema": SCHEMA, "video_id": video_id, "notes": []})
        except FileFormatError as e:
            raise _damaged(path, e) from None
        notes = doc.setdefault("notes", [])
        if not isinstance(notes, list):
            raise _damaged(path, "`notes` is not a list")
        if notes and doc.get("seal") != seal_of(notes):     # 3b4ec0e P2-1: never seal a hand-added note
            raise Guidance(f"{path} was changed by hand (its seal does not match), so nothing is added to it",
                           "restore the copy `reel rules --record` wrote, or delete the file, then record this round's "
                           "comments again; nothing was written", where=str(path))
        seen = {(norm(n.get("text")), _ikey(n.get("intent")), n.get("scope")) for n in notes if isinstance(n, dict)}
        n_max = max([int(m.group(1)) for n in notes if isinstance(n, dict)
                     for m in [re.fullmatch(r"N(\d+)", str(n.get("id", "")))] if m] or [0])
        at = now_iso()
        for e in clean:
            k = (norm(e["text"]), _ikey(e.get("intent")), e.get("scope"))
            if k in seen:
                skipped += 1
                continue
            seen.add(k)
            n_max += 1
            e = {"id": f"N{n_max}", "at": at, **e}
            notes.append(e)
            added.append(e)
        if added:
            doc["schema"], doc["video_id"] = SCHEMA, video_id
            doc["seal"] = seal_of(notes)                   # 3b4ec0e P2-1: a hand-written note is not counted
            linksafe.replace_atomic(path, root, _bytes(doc), within)
    return {"ok": True, "file": str(path), "added": len(added), "already_recorded": skipped, "total": len(notes),
            "ids": [e["id"] for e in added]}


def _ikey(intent) -> str:
    return json.dumps(intent, sort_keys=True, ensure_ascii=False) if intent else ""


# ---------------------------------------------------------------------------------------------------- history
def history(root) -> tuple[list[dict], list[str]]:
    """Every recorded comment of the client, oldest first: [{video_id, id, at, text, intent, scope, source}], and a
    warning for each notes file that cannot be read (the others are still used)."""
    root = Path(root).expanduser().resolve()
    projects = root / "output" / "projects"
    out, warnings = [], []
    if not projects.is_dir() or linksafe.is_link(projects) or linksafe.is_link(root / "output"):
        return out, warnings
    for d in sorted(projects.iterdir(), key=lambda p: p.name):
        try:
            check_project_id(d.name)
        except (Guidance, ValueError, SystemExit):
            continue
        f = d / NOTES_REL
        if not f.exists() and not linksafe.is_link(f):
            continue
        try:
            doc = _read_doc(f, root, f"output/projects/{d.name}", {"notes": []})
        except (FileFormatError, Guidance, OSError) as e:
            warnings.append(f"{f}: {getattr(e, 'error', e)}: its comments are not counted")
            continue
        notes = doc.get("notes")
        if not isinstance(notes, list):
            warnings.append(f"{f}: `notes` is not a list: its comments are not counted")
            continue
        if doc.get("seal") != seal_of(notes):
            warnings.append(f"{f}: not written by `reel rules --record` (its seal does not match): its comments are "
                            "not counted (restore the copy `reel rules` wrote, or delete the file and record the "
                            "comments again)")
            continue
        for n in notes:
            if not isinstance(n, dict) or not isinstance(n.get("text"), str) or not n["text"].strip():
                warnings.append(f"{f}: an entry without text is skipped")
                continue
            try:
                intent = check_intent(n.get("intent"))
            except Guidance as g:
                warnings.append(f"{f} {n.get('id', '?')}: {g.error}: this comment is not counted (relabel it with "
                                "`reel rules --record`)")
                continue
            if intent is None:                    # S1-T4.3 ruling: only the skill's labelled comments ever count
                warnings.append(f"{f} {n.get('id', '?')}: no intent label: this comment is not counted (relabel it "
                                "with `reel rules --record`)")
                continue
            out.append({"video_id": d.name, "id": n.get("id"), "at": str(n.get("at") or ""), "text": n["text"],
                        "intent": intent, "scope": n.get("scope") if n.get("scope") in SCOPES else None,
                        "source": n.get("source") if n.get("source") in SOURCES else "comment"})
    out.sort(key=lambda n: (n["at"], n["video_id"], _num(n["id"])))
    return out, warnings


def _num(nid) -> tuple:
    m = re.fullmatch(r"[A-Z](\d+)", str(nid or ""))
    return (0, int(m.group(1)), "") if m else (1, 0, str(nid))


# ---------------------------------------------------------------------------------------------------- grouping
def _label(n: dict) -> tuple[dict | None, str]:
    """(label, how): the skill's label. history() never returns an unlabelled comment (S1-T4.3 ruling)."""
    return (n.get("intent") or None), "label"


def _target(label: dict | None, text: str) -> tuple[str, str, object]:
    """(subject, polarity, value). subject: what the rule is about ("knob:caption_size_px", "topic:x", "text:...");
    polarity: the direction it sets (two comments on one subject with different polarities conflict). With no
    direction given (an old comment's words, a topic without one) it is read from the words: "off" when they say
    never / don't / «مش» / «بلاش», else "on" — so "always put music" and "never put music" are a conflict."""
    if label is None:
        return f"text:{_core(text)}", _text_polarity(text), None
    if "knob" in label and _knob(label["knob"]):
        k, d = _knob(label["knob"]), label.get("direction")
        if d in ("on", "off"):
            v = _onoff(k, d)
            return f"knob:{k}", json.dumps(v), v
        if d == "value":
            v = label["value"]
            if k == "caption_size_px":
                return f"knob:{k}", "value", v            # resolved to up / down against the current size later
            return f"knob:{k}", json.dumps(v), v
        return f"knob:{k}", d, None
    if "knob" in label:
        return f"other:{label['knob']}", label.get("direction") or "", None
    return f"topic:{label['topic']}", label.get("direction") or "", None


_OFF = re.compile(r"(?<![\w'])(?:never|don't|dont|do not|no|not|no more|no longer|stop|avoid|without|ابدا|[وف]?مش|"
                  r"بلاش|من غير|بدون|دون|[وف]?لا|[وف]?ما)(?![\w'])|\w+n't(?![\w'])|(?<!\w)[وف]?م\w{2,}ش(?!\w)")
_FILLER = re.compile(r"(?<![\w'])(?:always|never|please|every time|from now on|don't|dont|do not|no|not|دايما|دائما|"
                     r"ابدا|مش|بلاش|ما|لا|على طول|علي طول|بعد كده|كل مره|من فضلك|لو سمحت)(?![\w'])")


def _text_polarity(text: str) -> str:
    return "off" if _OFF.search(norm(text).replace("never mind", " ")) else "on"


def _core(text: str) -> str:
    """The words of a comment without its always / never / please words: what it is about."""
    return " ".join(_FILLER.sub(" ", norm(text)).split()) or norm(text)


def _gid(subject: str, polarity: str) -> str:
    return "P-" + hashlib.sha1(f"{subject}|{polarity}".encode("utf-8")).hexdigest()[:8]


class _State:
    """What `propose` / `add` need: the client root, its rules registry and the current knob values."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.prof = _profile(self.root)
        self._ctx = None

    @property
    def ctx(self):
        if self._ctx is None:
            from .common import Context
            self._ctx = Context(self.root)
        return self._ctx

    def registry(self) -> dict:
        """rules.json as `reel rules` wrote it, checked on every read, never trusted as found: the schema, the seal
        over the rule rows, and each knob rule's knob and value through the T4.2 allowlist parsers. Anything else is
        refused with one plain line (nothing is shown as a rule or applied from it). No file = no rules."""
        p = self.prof / RULES_FILE
        try:
            doc = _read_doc(p, self.root, CLIENT_PROFILE_REL, None)
        except FileFormatError as e:
            raise _damaged(p, e) from None
        if doc is None:
            return {"schema": SCHEMA, "rules": []}
        problem = self._problem(doc)
        if problem:
            raise Guidance(f"{p}: the client rules file was not written by `reel rules` ({problem}), so no rule is "
                           f"read from it. {TAMPERED_AR}",
                           f"put back the copy `reel rules` wrote, or delete {RULES_FILE} (the rules start over; the "
                           "values already in style.json stay), then run `reel rules --list`; nothing was written",
                           where=str(p))
        return doc

    def _problem(self, doc) -> str | None:
        rules = doc.get("rules")
        if doc.get("schema") != SCHEMA or not isinstance(rules, list):
            return "unknown layout"
        dismissed = doc.get("dismissed")
        if dismissed is not None and (not isinstance(dismissed, list) or not all(
                isinstance(d, dict) and isinstance(d.get("proposal"), str) and isinstance(d.get("from"), list)
                for d in dismissed)):
            return "its dismissed list is not one `reel rules` writes"
        if doc.get("seal") != seal_of(rules, dismissed):
            return "its seal does not match its rules" if "seal" in doc else "it has no seal"
        for r in rules:
            if not isinstance(r, dict) or r.get("status") not in ("active", "replaced", "removed") \
                    or not re.fullmatch(r"R\d+", str(r.get("id"))) \
                    or any(r.get(k) is not None and not re.fullmatch(r"\d{4}-\d\d-\d\d", str(r.get(k)))
                           for k in ("added", "replaced", "removed")) \
                    or (r.get("area") is not None and r.get("area") not in AREAS):
                return "a rule row is not one `reel rules` writes"
            knob = r.get("knob")
            if knob is None:
                continue
            if knob not in _ALLOWED:
                return f"rule {r['id']} names {knob!r}, which is not a style knob"
            try:
                _parse(knob, r.get("value"), self.frame_w())
            except ValueError as e:
                return f"rule {r['id']}: {knob} {r.get('value')!r} {e}"
        return None

    def frame_w(self) -> int:
        try:
            return int(frame_size_of(self.ctx.config("sequence-settings.json"))[0] or 1080)
        except (Guidance, ValueError, TypeError):
            return 1080

    def current_size(self) -> int:
        """The caption size today: the highest style.json layer that sets it, else the caption template's size."""
        for _label_, data in reversed(style_knobs.layers(self.ctx)):
            if isinstance(data, dict):
                here, v = style_knobs._value(data, "caption_size_px")
                if here:
                    try:
                        return style_knobs._size(v, self.frame_w())
                    except ValueError:
                        break
        tpl = ((self.ctx.config("graphics-templates.json").get("templates") or {}).get("highlight_caption") or {})
        return int(tpl.get("size") or 62)


def _size_value(state: _State, direction: str, explicit: list) -> tuple[int | None, str | None]:
    """The caption size a "bigger"/"smaller" rule sets: the newest number the editor gave, else the current size x
    or / 1.15, inside T4.2's range. (value, why-not) — None when it cannot move further."""
    lo, hi = style_knobs.size_range(state.frame_w())
    cur = state.current_size()
    if explicit:
        return explicit[-1], None
    v = int(round(cur * STEP)) if direction == "up" else int(round(cur / STEP))
    v = max(lo, min(hi, v))
    if v == cur:
        return None, (f"the captions are already at the {'largest' if direction == 'up' else 'smallest'} size "
                      f"T4.2 allows ({cur} px)")
    return v, None


def _summary(rule: dict) -> tuple[str, str]:
    """(Arabic, English) line for one rule or proposal."""
    k, v = rule.get("knob"), rule.get("value")
    if k == "caption_size_px":
        return f"الكابشن بحجم {v} بكسل", f"captions at {v} px"
    if k == "captions_during_hook":
        return (("الكابشن يفضل ظاهر تحت عنوان الهوك", "captions stay on under the hook title") if v == "show" else
                ("الكابشن يختفي تحت عنوان الهوك", "captions hidden under the hook title"))
    if k == "hook_title_sfx":
        return (("صوت على عنوان الهوك", "a sound on the hook title") if v else
                ("من غير صوت على عنوان الهوك", "no sound on the hook title"))
    if k == "highlight_colour":
        return f"لون التمييز {v}", f"highlight colour {v}"
    ph = phrase_of({"area": rule.get("area"), "phrase": rule.get("phrase")})
    if ph:
        item = phrases()[ph[0]][ph[1]]
        return item["ar"], item["en"]
    return "(مش متطبّقة)", "(not shown)"


def _relation(r: dict, subject: str, polarity: str, knob, value, tone: str = "") -> str | None:
    """How an active rule stands to a proposal: None (another subject), "same" or "conflict". A knob holds one
    value, so two values of one knob always conflict; a topic conflicts on opposite directions, or, when neither
    gave one, when the words point the other way ("always glass at the end" vs "never use glass"): shown to the
    editor, who picks."""
    if r.get("subject") != subject:
        return None
    if knob:
        return "same" if r.get("value") == value else "conflict"
    if r.get("polarity") and polarity:
        return "conflict" if r.get("polarity") != polarity else "same"
    if not r.get("polarity") and not polarity and tone and r.get("tone") and r["tone"] != tone:
        return "conflict"
    return "same"


def _find(active: list, rel: str, subject: str, polarity: str, knob, value, tone: str = "") -> dict | None:
    return next((r for r in active if _relation(r, subject, polarity, knob, value, tone) == rel), None)


def _used(rules: list) -> set:
    """The comments every rule was made from (active, replaced or removed): never proposed again."""
    return {(v, n) for r in rules if isinstance(r, dict) for v, n in (tuple(x) for x in r.get("from", [])
                                                                       if isinstance(x, list) and len(x) == 2)}


def propose(root) -> dict:
    """The proposals for the editor: recurring or standing comments grouped by meaning, with conflicts, refusals and
    the active rules. Writes nothing."""
    st = _State(root)
    notes, warnings = history(st.root)
    reg = st.registry()
    active = [r for r in reg["rules"] if isinstance(r, dict) and r.get("status") == "active"]
    used = _used(reg["rules"])
    dismissed: dict = {}                                # by subject (an older entry without one: by proposal id)
    for d in reg.get("dismissed") or []:
        dismissed.setdefault(d.get("subject") or d["proposal"], set()).update(
            tuple(x) for x in d["from"] if isinstance(x, list) and len(x) == 2)
    groups: dict = {}
    refused = []
    hand: dict = {}                                     # free-text wishes: listed, never a proposal
    live = [n for n in notes if not (n["scope"] == "this_clip" or this_clip_only(n["text"])
                                     or (n["video_id"], n["id"]) in used)]
    bad = {norm(n["text"]) for n in live if weakens_safety(n["text"], _label(n)[0])}
    for n in live:
        label, how = _label(n)
        if norm(n["text"]) in bad:                         # refused once = refused on every video, however labelled
            refused.append({"video_id": n["video_id"], "note": n["id"], "text": n["text"], "ar": REFUSED_AR,
                            "en": REFUSED_EN})
            continue
        if _notes_only(label):
            ph = phrase_of(label)
            if ph is None:                                 # free text: never a rule (option A)
                key = (label or {}).get("topic") or (label or {}).get("knob") or _core(n["text"])
                h = hand.setdefault(key, {"topic": key, "area": (label or {}).get("area"), "videos": [],
                                          "standing": False, "text": n["text"]})
                if n["video_id"] not in h["videos"]:
                    h["videos"].append(n["video_id"])
                h["standing"] = h["standing"] or n["scope"] == "standing" or standing_word(n["text"])
                h["text"] = n["text"]
                continue
            area, pid = ph
            subject, polarity, value = f"phrase:{area}.{phrases()[area][pid]['group']}", pid, pid
        else:
            subject, polarity, value = _target(label, n["text"])
        if subject == "knob:caption_size_px" and polarity == "value":
            cur = st.current_size()
            if value == cur:
                continue
            polarity = "up" if value > cur else "down"
        g = groups.setdefault((subject, polarity), {"subject": subject, "polarity": polarity, "value": value,
                                                    "label": label, "how": set(), "comments": [], "videos": [],
                                                    "standing": False, "explicit": []})
        g["how"].add(how)
        g["comments"].append({"video_id": n["video_id"], "note": n["id"], "text": n["text"], "source": n["source"]})
        if n["video_id"] not in g["videos"]:
            g["videos"].append(n["video_id"])
        if n["scope"] == "standing" or standing_word(n["text"]):
            g["standing"] = True
        if subject == "knob:caption_size_px" and label and label.get("direction") == "value":
            g["explicit"].append(label["value"])
        if label is not None and value is not None:
            g["value"] = value                            # the newest wording of the same value
    proposals = []
    for (subject, polarity), g in groups.items():
        qualifies = g["standing"] or len(g["videos"]) >= 2
        knob = subject.split(":", 1)[1] if subject.startswith("knob:") else None
        value, why_not = g["value"], None
        if knob == "caption_size_px":
            value, why_not = _size_value(st, polarity, g["explicit"])
        p = {"id": _gid(subject, polarity), "subject": subject, "polarity": polarity, "knob": knob, "value": value,
             "area": (g["label"] or {}).get("area"),
             "phrase": value if subject.startswith("phrase:") else None,
             "target": "style.json + notes.md" if knob else "notes.md",
             "text": g["comments"][-1]["text"], "videos": g["videos"], "comments": g["comments"],
             "why": ("standing word" if g["standing"] else f"said on {len(g['videos'])} videos"),
             "read_by": sorted(g["how"]), "qualifies": qualifies,
             "tone": _text_polarity(g["comments"][-1]["text"])}
        if why_not:
            p["qualifies"], p["not_actionable"] = False, why_not
        p["ar"], p["en"] = _summary(p)
        if _find(active, "same", subject, polarity, knob, value, p["tone"]):
            continue                                       # already a rule
        said_no = (dismissed.get(subject) or set()) | (dismissed.get(p["id"]) or set())
        if said_no is not None and {(c["video_id"], c["note"]) for c in p["comments"]} <= said_no:
            continue                                       # the editor said no; a NEW comment brings it back
        clash = _find(active, "conflict", subject, polarity, knob, value, p["tone"])
        if clash:
            p["conflicts_with_rule"] = clash["id"]
        proposals.append(p)
    conflicts = []
    by_subject: dict = {}
    for p in proposals:
        if p["polarity"]:
            by_subject.setdefault(p["subject"], []).append(p)
    for subject, ps in by_subject.items():
        ps = [p for p in ps if not p.get("not_actionable")]
        if len({p["polarity"] for p in ps}) < 2:
            continue
        videos = {v for p in ps for v in p["videos"]}
        if not (any(p["qualifies"] for p in ps) or len(videos) >= 2):
            continue                                       # two one-off comments that happen to disagree
        for p in ps:
            p["conflicts_with"] = [q["id"] for q in ps if q is not p]
            p["qualifies"] = True                          # shown as a choice, never as a rule on its own
        conflicts.append({"subject": subject, "proposals": [p["id"] for p in ps],
                          "ar": "التعليقات دي متعارضة: المحرر يختار واحدة (أو ولا واحدة)",
                          "en": "these comments disagree: the editor picks one (or neither)"})
    out_props = sorted([p for p in proposals if p["qualifies"]], key=lambda p: p["id"])
    by_hand = [{"topic": h["topic"], "area": h["area"], "videos": h["videos"], "text": h["text"],
                "ar": BY_HAND_AR.format(n=len(h["videos"])), "en": BY_HAND_EN.format(n=len(h["videos"]))}
               for h in hand.values() if h["standing"] or len(h["videos"]) >= 2]
    rules = [_public(r) for r in active]
    return {"ok": True, "proposals": out_props, "conflicts": conflicts, "refused": refused, "by_hand": by_hand,
            "active": rules,
            "summary": [{"id": r["id"], "ar": r["ar"], "en": r["en"]} for r in rules] +
                       [{"id": p["id"], "ar": "مقترح: " + p["ar"], "en": "proposed: " + p["en"]} for p in out_props],
            "warnings": warnings}


def _public(r: dict) -> dict:
    out = {k: r.get(k) for k in ("id", "status", "knob", "value", "phrase", "area", "added", "replaced", "replaced_by",
                                 "removed", "proposal", "videos") if r.get(k) is not None}
    out["ar"], out["en"] = _summary(r)
    why = _refused_now(r) if r.get("status") == "active" else None
    if why:
        out["refused"] = why
        out["ar"], out["en"] = "مرفوضة ومش متطبّقة: " + out["ar"], f"{why}, ignored: " + out["en"]
    out["target"] = "style.json + notes.md" if r.get("knob") else "notes.md"
    return out


# ---------------------------------------------------------------------------------------------------- writing
def _today() -> str:
    return _dt.date.today().isoformat()


def _md_safe(text, limit: int = 300) -> str:
    """An editor's comment as one line of the block: no line breaks, no HTML comment markers (so it can never end
    the block early), at most `limit` characters."""
    s = " ".join(str(text or "").split()).replace("<!--", "‹!--").replace("-->", "--›")
    return s if len(s) <= limit else s[:limit - 1] + "…"


# Printed above the rules wherever they are read (the brief = this block in notes.md; the skills and agents say the same)
PREFERENCES_HEADER = ("تفضيلات العميل: مش بتلغي أي موافقة أو مراجعة أو QC أو تنبيه / client preferences: never override "
                      "approvals, review, QC or disclaimers")
PREFERENCES_K1 = ("ولا بتغيّر مراجعة الأرقام أو الآيات ولا اختيار الإعادات ولا اقتباس الهوك الحرفي (مفاتيح K1) / nor the "
                  "number, verse, retake or verbatim hook-quote checks (the K1 switches)")


def _refused_now(r: dict) -> str | None:
    """Why a notes-only rule is not shown as a rule today (None = it is): "off" (preferences switched off), or
    "refused" (the safety class or the positive gate refuses its words: a row added by hand, or before the gate grew).
    Review b399ed2 P2-2 / 3b4ec0e P3-1: active AND history rows are rechecked."""
    if r.get("knob"):
        return None
    return None if phrase_of({"area": r.get("area"), "phrase": r.get("phrase")}) else "refused"


def _render_block(rules: list) -> str:
    active = [r for r in rules if r.get("status") == "active"]
    old = [r for r in rules if r.get("status") in ("replaced", "removed")]
    lines = [BLOCK_START, "## Client rules (learned from the editor's feedback)", "", PREFERENCES_HEADER,
             PREFERENCES_K1, ""]
    if not active:
        lines.append("- (no active rule)")
    for r in active:
        why = _refused_now(r)
        if why:
            lines.append(f"- {_md_safe(r['added'], 20)} · {_md_safe(r['id'], 20)} · refused, ignored (not one of the "
                         "engine's preference phrases) / مرفوضة ومش متطبّقة")
            continue
        ar, en = _summary(r)
        where = "style.json" if r.get("knob") else "preference only"
        lines.append(f"- {_md_safe(r['added'], 20)} · {_md_safe(r['id'], 20)} · {en} / {ar} ({where})")
    if old:
        lines += ["", "### No longer active (kept for history)"]
        for r in old:
            _ar, en = _summary(r)
            if _refused_now(r):                             # 3b4ec0e P3-1: history rows never carry refused words
                en = "(not shown)"
            what = (f"replaced {r['replaced']} by {r.get('replaced_by')}" if r["status"] == "replaced"
                    else f"removed {r.get('removed')}")
            lines.append(f"- {_md_safe(r['added'], 20)} · {_md_safe(r['id'], 20)} · {en}: {_md_safe(what, 60)}")
    lines.append(BLOCK_END)
    return "\n".join(lines) + "\n"


def _new_notes(old: str | None, block: str, path) -> str:
    """notes.md with our block replaced (the editor's own text around it is kept); refuses broken markers."""
    if old is None or not old.strip():
        return "# Client notes\n\n" + block
    starts = old.count(_MARK_START)
    ends = old.count(BLOCK_END)
    if starts == 0 and ends == 0:
        return old.rstrip("\n") + "\n\n" + block
    if starts != 1 or ends != 1 or old.index(_MARK_START) > old.index(BLOCK_END):
        raise Guidance(f"{path}: the client-rules block markers were changed by hand ({starts} start, {ends} end)",
                       f"put back exactly one `{BLOCK_START}` line and one `{BLOCK_END}` line around the rules "
                       "(or delete both and the lines between them), then run the command again; nothing was written",
                       where=str(path))
    a = old.index(_MARK_START)
    b = old.index(BLOCK_END) + len(BLOCK_END)
    tail = old[b:]
    if tail.startswith("\r\n"):
        tail = tail[2:]
    elif tail.startswith("\n"):
        tail = tail[1:]
    return old[:a] + block + tail


def _read_text(path: Path, root: Path) -> str | None:
    real = linksafe.confine(path, root, CLIENT_PROFILE_REL)
    if not real.exists():
        return None
    try:
        return real.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Guidance(f"{path} is not UTF-8 text", "save it as UTF-8, then run the command again; nothing was "
                       "written", where=str(path)) from None


def _style_doc(st: _State) -> dict:
    p = st.prof / "style.json"
    try:
        return _read_doc(p, st.root, CLIENT_PROFILE_REL, {})
    except FileFormatError as e:
        raise _damaged(p, e) from None


def _commit(st: _State, writes: list[tuple[Path, bytes | None]]):
    """Write every file, or none: the old bytes are put back if a later write fails. bytes None = remove the key file
    (never used for notes.md)."""
    linksafe.makedirs(st.prof, st.root, CLIENT_PROFILE_REL)
    before = []
    for path, _data in writes:
        real = linksafe.confine(path, st.root, CLIENT_PROFILE_REL)
        before.append((path, real.read_bytes() if real.exists() else None))
    done = []
    try:
        for path, data in writes:
            linksafe.replace_atomic(path, st.root, data, CLIENT_PROFILE_REL)
            done.append(path)
    except BaseException:
        for path, old in before:
            if path not in done:
                continue
            if old is None:
                linksafe.remove(path, st.root, CLIENT_PROFILE_REL)
            else:
                linksafe.replace_atomic(path, st.root, old, CLIENT_PROFILE_REL)
        raise


def add(root, proposal_id: str, value=None, replace: str | None = None) -> dict:
    """The editor confirmed proposal `proposal_id`: write it as an active rule (rules.json), a dated entry in
    notes.md and, for a T4.2 knob, the knob in style.json. A rule it contradicts must be named with `replace` (that
    rule is kept as `replaced <date>`). Running it again changes nothing."""
    st = _State(root)
    rules_path = st.prof / RULES_FILE
    linksafe.makedirs(st.prof, st.root, CLIENT_PROFILE_REL)
    with file_locked(rules_path):
        reg = st.registry()
        props = propose(st.root)
        p = next((x for x in props["proposals"] if x["id"] == proposal_id), None)
        active = [r for r in reg["rules"] if isinstance(r, dict) and r.get("status") == "active"]
        if p is None:
            done = next((r for r in active if r.get("proposal") == proposal_id), None)
            if done is not None and value is None and replace is None:
                return {"ok": True, "unchanged": True, "rule": _public(done),
                        "note": f"already a rule since {done['added']}: nothing written"}
            raise Guidance(f"no proposal {proposal_id!r} (or it is not ready to become a rule)",
                           "run `reel rules --propose` and use an id it lists; nothing was written")
        knob = p["knob"]
        if knob is None and value is not None:
            raise Guidance(f"{proposal_id} is a note, not a style knob, so it takes no --value",
                           "run it without --value; nothing was written")
        if knob:
            v = p["value"] if value is None else value
            if v is None:
                raise Guidance(f"{proposal_id}: {p.get('not_actionable') or 'no value'}",
                               "give the value with --value, or leave the rule; nothing was written")
            try:
                v = _parse(knob, v, st.frame_w())
            except ValueError as e:
                raise Guidance(f"{knob} {v!r} {e}", "give a value `reel plan` accepts; nothing was written") from None
        else:
            v = None
        polarity = p["polarity"]
        if knob == "caption_size_px" and value is not None:
            cur = st.current_size()
            polarity = "up" if v > cur else "down" if v < cur else polarity
        elif knob and value is not None:
            polarity = json.dumps(v)                       # the value the editor chose sets the direction
        clash = _find(active, "conflict", p["subject"], polarity, knob, v, p["tone"])
        same = _find(active, "same", p["subject"], polarity, knob, v, p["tone"])
        if same is not None:
            return {"ok": True, "unchanged": True, "rule": _public(same),
                    "note": f"already a rule since {same['added']}: nothing written"}
        if clash is not None and replace != clash["id"]:
            ar, en = _summary(clash)
            raise Guidance(f"{proposal_id} contradicts the active rule {clash['id']} ({en})",
                           f"show both to the editor; if they pick the new one, run `reel rules --add {proposal_id} "
                           f"--replace {clash['id']}`; nothing was written")
        if replace is not None and (clash is None or replace != clash["id"]):
            raise Guidance(f"--replace {replace}: {proposal_id} does not contradict that rule",
                           "leave --replace out; nothing was written")
        today = _today()
        n = max([int(m.group(1)) for r in reg["rules"] if isinstance(r, dict)
                 for m in [re.fullmatch(r"R(\d+)", str(r.get("id", "")))] if m] or [0]) + 1
        rule = {"id": f"R{n}", "status": "active", "added": today, "proposal": proposal_id, "subject": p["subject"],
                "polarity": polarity, "knob": knob, "value": v, "phrase": p.get("phrase"), "videos": p["videos"],
                "from": [[c["video_id"], c["note"]] for c in p["comments"]], "tone": p["tone"], "area": p.get("area"),
                "source": sorted({c["source"] for c in p["comments"]})}
        note = ""
        if knob:
            style = dict(_style_doc(st))
            if clash is not None and clash.get("knob") == knob:
                if "prev" in clash:                        # the value before the first rule on this knob
                    rule["prev"] = clash["prev"]
            else:
                here, before = style_knobs._value(style, knob)
                if here:
                    rule["prev"] = before
                    if before != v:
                        note = (f"style.json had {knob} {before!r} (set by hand): it is kept in the rule and put back "
                                "if the rule is removed")
        new_reg = copy.deepcopy(reg)
        new_reg["schema"] = SCHEMA
        if clash is not None:
            for r in new_reg["rules"]:
                if isinstance(r, dict) and r.get("id") == clash["id"]:
                    r.update(status="replaced", replaced=today, replaced_by=rule["id"])
        new_reg["rules"].append(rule)
        writes = []
        if knob:
            for alias, real in style_knobs.ALIASES.items():
                if real == knob:
                    style.pop(alias, None)
            style[knob] = v
            writes.append((st.prof / "style.json", _bytes(style)))
        md_path = st.prof / NOTES_MD
        writes.append((md_path, _new_notes(_read_text(md_path, st.root), _render_block(new_reg["rules"]),
                                           md_path).encode("utf-8")))
        writes.append((rules_path, _registry_bytes(new_reg)))
        _commit(st, writes)
    return {"ok": True, "rule": _public(rule), "replaced": clash["id"] if clash else None, "note": note,
            "files": [str(w[0]) for w in writes],
            "next": "run `reel plan` again: builds follow the compiled plan" if knob else
                    "the story-editor reads it in notes.md from the next edit"}


def list_rules(root) -> dict:
    st = _State(root)
    reg = st.registry()
    rules = [r for r in reg["rules"] if isinstance(r, dict)]
    return {"ok": True, "active": [_public(r) for r in rules if r.get("status") == "active"],
            "history": [_public(r) for r in rules if r.get("status") != "active"]}


def dismiss(root, proposal_id: str) -> dict:
    """The editor said no to proposal `proposal_id`: remember that (rules.json `dismissed`: the proposal, the comments
    it covered, the date), so it is not shown again at every edit. It comes back only when a new comment joins it.
    Nothing else changes; the lead runs it (the guard)."""
    st = _State(root)
    rules_path = st.prof / RULES_FILE
    linksafe.makedirs(st.prof, st.root, CLIENT_PROFILE_REL)
    with file_locked(rules_path):
        reg = st.registry()
        p = next((x for x in propose(st.root)["proposals"] if x["id"] == proposal_id), None)
        if p is None:
            raise Guidance(f"no open proposal {proposal_id!r}",
                           "run `reel rules --propose` and use an id it lists; nothing was written")
        new_reg = copy.deepcopy(reg)
        new_reg.setdefault("dismissed", []).append(
            {"proposal": proposal_id, "subject": p["subject"],
             "from": [[c["video_id"], c["note"]] for c in p["comments"]], "date": _today()})
        _commit(st, [(rules_path, _registry_bytes(new_reg))])
    return {"ok": True, "dismissed": proposal_id, "comments": len(p["comments"]),
            "next": "it is not proposed again unless the editor says it on another video"}


def remove(root, rule_id: str) -> dict:
    """The editor dropped rule `rule_id`: it is kept as `removed <date>`, and its knob leaves style.json when the
    file still holds the value the rule wrote (a value changed by hand is kept, with a warning)."""
    st = _State(root)
    rules_path = st.prof / RULES_FILE
    with file_locked(rules_path):
        reg = st.registry()
        rule = next((r for r in reg["rules"] if isinstance(r, dict) and r.get("id") == rule_id), None)
        if rule is None or rule.get("status") != "active":
            what = "no rule" if rule is None else f"rule {rule_id} is already {rule.get('status')}"
            raise Guidance(f"{what} {rule_id!r}" if rule is None else what,
                           "run `reel rules --list` and use an active rule's id; nothing was written")
        today = _today()
        new_reg = copy.deepcopy(reg)
        for r in new_reg["rules"]:
            if isinstance(r, dict) and r.get("id") == rule_id:
                r.update(status="removed", removed=today)
        writes, warnings = [], []
        knob = rule.get("knob")
        if knob:
            style = dict(_style_doc(st))
            here, cur = style_knobs._value(style, knob)
            if here and cur == rule.get("value"):
                for alias, real in style_knobs.ALIASES.items():
                    if real == knob:
                        style.pop(alias, None)
                if "prev" in rule:
                    style[knob] = rule["prev"]             # the editor's own value from before the rule
                else:
                    style.pop(knob, None)
                writes.append((st.prof / "style.json", _bytes(style)))
            elif here:
                warnings.append(f"style.json {knob} is {cur!r} now, not the rule's {rule.get('value')!r} (changed by "
                                "hand): it is kept")
        md_path = st.prof / NOTES_MD
        writes.append((md_path, _new_notes(_read_text(md_path, st.root), _render_block(new_reg["rules"]),
                                           md_path).encode("utf-8")))
        writes.append((rules_path, _registry_bytes(new_reg)))
        _commit(st, writes)
    return {"ok": True, "removed": rule_id, "warnings": warnings,
            "next": "run `reel plan` again: builds follow the compiled plan" if knob else
                    "the story-editor no longer reads it in notes.md"}


# ---------------------------------------------------------------------------------------------------- the plan side
def applied(root, spec: dict | None) -> list[dict]:
    """The client rules behind a compiled plan, for `reel plan`'s report: each active knob rule with `applied` true
    when the timeline-spec carries its value from the client's style.json ("reel" when this reel's edit-decisions
    override it), and each notes-only rule as "in the brief" (the story-editor reads notes.md). [] without rules."""
    st = _State(root)
    try:
        rules = st.registry()["rules"]
    except (Guidance, FileFormatError):
        return [{"id": "?", "applied": False, "ar": "ملف قواعد العميل مش مقروء", "en": "the client rules file "
                 f"({CLIENT_PROFILE_REL}/{RULES_FILE}) cannot be read: no rule is shown as applied"}]
    style = (spec or {}).get("style") or {}
    sources = style.get("sources") or {}
    out = []
    for r in rules:
        if not isinstance(r, dict) or r.get("status") != "active":
            continue
        ar, en = _summary(r)
        e = {"id": r["id"], "ar": ar, "en": en}
        k, v = r.get("knob"), r.get("value")
        if not k:
            e["applied"] = _refused_now(r) or "brief"
        elif sources.get(k) == "reel":
            e["applied"] = "overridden by this reel"
        elif k == "caption_size_px":
            tpl = ((st.ctx.config("graphics-templates.json").get("templates") or {}).get("highlight_caption") or {})
            e["applied"] = style.get(k) == v or (k not in style and v == tpl.get("size"))
        elif k == "captions_during_hook":
            if v == "show":
                from .common import CAPTION_HIDE_SAFE
                hide = st.ctx.config("style.json").get("captions_hidden_during") or CAPTION_HIDE_SAFE
                e["applied"] = style.get(k) == "show" or "hook_title" not in hide
            else:
                e["applied"] = style.get(k) != "show"
        elif k == "hook_title_sfx":
            e["applied"] = (style.get(k) is False) == (v is False)
        elif k == "highlight_colour":
            hl = style.get("highlight") or {}
            e["applied"] = (hl.get("policy", "brand") == v) and ("adjusted for contrast" if hl.get("adjusted") else True)
        out.append(e)
    return out
