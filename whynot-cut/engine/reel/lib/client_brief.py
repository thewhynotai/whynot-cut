# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""The client brief cache (Addendum M5-T4): output/client_database/client-brief.md.

Every video and agent starts from this file instead of reading the client database: brand (colour roles, logo), people
(name, role, gender, honorifics), fonts and their pairs, style family and intensity, standing rules and review domains,
at most CAP_TOKENS (1,000) tokens as counted by `estimate_tokens`, the ONE pinned estimator of lib/brief.py (the same
function object: tests/test_brief.py C11 checks the identity).

Where each part comes from, read only through the owners' public readers (no edit to client_db.py, wnc-queue's file):
    brand            client_db.load: branding/brand-tokens.json (roles, official colours), asset-manifest.json (logos)
    people           common.Context(root).config("profile.json") -> people.load_people (a missing or invalid gender
                     is `unknown`: never inferred from a name, T1.7); only name, role, gender, honorifics, pronouns
    fonts and pairs  client_db.load: branding/typography.json -> font_roles.resolve per role (the resolver every
                     renderer uses, with brand.json font_roles_fallback); `pairing` (the Task 56 field) when present
    style            Context.config("style.json"): `style_family` / `intensity` (M3 names them; "not set (M3)" until
                     then, never a guess), the T4.2 knobs, the caption look, pause removal
    standing rules   rules_loop.list_rules (the sealed registry; the engine's own phrases, never the editor's words)
    review domains   review_domains.client_set (medical and ai always), registry() for the approver, detect_mode
    notes            typography.json notes, client-database-status.json issues, role files edited after the last
                     `reel client-db` (branding/brand-roles.json, typography-roles.json)
Contact details (phone, email) and free-text profile fields never reach the brief: only the fields above are read, and
an e-mail address or phone number written inside one of them is replaced by "(contact removed)".

Cache. `ensure(root)` rebuilds only when a source changed. The fingerprint (client-brief.json, written LAST, after the
body; both atomically and never through a link, lib/linksafe) holds the sha256 of every file the builder actually
opened (recorded with an audit hook while `collect` runs, so a reader that opens one more file is fingerprinted with no
list to keep in step), the sha256 or "missing" of every declared source it did not open (a rules.json that appears
later), the sha256 of the body and the builder's own stamp (this module, the estimator rates, the gender values).
Keys are relative to the client root (a moved or copied client is not rebuilt for nothing), `plugin:<path>` under the
plugin, `ext:<absolute path>` anywhere else. A crash between body and fingerprint, a hand-edited body or a damaged
fingerprint reads as stale: the next call rebuilds. `build` and `state` never write.

The cap. Whole lines go, in this order: notes, style details, extra font families, extra colours, rules that forbid
nothing; then (only if the rest alone is still over) rules that forbid something, profile problems and people, each as
"the first N" and `… N more <what>, see <file>` in place. The first group's cuts are said once, in a closing `cut to fit`
line (paths under output/client_database/). When even the lines never cut exceed the cap, the first line says so.
Review domains and the gender of every shown person are never cut. A
line that is too long stops on a whole word, else on a safe grapheme boundary (brief.clip). Client text is fenced as
data (a ~~~text block longer than any tilde run inside); the brief has no wall-clock time (the `generated` stamp is in
the fingerprint only), so identical sources give an identical brief.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from . import client_db, font_roles, linksafe, people, review_domains, rules_loop, style_knobs
from .brief import RATES, clip, estimate_tokens, fence_for, rel_path, scrub
from .common import CLIENT_PROFILE_REL, CONFIG_DIR, PLUGIN_DIR, PROFILES_DIR, Context, Paths, now_iso, read_json
from .errors import FileFormatError, Guidance

__all__ = ("CAP_TOKENS", "BRIEF_REL", "PRINTS_REL", "estimate_tokens", "build", "collect", "render", "ensure",
           "state", "notice", "source_key", "key_path")

CAP_TOKENS = 1000
DB_REL = "output/client_database"
BRIEF_REL = DB_REL + "/client-brief.md"
PRINTS_REL = DB_REL + "/client-brief.json"
SCHEMA = 1

# The path-bearing typography file is named by client_db's own table (PATH_FIELDS), not spelled here: the T4.5
# guard (tests/test_t45_guard.py) keeps every read of it on client_db.load, and so it is (see _fonts and _notes).
TYPOGRAPHY_REL = next(r for r in client_db.PATH_FIELDS if r.startswith("branding/"))
DB_FILES = ("branding/brand-tokens.json", "branding/brand-roles.json", TYPOGRAPHY_REL,
            "branding/typography-roles.json", "asset-manifest.json", "client-database-status.json")
PROFILE_FILES = ("profile.json", "style.json", "brand.json")
RULES_FILE = "rules.json"
DEFAULT_FILES = ("profile.json", "style.json", "brand.json", "preference-phrases.json")

