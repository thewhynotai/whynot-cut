# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The medical lexicon K-T1 ranks drug and product names with: the shipped list (data/, licence-checked per K0.5) plus
the client's own glossary (reel-profile/medical-glossary.json, merged over config/defaults).

A source whose licence is not on the allow-list, whose licence names non-commercial, AGPL, UMLS or "unknown" terms, or
whose file no longer matches its pinned sha256 is refused: its terms are not loaded and the refusal says why. There is
no "use it for now" path."""
import hashlib
import json
import re
from pathlib import Path

from .numbers import fold

DATA = Path(__file__).resolve().parent / "data"
MANIFEST = DATA / "lexicon-sources.json"
# licences that allow commercial redistribution inside a GPL-3.0-or-later product (K0.5)
ALLOWED = {"gpl-3.0-or-later", "gpl-3.0-only", "gpl-3.0", "mit", "bsd-2-clause", "bsd-3-clause", "apache-2.0", "isc",
           "cc0-1.0", "cc-by-4.0", "cc-by-sa-4.0", "unlicense", "public-domain", "zlib"}
_DENY = re.compile(r"(^|[-_ ])nc([-_ ]|$)|non.?commercial|agpl|umls|proprietary|unknown|paid", re.I)


def licence_ok(licence) -> tuple:
    """(ok, reason). Only an allow-listed SPDX id passes; anything else is refused with the reason."""
    lic = str(licence or "").strip()
    if not lic:
        return False, "no licence recorded"
    if _DENY.search(lic):
        return False, f"licence {lic} does not allow commercial redistribution (K0.5)"
    if lic.lower() not in ALLOWED:
        return False, f"licence {lic} is not on the allow-list of K0.5"
    return True, ""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_sources(manifest: Path = MANIFEST) -> dict:
    """{"terms": [folded terms], "groups": [[folded spellings of one medicine]], "used": [source ids],
    "refused": [{"id", "reason", "reason_ar"}]}. Never raises (G10): a damaged manifest means no shipped terms and one
    refusal naming the file."""
    used, refused, groups = [], [], []
    try:
        doc = json.loads(Path(manifest).read_text(encoding="utf-8-sig"))
        sources = doc["sources"]
        if not isinstance(sources, list):
            raise TypeError("sources is not a list")
    except Exception as e:  # noqa: BLE001
        return {"terms": [], "groups": [], "used": [],
                "refused": [_refusal(str(manifest), f"unreadable: {type(e).__name__}")]}
    for s in sources:
        sid = str((s or {}).get("id") or "?") if isinstance(s, dict) else "?"
        if not isinstance(s, dict):
            refused.append(_refusal(sid, "not a source record"))
            continue
        ok, why = licence_ok(s.get("licence"))
        if ok and s.get("commercial_redistribution") is not True:
            ok, why = False, "commercial redistribution not confirmed"
        f = Path(manifest).parent / str(s.get("file") or "")
        if ok and (not s.get("file") or not f.is_file()):
            ok, why = False, f"file {s.get('file')} missing"
        if ok and _sha(f) != str(s.get("sha256") or ""):
            ok, why = False, f"file {s.get('file')} does not match its pinned sha256"
        if ok:
            try:
                got = _groups_of(json.loads(f.read_text(encoding="utf-8-sig")))
            except Exception as e:  # noqa: BLE001
                ok, why = False, f"file {s.get('file')} unreadable: {type(e).__name__}"
        if not ok:
            refused.append(_refusal(sid, why))
            continue
        used.append(sid)
        groups += got
    groups = [g for g in (_folded(g) for g in groups) if g]
    return {"terms": _folded([t for g in groups for t in g]), "groups": groups, "used": used, "refused": refused}


def _refusal(sid: str, why: str) -> dict:
    return {"id": sid, "reason": why,
            "reason_ar": f"مصدر أسماء الأدوية «{sid}» اترفض ومش هيتستخدم ({why})؛ لازم يتبدل بمصدر رخصته سليمة"}


def _groups_of(doc: dict) -> list:
    """{"groups": [[spellings]]} (one medicine per group), or the older {"terms": {"english": [...], ...}} (one term
    per group)."""
    if isinstance(doc.get("groups"), list):
        return [[t for t in g if isinstance(t, str)] for g in doc["groups"] if isinstance(g, list)]
    grp = doc.get("terms") or {}
    return [[t] for g in grp.values() if isinstance(g, list) for t in g if isinstance(t, str)]


def client_terms(ctx=None) -> list:
    """The client's glossary terms (config/defaults/medical-glossary.json <- profile <- client reel-profile)."""
    from ..common import load_config
    try:
        g = load_config("medical-glossary.json", ctx).get("terms") or {}
        return _folded([t for grp in g.values() if isinstance(grp, list) for t in grp if isinstance(t, str)])
    except Exception:  # noqa: BLE001
        return []


def _folded(terms) -> list:
    out, seen = [], set()
    for t in terms:
        f = " ".join(fold(x) for x in str(t).split() if fold(x))
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def near(a: str, b: str) -> bool:
    """One letter added, dropped or changed (a mishearing of a long name: «اوزمبك» for «اوزمبيك»)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return a == b
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:k] + t[k + 1:] == s for k in range(len(t)))


# International non-proprietary name endings (generic drug names), in English and their usual Arabic spelling:
# a long word ending so is a likely medicine even when no list knows it
INN_ENDINGS = ("mab", "cillin", "mycin", "floxacin", "prazole", "sartan", "pril", "olol", "statin", "dipine", "gliptin",
               "gliflozin", "azole", "cycline", "parin", "lukast", "setron", "triptan", "tidine", "profen", "semide",
               "thiazide", "vir", "oxetine", "pam", "lam",
               "سيلين", "مايسين", "فلوكساسين", "برازول", "سارتان", "بريل", "ولول", "ستاتين", "ديبين", "جليبتين",
               "جليفلوزين", "ازول", "سيكلين", "بارين", "لوكاست", "سيترون", "تريبتان", "تيدين", "بروفين", "سيميد",
               "ثيازيد", "اوكستين", "ازيبام")


def inn_like(tok: str) -> bool:
    return len(tok) >= 7 and any(tok.endswith(e) for e in INN_ENDINGS)