UNKNOWN_GENDER = "gender unknown, ask the editor / غير معروف، اسأل المونتير"
GENDER_TEXT = {"male": "male", "female": "female"}
SEP = " | "                                 # ASCII: the estimator counts "·" or "«»" as 2 tokens each
NOT_SET = "not set (M3)"
ROLES_ORDER = ("primary", "secondary", "accent", "neutral_light")
FONT_ROLES = ("caption", "headline", "body", "term", "small")
LINE_CHARS = 300
PERSON_CHARS = 300                     # the row bound; the fields below keep every row well under it
FIELD_CHARS = {"name": 80, "role": 80, "honorific": 30, "pronouns": 20}
NOTE_CHARS = 220
RULE_CHARS = 120
LOGOS_SHOWN = 3

# parts that may be cut, in order (TRIM first; LAST only when the rest alone is still over the cap)
TRIM = ("notes", "style_detail", "fonts_extra", "colours_extra", "rules_other")
LAST = ("rules_block", "people_issues", "people")
PARTS = TRIM + LAST
LABEL = "label:"                        # a row "label:<part>" is shown only while a line of <part> is
OVER_CAP = " (over the cap: the lines that are never cut are longer)"
MORE = {"notes": ("notes", DB_REL + "/client-database-status.json"),
        "style_detail": ("style details", CLIENT_PROFILE_REL + "/style.json"),
        "fonts_extra": ("font families", f"{DB_REL}/{TYPOGRAPHY_REL}"),
        "colours_extra": ("colour lines", DB_REL + "/branding/brand-tokens.json"),
        "rules_other": ("rules", CLIENT_PROFILE_REL + "/rules.json"),
        "rules_block": ("rules that forbid something", CLIENT_PROFILE_REL + "/rules.json"),
        "people_issues": ("profile problems", CLIENT_PROFILE_REL + "/profile.json"),
        "people": ("people", CLIENT_PROFILE_REL + "/profile.json")}

_HEX = re.compile(r"#?([0-9A-Fa-f]{6})")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<![\w#])\+?\d[\d\s().\-]{6,}\d(?!\w)")
_NAME = re.compile(r"[\w][\w \-]*")
_KNOB_HEX = re.compile(r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})")       # style_knobs: the "#" is required
_BLOCKS = re.compile(r"\b(no|without|never|hidden)\b", re.I)
_CODE = (".py", ".pyc", ".pyd", ".so", ".dll", ".pth", ".zip")
CONTACT = "(contact removed)"


def _builder_stamp() -> str:
    """Changes when this module, the estimator's rates, the cap or the gender values change: the brief is rebuilt."""
    try:
        src = Path(__file__).read_bytes()
    except OSError:
        src = b""
    extra = json.dumps({"rates": RATES, "cap": CAP_TOKENS, "genders": people.GENDERS, "schema": SCHEMA},
                       sort_keys=True).encode("utf-8")
    return hashlib.sha256(src + b"\0" + extra).hexdigest()[:16]


BUILDER = _builder_stamp()


# --------------------------------------------------------------------------------------------- what was opened
_OPENED: contextvars.ContextVar = contextvars.ContextVar("client_brief_opened", default=None)
_HOOKED: list = []


def _audit(event, args):
    """sys audit hook: while `build` runs `collect` (this thread or task only), note every file opened."""
    if event == "open":
        rec = _OPENED.get()
        if rec is not None:
            rec.append(args)


def _hook():
    if not _HOOKED:
        sys.addaudithook(_audit)                 # stays for the process; idle (one context lookup) outside a build
        _HOOKED.append(True)


def _plain(s: str) -> str:
    r"""Without the Windows extended-length prefix (\\?\C:\x, \\?\UNC\srv\share)."""
    if s.startswith("\\\\?\\UNC\\"):
        return "\\\\" + s[8:]
    return s[4:] if s.startswith("\\\\?\\") else s


def _rel_under(p: str, base: str, pm) -> str | None:
    try:
        rel = pm.relpath(p, base)
    except ValueError:                          # another drive
        return None
    if rel in (".", pm.curdir) or rel == pm.pardir or rel.startswith(pm.pardir + pm.sep) or pm.isabs(rel):
        return None
    return rel.replace(pm.sep, "/")


def source_key(path, root, plugin=PLUGIN_DIR, pathmod=os.path, real: bool = True) -> str:
    """The fingerprint key of a file: its POSIX path relative to the client root, `plugin:<path>` under the plugin,
    else `ext:<absolute path>`. Case and separators follow `pathmod` (ntpath on Windows: case-insensitive); the
    extended-length prefix is ignored; with `real`, the real paths are compared too (a junction, macOS /private)."""
    pm = pathmod
    p = _plain(os.fsdecode(os.fspath(path)))
    if not pm.isabs(p):
        p = os.path.abspath(p) if real else pm.join(_plain(str(root)), p)
    cands = [pm.normpath(p)]
    if real:
        cands.append(_plain(os.path.realpath(p)))
    for base, prefix in ((root, ""), (plugin, "plugin:")):
        b = _plain(os.fsdecode(os.fspath(base)))
        bases = [pm.normpath(b)] + ([_plain(os.path.realpath(b))] if real else [])
        for c in cands:
            for bb in bases:
                rel = _rel_under(c, bb, pm)
                if rel:
                    return prefix + rel
    return "ext:" + cands[0].replace("\\", "/") if pm.sep == "\\" else "ext:" + cands[0]


def key_path(key: str, root, plugin=PLUGIN_DIR, pathmod=os.path) -> str:
    """The file a fingerprint key names on this computer (the inverse of source_key)."""
    if key.startswith("plugin:"):
        return pathmod.join(str(plugin), *key[len("plugin:"):].split("/"))
    if key.startswith("ext:"):
        return key[len("ext:"):]
    return pathmod.join(str(root), *key.split("/"))


def _hash(path) -> str:
    """sha256 of a file's bytes; "missing" when it does not exist. os.open, not open(): the fingerprint's own reads
    are never mistaken for the builder's."""
    try:
        fd = os.open(os.fspath(path), os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except (FileNotFoundError, NotADirectoryError):
        return "missing"
    except OSError:
        return "unreadable"
    h = hashlib.sha256()
    try:
        while True:
            b = os.read(fd, 1 << 20)
            if not b:
                break
            h.update(b)
    finally:
        os.close(fd)
    return h.hexdigest()


def _prefixes() -> list:
    out = []
    for p in {sys.prefix, sys.base_prefix, sys.exec_prefix}:
        if p:
            out.append(os.path.normcase(os.path.abspath(p)))
    return out


def _opened_keys(raw: list, root) -> list:
    """Fingerprint keys of the data files `collect` opened for reading (code and the interpreter's own files left out)."""
    keys, skip = set(), (BRIEF_REL, PRINTS_REL)
    pre = _prefixes()
    for args in raw:
        path, mode, flags = (tuple(args) + (None, None, None))[:3]
        if isinstance(mode, str) and any(c in mode for c in "wax+"):
            continue
        if mode is None and isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            continue
        if path is None or isinstance(path, int):
            continue
        try:
            s = os.fsdecode(os.fspath(path))
        except TypeError:
            continue
        if s.lower().endswith(_CODE):
            continue
        a = os.path.normcase(os.path.abspath(_plain(s)))
        if any(a == p or a.startswith(p.rstrip("\\/") + os.sep) for p in pre):
            continue
        k = source_key(s, root)
        if k not in skip:
            keys.add(k)
    return sorted(keys)


# --------------------------------------------------------------------------------------------- reading
def _root(x) -> Path:
    """The client root of a Paths-like object (anything with `.root` that is not itself a path) or of a path."""
    r = x if isinstance(x, (str, bytes, os.PathLike)) else getattr(x, "root", x)
    return Path(os.fsdecode(r)).expanduser().resolve()


def _db(paths, rel: str):
    """(document, "ok" | "missing" | "damaged") of a client-database file, through client_db.load."""
    try:
        doc = client_db.load(paths, rel, None)
    except (FileFormatError, OSError, ValueError):
        return None, "damaged"
    if doc is None:
        return None, "missing"
    return doc, "ok"


def _config(ctx: Context, name: str):
    """(merged config, None) or ({}, why) when a layer is damaged."""
    try:
        doc = ctx.config(name)
    except (FileFormatError, OSError, ValueError) as e:
        return {}, f"{name} damaged, not read ({type(e).__name__})"
    return (doc if isinstance(doc, dict) else {}), None


def _hexv(v) -> str | None:
    h = v.get("hex") if isinstance(v, dict) else v
    m = _HEX.fullmatch(h.strip()) if isinstance(h, str) else None
    return "#" + m.group(1).upper() if m else None


def _brand(paths, root) -> dict:
    tok, st = _db(paths, "branding/brand-tokens.json")
    out = {"state": st, "roles": [], "official_extra": [], "derived": [], "measured_only": False, "logos": []}
    if isinstance(tok, dict):
        roles = tok.get("roles") if isinstance(tok.get("roles"), dict) else {}
        order = [r for r in ROLES_ORDER if r in roles] + sorted(r for r in roles if r not in ROLES_ORDER)
        out["roles"] = [(str(r), h) for r in order if (h := _hexv(roles[r]))]
        used = {h for _, h in out["roles"]}
        seen = set()
        for c in tok.get("official_colors") or []:
            h = _hexv(c)
            if h and h not in used and h not in seen:
                seen.add(h)
                out["official_extra"].append(h)
        der = tok.get("derived") if isinstance(tok.get("derived"), dict) else {}
        out["derived"] = [(str(k), h) for k in sorted(der) if (h := _hexv(der[k]))]
        out["measured_only"] = not out["roles"] and not tok.get("official_colors") and bool(tok.get("measured_palettes"))
    elif st == "damaged":
        out["state"] = "damaged"
    man, _ = _db(paths, "asset-manifest.json")
    if isinstance(man, dict):
        for a in man.get("assets") or []:
            if isinstance(a, dict) and a.get("category") == "logo" and (a.get("file") or a.get("rel")):
                out["logos"].append(rel_path(root, a.get("file") or a.get("rel")))
    return out


def _people(prof: dict, perr) -> dict:
    out = {"state": "ok" if not perr else "damaged", "people": [], "issues": [], "error": perr}
    if perr:
        return out
    try:
        ppl, issues = people.load_people(prof)
    except Exception as e:  # noqa: BLE001 — a profile slip never stops the brief
        return {"state": "damaged", "people": [], "issues": [], "error": f"people[] not read ({type(e).__name__})"}
    for p in ppl:
        out["people"].append({k: str(p.get(k) or "").strip() for k in ("name", "role", "honorific_ar",
                                                                         "honorific_en", "pronouns")}
                             | {"gender": p.get("gender") if p.get("gender") in ("male", "female") else "unknown"})
    out["issues"] = [str(i) for i in issues]
    return out


def _fonts(paths, ctx: Context) -> dict:
    typ, st = _db(paths, TYPOGRAPHY_REL)
    out = {"state": st, "roles": [], "pairs": [], "used": [], "extra": [], "uninstalled": 0}
    if not isinstance(typ, dict):
        if typ is not None:
            out["state"] = "damaged"
        return out
    brand_cfg, _ = _config(ctx, "brand.json")
    fb = (brand_cfg.get("font_roles_fallback") or {}) if isinstance(brand_cfg.get("font_roles_fallback"), dict) else {}
    fb = fb.get("weights") if isinstance(fb.get("weights"), dict) else {}
    used = []
    for role in FONT_ROLES:
        try:
            r = font_roles.resolve(typ, role, fb)
        except Exception:  # noqa: BLE001 — a malformed typography.json: said, not raised
            r = {}
        if r.get("family"):
            out["roles"].append((role, str(r["family"]), str(r.get("style") or ""), bool(r.get("exact"))))
            if r["family"] not in used:
                used.append(r["family"])
        else:
            out["roles"].append((role, None, None, False))
    fams = typ.get("families") if isinstance(typ.get("families"), dict) else {}

    def desc(name, e):
        e = e if isinstance(e, dict) else {}
        ar, lat = bool(e.get("supports_arabic")), bool(e.get("supports_latin"))
        script = "Arabic+Latin" if ar and lat else "Arabic" if ar else "Latin" if lat else "script unknown"
        n = len(e.get("weights") or [])
        return f"{name} ({script}, {n} weight{'s' if n != 1 else ''})"
    out["used"] = [desc(n, fams.get(n)) for n in used if n in fams] + [n for n in used if n not in fams]
    out["extra"] = [desc(n, e) for n, e in fams.items() if n not in used]
    pairing = typ.get("pairing") if isinstance(typ.get("pairing"), dict) else {}
    order = [r for r in FONT_ROLES if r in pairing] + sorted(r for r in pairing if r not in FONT_ROLES)
    for role in order:
        e = pairing[role]
        if isinstance(e, dict) and e.get("arabic") and e.get("latin"):
            out["pairs"].append({"role": str(role), "arabic": str(e["arabic"]), "latin": str(e["latin"]),
                                 "latin_scale": e.get("latin_scale"), "score": e.get("score"),
                                 "source": str(e.get("source") or "client")})
    miss = typ.get("missing_or_uninstalled")
    out["uninstalled"] = len(miss) if isinstance(miss, list) else 0
    return out


def _knob(layers: list, key: str):
    """A T4.2 knob as `reel plan` reads it: the highest style.json layer that sets it (an explicit null is "not set";
    the alias spelling counts only in a file without the real key), else the engine default."""
    for _label, data in reversed(layers):
        if not isinstance(data, dict):
            continue
        if key in data:
            if data[key] is not None:
                return data[key]
            continue
        for alias, real in style_knobs.ALIASES.items():
            if real == key and data.get(alias) is not None:
                return data[alias]
    return style_knobs.DEFAULTS.get(key)


def _word(v, n: int = 40) -> str | None:
    """A short name from a client file (a look, a style family): letters, digits, space, - and _ only, else None."""
    return v.strip() if isinstance(v, str) and _NAME.fullmatch(v.strip() or "-" * 99) and len(v.strip()) <= n else None


def _style(ctx: Context) -> dict:
    sty, err = _config(ctx, "style.json")
    out = {"family": _word(sty.get("style_family")), "intensity": _word(sty.get("intensity")), "detail": [],
           "error": err}
    try:
        layers = style_knobs.layers(ctx)
    except (FileFormatError, OSError, ValueError):
        layers = []
    size, hook = _knob(layers, "caption_size_px"), _knob(layers, "captions_during_hook")
    sfx, hl = _knob(layers, "hook_title_sfx"), _knob(layers, "highlight_colour")
    size_s = str(int(size)) + " px" if isinstance(size, (int, float)) and not isinstance(size, bool) \
        and float(size).is_integer() else "template size" if size is None else "invalid (template size)"
    hook_s = hook.strip().lower() if isinstance(hook, str) and hook.strip().lower() in ("hide", "show") else "hide"
    hl_s = hl.strip() if isinstance(hl, str) and (hl.strip().lower() in ("brand", "accent", "ink")
                                                 or _KNOB_HEX.fullmatch(hl.strip())) else "brand"
    out["detail"].append(f"knobs: caption size {size_s}{SEP}captions under the hook title: {hook_s}{SEP}"
                         f"hook title sound: {'off' if sfx is False else 'on'}{SEP}highlight: {hl_s}")
    cap = sty.get("captions")
    if isinstance(cap, dict) and _word(cap.get("look")):
        out["detail"].append(f"caption look: {_word(cap.get('look'))}"
                             + (f"{SEP}digits {_word(cap.get('digits'))}" if _word(cap.get("digits")) else ""))
    rp = sty.get("remove_pauses")
    if isinstance(rp, dict):
        num = lambda v: str(int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else "?"  # noqa: E731
        out["detail"].append(f"pauses removed: min {num(rp.get('min_pause_ms'))} ms, pad {num(rp.get('pad_ms'))} ms")
    elif rp is True:
        out["detail"].append("pauses removed (engine defaults)")
    return out


def _blocks(r: dict) -> bool:
    """A rule that forbids something (never cut): no sound, captions hidden, no music, no emoji, no transitions..."""
    if r.get("knob") == "hook_title_sfx":
        return r.get("value") is False
    if r.get("knob") == "captions_during_hook":
        return r.get("value") == "hide"
    return bool(_BLOCKS.search(str(r.get("en") or "")))


def _rules(root) -> dict:
    try:
        lr = rules_loop.list_rules(root)
    except (Guidance, FileFormatError, OSError, ValueError) as e:
        why = e.error if isinstance(e, Guidance) else f"{type(e).__name__}: {e}"
        return {"state": "unreadable", "error": str(why), "block": [], "other": [], "refused": 0}
    active = [r for r in lr.get("active") or [] if isinstance(r, dict)]
    shown = [r for r in active if not r.get("refused")]
    rows = [(f"{r.get('id')} {r.get('en')}", _blocks(r)) for r in shown]
    return {"state": "ok" if shown else "none", "error": None, "block": [t for t, b in rows if b],
            "other": [t for t, b in rows if not b], "refused": len(active) - len(shown)}


def _domains(prof: dict, perr) -> dict:
    floor = tuple(sorted(review_domains.ALWAYS_ON))
    try:
        ids = review_domains.client_set(prof)
        reg = review_domains.registry()
        detect = review_domains.detect_mode(prof)
    except (Guidance, FileFormatError, OSError, ValueError) as e:
        return {"ids": list(floor), "approvers": {}, "always": list(floor), "detect": None,
                "error": e.error if isinstance(e, Guidance) else f"{type(e).__name__}: {e}"}
    appr = {d: str(((reg.get(d) or {}).get("approver") or {}).get("en") or "") for d in ids}
    return {"ids": list(ids), "approvers": appr, "always": list(floor), "detect": detect,
            "error": perr}


def _notes(paths) -> list:
    out = []
    tok, _ = _db(paths, "branding/brand-tokens.json")
    br, _ = _db(paths, "branding/brand-roles.json")
    if isinstance(tok, dict) and isinstance(br, dict) and any(
            (br.get(k) or {}) != (tok.get(k) or {}) for k in ("roles", "derived")):
        out.append("branding/brand-roles.json differs from brand-tokens.json: run `reel client-db` so the colour "
                   "roles apply")
    typ, _ = _db(paths, TYPOGRAPHY_REL)
    tr, _ = _db(paths, "branding/typography-roles.json")
    if isinstance(typ, dict) and isinstance(tr, dict) and any(
            (tr.get(k) or ({} if k == "roles" else [])) != (typ.get(k) or ({} if k == "roles" else []))
            for k in ("roles", "notes")):
        out.append("branding/typography-roles.json differs from typography.json: run `reel client-db` so the font "
                   "roles apply")
    if isinstance(typ, dict):
        out += [str(n) for n in typ.get("notes") or [] if isinstance(n, (str, int, float))]
    status, _ = _db(paths, "client-database-status.json")
    if isinstance(status, dict):
        out += [str(n) for n in status.get("issues") or [] if isinstance(n, (str, int, float))]
    return out


def collect(paths) -> dict:
    """The brief's facts, read from the client database through the owners' public readers. Never writes."""
    root = Path(paths.root)
    ctx = Context(root)
    prof, perr = _config(ctx, "profile.json")
    name = prof.get("display_name") or prof.get("id")
    brand_ = _brand(paths, root)
    return {"client": str(name) if isinstance(name, (str, int)) and str(name).strip() else None,
            "brand": brand_, "people": _people(prof, perr), "fonts": _fonts(paths, ctx), "style": _style(ctx),
            "rules": _rules(root), "domains": _domains(prof, perr), "notes": _notes(paths)}


# --------------------------------------------------------------------------------------------- rendering
def _no_contacts(s: str) -> str:
    s = _EMAIL.sub(CONTACT, s)
    return _PHONE.sub(lambda m: CONTACT if sum(c.isdigit() for c in m.group()) >= 8 else m.group(), s)


def _person(p: dict, root) -> str:
    """One person, each field clipped on its own (contacts removed first, so a cut never leaves part of a number);
    the gender text is never cut."""
    f = lambda k, n: clip(scrub(_no_contacts(p[k]), root), n)  # noqa: E731
    bits = [f("name", FIELD_CHARS["name"]) or "?"]
    if p["role"]:
        bits.append(f("role", FIELD_CHARS["role"]))
    bits.append(GENDER_TEXT.get(p["gender"], UNKNOWN_GENDER))
    if p["honorific_ar"]:
        bits.append(f'"{f("honorific_ar", FIELD_CHARS["honorific"])}"')
    if p["honorific_en"]:
        bits.append(f'"{f("honorific_en", FIELD_CHARS["honorific"])}"')
    if p["pronouns"]:
        bits.append(f("pronouns", FIELD_CHARS["pronouns"]))
    return "- " + SEP.join(bits)


def _sections(f: dict, root) -> list:
    """[(title, fenced, [(part or None, line)])], every line already scrubbed and clipped."""
    d = lambda x, n=LINE_CHARS: clip(scrub(x, root), n)  # noqa: E731
    S = []
    b = f["brand"]
    rows = []
    if b["state"] == "missing":
        rows.append((None, "brand: missing: brand-tokens.json is not built yet (run `reel client-db`)"))
    elif b["state"] == "damaged":
        rows.append((None, "brand: damaged: brand-tokens.json could not be read (fix it, or run `reel client-db`)"))
    else:
        if b["roles"]:
            rows.append((None, "colours: " + SEP.join(f"{r} {h}" for r, h in b["roles"])))
        elif b["measured_only"]:
            rows.append((None, "colours: none official yet (measured candidates only: assign roles in "
                               "branding/brand-roles.json, or ask the client for colour codes)"))
        else:
            rows.append((None, "colours: none recorded"))
        if b["official_extra"]:
            rows.append(("colours_extra", "other official colours: " + ", ".join(b["official_extra"])))
        if b["derived"]:
            rows.append(("colours_extra", "working tints (not official): " + SEP.join(f"{k} {h}" for k, h in
                                                                                       b["derived"])))
    logos = b["logos"]
    rows.append((None, "logo: " + (d(", ".join(logos[:LOGOS_SHOWN])) + (f" (+{len(logos) - LOGOS_SHOWN} more)"
                                                                          if len(logos) > LOGOS_SHOWN else "")
                                   if logos else "none identified")))
    S.append(("brand", False, rows))

    p = f["people"]
    rows = []
    if p["state"] == "damaged":
        rows.append((None, d(f"people: not read: {p['error']} (fix reel-profile/profile.json)")))
    elif not p["people"]:
        rows.append((None, "people: none recorded (fill people[] in reel-profile/profile.json from the client's "
                           "material; gender and honorific checks are off until then)"))
    for x in p["people"]:
        rows.append(("people", clip(_person(x, root), PERSON_CHARS)))
    for i in p["issues"]:
        rows.append(("people_issues", "! " + d(_no_contacts(i), NOTE_CHARS)))
    S.append(("people (data)", True, rows))

    fo = f["fonts"]
    rows = []
    if fo["state"] == "missing":
        rows.append((None, "fonts: missing: typography.json is not built yet (run `reel client-db`)"))
    elif fo["state"] == "damaged":
        rows.append((None, "fonts: damaged: typography.json could not be read (fix it, or run `reel client-db`)"))
    else:
        rows.append((None, d("roles: " + SEP.join(
            f"{r} {fam} {sty}".rstrip() + ("" if exact else " (nearest)") if fam else f"{r} none"
            for r, fam, sty, exact in fo["roles"]))))
        if fo["pairs"]:
            for pr in fo["pairs"]:
                bits = []
                ls, sc = pr["latin_scale"], pr["score"]
                if isinstance(ls, (int, float)) and not isinstance(ls, bool):
                    bits.append(f"latin x{ls:g}")
                if isinstance(sc, (int, float)) and not isinstance(sc, bool):
                    bits.append(f"score {sc:g}")
                bits.append(pr["source"])
                rows.append((None, d(f"font pair: {pr['role']} {pr['arabic']} + {pr['latin']} ({', '.join(bits)})")))
        else:
            rows.append((None, "font pairs: not set"))
        if fo["used"]:
            rows.append(("fonts_extra", d("families: " + SEP.join(fo["used"]))))
        for e in fo["extra"]:
            rows.append(("fonts_extra", d("also: " + e)))
        if fo["uninstalled"]:
            rows.append((None, f"not installed: {fo['uninstalled']} font file(s)"))
    S.append(("fonts", False, rows))

    st = f["style"]
    rows = [(None, f"style family: {d(st['family'], 40) if st['family'] else NOT_SET} | intensity: "
                   f"{d(st['intensity'], 40) if st['intensity'] else NOT_SET}")]
    if st["error"]:
        rows.append((None, d(f"style: {st['error']}")))
    rows += [("style_detail", d(x)) for x in st["detail"]]
    S.append(("style", False, rows))

    ru = f["rules"]
    if ru["state"] == "unreadable":
        S.append(("standing rules", False, [(None, d(f"standing rules: unreadable: {ru['error']}", NOTE_CHARS)),
                                            (None, "no rule applies until it is fixed: `reel rules --list`")]))
    elif ru["state"] == "none":
        S.append(("standing rules", False, [(None, "standing rules: none")]))
    else:
        rows = []
        if ru["block"]:                     # rules that forbid something: kept whole unless the rest alone overflows
            rows += [(None, "forbids:")] + [("rules_block", "- " + d(t, RULE_CHARS)) for t in ru["block"]]
        if ru["other"]:
            rows += [(LABEL + "rules_other", "prefers:")] + [("rules_other", "- " + d(t, RULE_CHARS))
                                                             for t in ru["other"]]
        if ru["refused"]:
            rows.append((None, f"- {ru['refused']} refused rule row(s) not shown (`reel rules --list`)"))
        S.append(("standing rules (data)", True, rows))

    dm = f["domains"]
    line = f"domains: {', '.join(dm['ids'])}{SEP}always on: {', '.join(dm['always'])}"
    if dm["detect"]:
        line += f"{SEP}detect: {dm['detect']}"
    rows = [(None, line)]
    if dm["error"]:
        rows.append((None, d(f"profile problem: {dm['error']} (review never goes off: always on "
                             f"{', '.join(dm['always'])})", NOTE_CHARS)))
    S.append(("review domains", False, rows))

    if f["notes"]:
        S.append(("notes (data)", True, [("notes", "- " + d(n, NOTE_CHARS)) for n in f["notes"]]))
    return S


def _render(sections: list, name: str, reason: str, cap: int, keep: dict, shown: int, over: bool = False) -> str:
    """A cut of a TRIM part is said once, in the closing `trimmed to fit` line (one shared folder, so the pointers
    cost less); a cut of a protected part (LAST) is said in place, with its full path."""
    L = [f"# client brief: {name} (~{shown} tokens / {cap})" + (OVER_CAP if over else ""),
         f"built: {reason}"]
    cuts = []
    for title, fenced, rows in sections:
        out, seen = [], {}
        last = {}
        for i, (part, _t) in enumerate(rows):
            if part and not part.startswith(LABEL):
                last[part] = i
        for i, (part, text) in enumerate(rows):
            if part and part.startswith(LABEL):        # a label, shown only while a line of its part is
                if keep.get(part[len(LABEL):], 0):
                    out.append(text)
                continue
            if part:
                seen[part] = seen.get(part, 0) + 1
                if seen[part] <= keep.get(part, 0):
                    out.append(text)
            else:
                out.append(text)
            if part and i == last[part] and seen[part] > keep.get(part, 0):
                what, where = MORE[part]
                more = f"… {seen[part] - keep.get(part, 0)} more {what}, see "
                if part in LAST:
                    out.append(more + where)
                else:
                    cuts.append(more + where[len(DB_REL) + 1:])
        if not out:
            continue                                # every line of it cut: said in the trimmed-to-fit line
        L.append(f"## {title}")
        if fenced and out:
            fence = fence_for(out)
            L += [fence + "text", *out, fence]
        else:
            L += out
    if cuts:
        L.append(f"cut to fit, in {DB_REL}/: " + "; ".join(cuts))
    return "\n".join(L) + "\n"


def _fit(sections, name, reason, cap, keep, over: bool = False) -> tuple:
    shown = 0
    for _ in range(4):
        text = _render(sections, name, reason, cap, keep, shown, over)
        n = estimate_tokens(text)
        if n == shown:
            break
        shown = n
    return text, estimate_tokens(text)


def render(f: dict, root, cap: int = CAP_TOKENS, reason: str = "built") -> tuple:
    """(text, tokens, trimmed, counts): whole lines go part by part (TRIM, then LAST), each part keeping the most
    lines that fit."""
    sections = _sections(f, root)
    name = clip(scrub(_no_contacts(f.get("client") or "client"), root), 80)
    reason = clip(scrub(reason, root), 240)
    counts = {p: 0 for p in PARTS}
    for _t, _f, rows in sections:
        for part, _x in rows:
            if part and not part.startswith(LABEL):
                counts[part] += 1
    keep = dict(counts)
    text, n = _fit(sections, name, reason, cap, keep)
    for part in PARTS:
        if n <= cap:
            break
        if not counts[part]:
            continue
        keep[part] = 0
        text, n = _fit(sections, name, reason, cap, keep)
        if n > cap:
            continue
        lo, hi = 0, counts[part]
        while lo < hi:
            mid = (lo + hi + 1) // 2
            keep[part] = mid
            if _fit(sections, name, reason, cap, keep)[1] <= cap:
                lo = mid
            else:
                hi = mid - 1
        keep[part] = lo
        text, n = _fit(sections, name, reason, cap, keep)
    if n > cap:                                 # nothing left to cut and still over: said, never hidden
        text, n = _fit(sections, name, reason, cap, keep, over=True)
    return text, n, {p: counts[p] - keep[p] for p in PARTS}, counts


# --------------------------------------------------------------------------------------------- build and cache
def _declared(root: Path) -> list:
    """(key, path) of every source the brief depends on, read or not: a file that appears later rebuilds it."""
    db = root / DB_REL
    files = [db / r for r in DB_FILES]
    files += [root / CLIENT_PROFILE_REL / n for n in PROFILE_FILES + (RULES_FILE,)]
    files += [CONFIG_DIR / n for n in DEFAULT_FILES]
    files.append(Path(review_domains.REGISTRY_DIR) / review_domains.REGISTRY)
    try:
        for d in Context(root).profile_dirs():
            if Path(d).parent == PROFILES_DIR:
                files += [Path(d) / n for n in PROFILE_FILES]
    except (FileFormatError, OSError, ValueError):
        pass
    out, seen = [], set()
    for f in files:
        k = source_key(f, root)
        if k not in seen:
            seen.add(k)
            out.append((k, f))
    return out


def build(paths_or_root, cap: int = CAP_TOKENS, reason: str = "built") -> dict:
    """The brief and its fingerprints, written nowhere: {"text", "tokens", "cap", "trimmed", "counts", "facts",
    "opened" (keys), "watched" (keys), "prints": {"opened": {key: sha256}, "watched": {key: sha256 | "missing"}}}."""
    root = _root(paths_or_root)
    paths = Paths(root)
    declared = _declared(root)
    pre = {k: _hash(p) for k, p in declared}
    _hook()
    tok = _OPENED.set([])
    try:
        f = collect(paths)
    finally:
        raw = _OPENED.get() or []
        _OPENED.reset(tok)
    opened = {k: _hash(key_path(k, root)) for k in _opened_keys(raw, root)}
    watched = {}
    for k, _p in declared:
        if k in opened:
            if pre[k] != opened[k]:
                opened[k] = pre[k]              # changed while the brief was built: the next state() rebuilds it
        else:
            watched[k] = pre[k]
    text, n, trimmed, counts = render(f, root, cap, reason)
    return {"text": text, "tokens": n, "cap": cap, "trimmed": trimmed, "counts": counts, "facts": f,
            "reason": reason, "opened": sorted(opened), "watched": sorted(watched),
            "prints": {"opened": dict(sorted(opened.items())), "watched": dict(sorted(watched.items()))}}


def _refusal(root) -> Guidance:
    return Guidance(f"there is no client database in this client folder yet ({DB_REL})",
                    "run `reel discover` then `reel client-db` first (or `reel client-init` for a new client); "
                    "nothing was written", where=str(root))


def _change(key: str, old: str, new: str) -> str:
    if old == "missing":
        return f"{key} added"
    if new == "missing":
        return f"{key} deleted"
    return f"{key} changed"


def state(paths_or_root) -> dict:
    """{"state": current | stale | missing | refused, "reasons", "path", "tokens"}. Reads only."""
    root = _root(paths_or_root)
    base = {"path": BRIEF_REL, "tokens": None}
    if not (root / DB_REL).is_dir():
        return dict(base, state="refused", reasons=[f"no client database ({DB_REL})"])
    md = root / BRIEF_REL
    if not md.exists():
        return dict(base, state="missing", reasons=["not built yet"])
    try:
        doc = read_json(root / PRINTS_REL)
    except (FileFormatError, OSError, ValueError):
        doc = None
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or not isinstance(doc.get("opened"), dict) \
            or not isinstance(doc.get("watched"), dict):
        return dict(base, state="stale", reasons=[f"{PRINTS_REL} missing or damaged"])
    reasons = []
    if doc.get("builder") != BUILDER:
        reasons.append("the brief builder changed (engine update)")
    if doc.get("brief_sha256") != _hash(md):
        reasons.append(f"{BRIEF_REL} changed by hand or half-written")
    for key, old in sorted({**doc["watched"], **doc["opened"]}.items()):
        new = _hash(key_path(key, root))
        if new != old:
            reasons.append(_change(key, str(old), new))
    return dict(base, state="stale" if reasons else "current", reasons=reasons, tokens=doc.get("tokens"))


def notice(paths_or_root) -> str | None:
    """The `reel next` line when the brief is missing or stale (None when current, or with no client database)."""
    st = state(paths_or_root)
    if st["state"] in ("current", "refused"):
        return None
    if st["state"] == "missing":
        return (f"client brief not built yet: run `reel client-brief` ({BRIEF_REL}; every video and agent reads it "
                "before the client's files)")
    rs = st["reasons"]
    more = f" and {len(rs) - 3} more" if len(rs) > 3 else ""
    return f"client brief stale ({'; '.join(rs[:3])}{more}): run `reel client-brief` (it rebuilds only on a change)"


def ensure(paths_or_root, force: bool = False, cap: int = CAP_TOKENS) -> dict:
    """Build client-brief.md when it is missing or a source changed (or `force`); else leave it untouched. The body
    first, the fingerprint last, both atomic and never through a link. No client database -> Guidance, nothing
    written."""
    root = _root(paths_or_root)
    if not (root / DB_REL).is_dir():
        raise _refusal(root)
    st = state(root)
    if st["state"] == "current" and not force:
        return {"ok": True, "path": BRIEF_REL, "rebuilt": False, "reason": "unchanged", "tokens": st["tokens"],
                "cap": cap, "summary": f"client brief current (~{st['tokens']} tokens): {BRIEF_REL}"}
    if force:
        reason = "rebuilt on request"
    elif st["state"] == "missing":
        reason = "first build"
    else:
        reason = "rebuilt: " + "; ".join(st["reasons"])
    r = build(root, cap=cap, reason=reason)
    body = r["text"].encode("utf-8")
    linksafe.replace_atomic(root / BRIEF_REL, root, body, within=DB_REL)
    doc = {"schema": SCHEMA, "builder": BUILDER, "brief_sha256": hashlib.sha256(body).hexdigest(),
           "tokens": r["tokens"], "cap": cap, "reason": reason, "trimmed": r["trimmed"],
           "opened": r["prints"]["opened"], "watched": r["prints"]["watched"], "generated": now_iso()}
    linksafe.replace_atomic(root / PRINTS_REL, root,
                            (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                            within=DB_REL)
    cut = sum(r["trimmed"].values())
    return {"ok": True, "path": BRIEF_REL, "rebuilt": True, "reason": reason, "tokens": r["tokens"], "cap": cap,
            "trimmed": r["trimmed"],
            "summary": f"client brief rebuilt (~{r['tokens']} tokens / {cap}" + (f", {cut} lines cut" if cut else "")
                       + f"): {BRIEF_REL}"}
