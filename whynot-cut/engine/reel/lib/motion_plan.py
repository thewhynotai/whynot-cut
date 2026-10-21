"""Motion plan compiler (`reel motion-plan`, spec §4.1): motion-script.json (authored) -> motion-plan.json (frames and
pixels the After Effects library renders as given), motion-plan.md (Gate 1) and motion-validation.json.

Order: window check -> field rules -> scene anchors -> per-scene content and truth checks (speech words, editorial lines,
numbers, names, assets) -> frames (TimeMap) -> recipe checks -> captions, speaker badge, voice pulse -> audio and SFX.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .common import fmt_ts, ms_to_frame, now_iso, read_json, seq_fps, set_status, write_json, write_text
from .episode_sheet import SHEET_PEOPLE
from .motion_config import direction_for, format_spec, motion_cfg, source as msource
from .motion_layout import contrast, fit, pick_text_color, place, role_of, theme_colors
from .motion_script import (REPLAYS_SPEECH, SCENE_TYPES, check_editorial, check_fields, check_number, digit_runs,
                            fill_placeholders, load_script, match_subsequence, person_name, source_of)
from .motion_timing import anchor_scenes, frame_scenes
from .plan import norm

ARABIC = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
MAX_LINES = {"quote": 3, "title": 2, "body": 3, "label": 2, "stat": 1, "caption": 2}
ROLE_FONT = {"title": "headline", "quote": "headline", "stat": "headline", "body": "body", "label": "body",
             "caption": "caption"}
NUM_IN = re.compile(r"[0-9٠-٩][0-9٠-٩.,٬٫]*")


def _f01(rgb) -> list:
    return [round(c / 255, 4) for c in rgb[:3]]


def _hash(frames: list[int]) -> str:
    return hashlib.sha1(json.dumps(frames).encode()).hexdigest()[:12]


def _system_font() -> dict | None:
    """{"file", "index"} of the system font text is measured with when the brand font files are missing: the Arabic
    fallback (lib/fonts.py: Segoe UI / Arial / Tahoma on Windows, Geeza Pro / Arial on macOS; Geeza Pro is a .ttc,
    so the face index travels with the file)."""
    from .fonts import arabic_fallback
    face = arabic_fallback()
    return {"file": face["file"], "index": int(face.get("index") or 0)} if face else None


# the episode sheet values a motion plan puts on screen (BL-20): the sheet's people (host, guest, guest_2 … guest_9:
# the badge names every speaker turn by its role) and the show
SHEET_SHOWN = SHEET_PEOPLE + ("show",)


def episode_sheet(paths, src: dict) -> dict:
    """The episode sheet values (SHEET_SHOWN) of the reel's episode, from output/episodes/<EP>/00_inputs/episode.json:
    the people's names (and roles), the show. {} without an episode_id or before `reel episode-prep`. The compiler
    reads the sheet only through this, so fingerprint() binds every sheet value that can reach the screen."""
    from .episode import EpisodePaths, load_episode
    eid = src.get("episode_id")
    if "episode_id" in src and not isinstance(eid, str):     # review a1c14fc P3-2: a plain line, never a TypeError
        from .errors import Guidance
        raise Guidance(f"invalid episode id {eid!r} in 00_inputs/source.json: it must be text, e.g. \"EP12\"",
                       "Put back the episode id `reel episodes` lists (in quotes), or pick the reel again with "
                       "`reel reels-select`")
    try:
        sheet = load_episode(EpisodePaths(paths.root, src["episode_id"])).get("sheet") or {}
    except (SystemExit, KeyError):
        return {}
    return {k: sheet[k] for k in SHEET_SHOWN if k in sheet}


def badge_turns(rm: dict, sp: dict) -> list | None:
    """The speaker turns the speaker badge shows from 00_inputs/speakers.json `sp` (each named by its `speaker` role);
    None when the recipe's `speaker_badge` (`rm`, the recipe's motion values) is off or fewer than two speakers talk:
    then no badge, and speakers.json is not bound (review a1c14fc P3-1: every reel has one)."""
    if not rm.get("speaker_badge", True):
        return None
    turns = sp.get("turns") or []
    if len({t.get("speaker") for t in turns}) < 2:
        return None
    return turns


def fingerprint(paths) -> str:
    """Changes when anything the compiled plan depends on changes (script, words, pauses, recipe, motion.json, brand,
    the data/Music tracks and licences the music choice reads, and (BL-20) the names it shows: the episode sheet's
    host / guest / show and the reel's 00_inputs/speakers.json, the speaker badge's fallback names and turns)."""
    src = msource(paths)
    h = hashlib.sha1()
    for rel in ("01_analysis/motion-script.json", "02_transcription/words.json", "06_audio/dialogue/pauses.json"):
        f = paths.p(rel)
        h.update(f.read_bytes() if f.exists() else b"-")
    bt = paths.client_db / "branding/brand-tokens.json"
    h.update(bt.read_bytes() if bt.exists() else b"-")
    h.update(json.dumps([src.get("recipe"), src.get("format"), src.get("direction"), motion_cfg()], sort_keys=True,
                        ensure_ascii=True).encode())
    from .motion_audio import music_state       # T4.6: what THIS plan's music choice reads (off / hand pick / auto)
    try:
        script = json.loads(paths.p("01_analysis/motion-script.json").read_text(encoding="utf-8-sig"))
        sm = script.get("music", "__auto__")
    except (OSError, ValueError, AttributeError, RecursionError):
        script, sm = None, "__auto__"
    rmood = ((src.get("recipe") or {}).get("music") or {}).get("mood") or []
    ms = music_state(paths.root, sm, [rmood] if isinstance(rmood, str) else list(rmood))
    if ms:                      # no tracks: the fingerprint stays as before T4.6 (approved plans do not go stale)
        h.update(json.dumps(ms, sort_keys=True, ensure_ascii=True).encode())
    # BL-20: the names shown. No sheet value shown and no speaker badge: the fingerprint stays as before BL-20
    shown = episode_sheet(paths, src)
    if shown:
        h.update(b"sheet" + json.dumps(shown, sort_keys=True, ensure_ascii=True).encode())
    sp = paths.p("00_inputs/speakers.json")
    if badge_turns((src.get("recipe") or {}).get("motion") or {}, read_json(sp, {}) or {}):
        h.update(b"speakers" + sp.read_bytes())
    cues = shown_cues(paths, script, src)       # BL-21: no captions shown (or no file): as before BL-21
    if cues is not None:
        h.update(b"captions" + json.dumps(cues, ensure_ascii=True).encode())
    return h.hexdigest()


def shown_cues(paths, script, src: dict) -> list | None:
    """BL-21: the caption cues a plan shows, as _Compiler.captions reads them from 02_transcription/captions-short.srt
    ([start_ms, end_ms, text with its line breaks as spaces]); None when no scene shows captions (the script's, a
    scene's or the recipe's `captions`, as _finish decides) or there is no file. An unreadable script counts as
    showing them."""
    f = paths.p("02_transcription/captions-short.srt")
    if not f.exists():
        return None
    if isinstance(script, dict) and isinstance(script.get("scenes"), list):
        rm = (src.get("recipe") or {}).get("motion") or {}
        video = _caption_mode(script.get("captions")) or _caption_mode(rm.get("captions", "off"))
        if not any(((_caption_mode(sc.get("captions")) if isinstance(sc, dict) else None) or video) == "subtitles"
                   for sc in script["scenes"]):
            return None
    from . import srt as srtlib
    return [[c["start_ms"], c["end_ms"], c["text"].replace("\n", " ")] for c in srtlib.read_srt(f)]


class _Compiler:
    def __init__(self, paths, font_override: dict | None = None):
        from .previews import Brand
        from .timemap import TimeMap
        self.paths = paths
        self.src = msource(paths)
        self.cfg = motion_cfg()
        self.rm = dict((self.src.get("recipe") or {}).get("motion") or {})
        self.recipe_type = (self.src.get("recipe") or {}).get("type") or self.src.get("content_type")
        self.fmt = format_spec(self.src.get("format") or "9x16")
        self.direction = self.src.get("direction") or direction_for(self.src.get("language"))
        self.dir = -1 if self.direction == "rtl" else 1
        self.errors, self.warnings, self.approvals, self.editorial, self.notes = [], [], [], [], []
        self.assets, self.sfx = [], []
        self.words = (read_json(paths.p("02_transcription/words.json"), {}) or {}).get("words", [])
        if not self.words:
            raise SystemExit("02_transcription/words.json missing — the motion project's transcript is sliced when the editor picks the reels")
        self.total_ms = int(self.src.get("duration_ms") or self.words[-1]["end_ms"])
        pz = read_json(paths.p("06_audio/dialogue/pauses.json"))
        if not pz:
            raise SystemExit("06_audio/dialogue/pauses.json missing — run `reel audio-clean` for this motion project first")
        self.tmap = TimeMap(pz.get("keep_ms") or [[0, self.total_ms]])
        self.fps = seq_fps()
        self.sheet = episode_sheet(paths, self.src)         # only what fingerprint() binds (BL-20)
        self.window_digits = set().union(*(digit_runs(w["word"]) for w in self.words)) if self.words else set()
        self.brand = Brand(paths.client_db)
        self.font_override = font_override
        self.fonts = self._fonts()

    # ------------------------------------------------------------------ helpers
    def _fonts(self) -> dict:
        if self.font_override:               # the font After Effects will actually draw (e.g. an approved fallback)
            return {role: {"index": 0, **self.font_override} for role in ROLE_FONT}
        from .ae_builder import fonts_map
        fm = fonts_map(self.paths.client_db)
        out, fallback = {}, None
        for role, brole in ROLE_FONT.items():
            # the role's weight (typography.json roles, brand.json, default), else the nearest one the brand has: file and
            # PostScript name always from the SAME face
            face = self.brand.face(brole)
            f, index = face["file"], int(face.get("index") or 0)
            ps = face["ps"] or fm.get(brole) or ""
            if not ps:
                raise SystemExit(f"no PostScript font name for the {brole} role: run `reel client-db` (typography.json)")
            if not f or not Path(f).exists():
                fallback = fallback or _system_font()
                if not fallback:
                    raise SystemExit("no brand font file (run `reel client-db`) and no system font to measure text with")
                f, index = fallback["file"], fallback["index"]
            out[role] = {"ps": ps, "file": str(f), "index": index}      # index: the face of a .ttc/.otc collection
        if fallback:
            self.warnings.append(f"brand font files not found: text measured with {Path(fallback['file']).name}; "
                                 "After Effects "
                                 "uses the brand font names (install them before motion-build)")
        return out

    def frame(self, ms: float) -> int:
        return self.tmap.frame(ms)

    def err(self, msg: str):
        self.errors.append(msg)

    def pool(self, a_ms: int, b_ms: int, slack: bool = True) -> list[int]:
        s = int(self.cfg.get("edge_slack_ms", 1500)) if slack else 0
        return [i for i, w in enumerate(self.words) if a_ms - s <= w["start_ms"] < b_ms + s]

    def speech(self, sid: str, field: str, text: str, pool: list[int], replay: bool = False,
               core: list[int] | None = None) -> list[dict] | None:
        spoken = [self.words[i]["word"] for i in pool]
        r = match_subsequence(text, spoken, 1.0)
        if r["added"] or not r["idx"]:
            self.err(f"{sid}: {field} «{text[:60]}» is not the speaker's words in this scene"
                     + (f" (not said here: {' '.join(r['added'][:6])})" if r["added"] else ""))
            return None
        if replay and core:
            used = {pool[i] for i in r["idx"]}
            dropped = len([i for i in core if i not in used]) / len(core)
            mx = float(self.cfg.get("max_drop_ratio", 0.4))
            if dropped > mx + 1e-9:
                self.err(f"{sid}: {field} leaves out {dropped:.0%} of what is said in this scene (max {mx:.0%}): show "
                         "the words as said, or split the scene")
        flat = [(t, k) for k, w in enumerate(spoken) for t in norm(w).split()]
        toks, j, last = [], 0, None
        for dw in text.split():
            nt = norm(dw).split()
            if not nt:
                toks.append({"text": dw, "cue_frame": last if last is not None else self.frame(self.words[pool[0]]["start_ms"])})
                continue
            k = j
            while k < len(flat) and flat[k][0] != nt[0]:
                k += 1
            k = min(k, len(flat) - 1)
            cue = self.frame(self.words[pool[flat[k][1]]]["start_ms"])
            toks.append({"text": dw, "cue_frame": cue, "word_id": self.words[pool[flat[k][1]]].get("id")})
            j, last = k + len(nt), cue
        return toks

    def find_at(self, at: str, pool: list[int], after: int = -1) -> int | None:
        toks = norm(at or "").split()
        flat = [(t, i) for i in pool for t in norm(self.words[i]["word"]).split()]
        for k in range(len(flat) - len(toks) + 1):
            if flat[k][1] > after and [t for t, _ in flat[k:k + len(toks)]] == toks:
                return flat[k][1]
        return None

    def editorial_text(self, sid: str, field: str, text: str, digits_ok: bool = False) -> str:
        """digits_ok: the caller checks this field's numbers itself (timeline.when → approval, spec §4.1 Numbers)."""
        filled, missing = fill_placeholders(text, self.sheet)
        for m in missing:
            self.err(f"{sid}: {field} uses {{{m}}} but the episode sheet has no {m}")
        for p in check_editorial(filled, set(self.window_digits) | (digit_runs(filled) if digits_ok else set())):
            self.err(f"{sid}: {field} «{filled[:50]}»: {p}")
        self.editorial.append({"scene": sid, "field": field, "text": filled})
        return filled

    def colors(self, theme: str, size: int) -> dict:
        t = theme_colors(theme, self.brand)
        need_cfg = {k: self.cfg.get(k) for k in ("min_contrast", "min_contrast_large", "large_px")}
        need = need_cfg["min_contrast_large"] if size >= need_cfg["large_px"] else need_cfg["min_contrast"]
        text = t["text"]
        if contrast(text, t["bg"]) < need:
            try:
                name, _ = pick_text_color(t["bg"], [("ink", self.brand.ink), ("white", self.brand.white)], size, need_cfg)
                text = self.brand.ink if name == "ink" else self.brand.white
            except ValueError as e:
                self.err(f"theme {theme}: {e}")
        accent = t["accent"] if contrast(t["accent"], t["bg"]) >= 3.0 else text
        return {"bg": t["bg"], "text": text, "accent": accent}

    def text_el(self, sid, n, scene_type, element, text, theme, *, reveal="none", tokens=None, emphasis=None,
                appear=None, box_w=None, x=None, y=None, anchor="center", name=None) -> dict | None:
        role = role_of(scene_type, element)
        hi, lo = self.fmt["sizes"][role]
        box = int(box_w or self.fmt["text_box_w"])
        f = fit(text, self.fonts[role]["file"], box, (hi, lo), MAX_LINES[role],
                index=self.fonts[role].get("index", 0))
        if not f["ok"]:
            self.err(f"{sid}: «{text[:40]}» is too long for the scene ({max(f['widths']):.0f} px > {box} px even at "
                     f"{lo} px): shorten it or split the scene")
            return None
        px, py = place(scene_type, element, self.fmt, self.direction)
        col = self.colors(theme, f["size"])
        toks = tokens or []
        return {"kind": "text", "name": name or f"{sid}_{element}_{n}", "role": role, "lines": f["lines"],
                "text": "\r".join(f["lines"]), "size": f["size"], "font_ps": self.fonts[role]["ps"],
                "color": _f01(col["text"]), "accent": _f01(col["accent"]), "x": round(px if x is None else x, 1),
                "y": round(py if y is None else y, 1), "rtl": bool(ARABIC.search(text)), "anchor": anchor,
                "reveal": reveal, "tokens": toks, "emphasis": emphasis or [], "appear_frame": appear,
                "cue_hash": _hash([t["cue_frame"] for t in toks]) if toks else None}

    def icon_el(self, sid, name, theme, size=None, x=None, y=None, appear=None, mirror=None, scene_type="icon_point",
                element="icon") -> dict | None:
        from .motion_icons import closest, icon_shapes, load_index, should_mirror
        if name not in load_index():
            self.err(f"{sid}: unknown icon {name!r} (closest: {', '.join(closest(name))}; `reel motion-icons --search …`)")
            return None
        size = size or int(self.fmt["w"] * 0.22)
        mir = should_mirror(name, self.direction) if mirror is None else bool(mirror and self.direction == "rtl")
        px, py = place(scene_type, element, self.fmt, self.direction)
        col = self.colors(theme, 200)
        self.assets.append({"ref": f"lucide:{name}", "license": "ISC", "attribution": ""})
        return {"kind": "icon", "name": f"{sid}_icon_1", "icon": name, "shapes": icon_shapes(name, size, mir),
                "size": size, "stroke": round(size / 12, 1), "x": round(px if x is None else x, 1),
                "y": round(py if y is None else y, 1), "mirror": mir, "color": _f01(col["accent"]),
                "draw_on_frame": appear}

    # ------------------------------------------------------------------ scenes
    def build_scene(self, sc: dict, an: dict, theme: str) -> tuple[list[dict], list[int]]:
        sid, typ = sc["id"], sc["type"]
        a_ms, b_ms = an["start_ms"], an["end_ms"]
        pool, core = self.pool(a_ms, b_ms), self.pool(a_ms, b_ms, slack=False)
        els, cues_ms = [], []

        def add(e):
            if e:
                els.append(e)

        def either(field, text, element, **kw):
            if source_of(sc, field) == "speech":
                toks = self.speech(sid, field, text, pool)
                if toks is None:
                    return None
                cues_ms.extend(self._ms_of(t) for t in toks)       # hero frame and too-short check see these words
                return self.text_el(sid, 1, typ, element, text, theme, tokens=toks, reveal="word", **kw)
            return self.text_el(sid, 1, typ, element, self.editorial_text(sid, field, text), theme, **kw)

        if typ in ("kinetic_quote", "quote_card"):
            toks = self.speech(sid, "text", sc["text"], pool, replay=True, core=core)
            if toks is not None:
                cues_ms += [self._ms_of(t) for t in toks]
                emph = []
                for w in sc.get("emphasis") or []:
                    k = next((i for i, t in enumerate(toks, 1) if norm(t["text"]) == norm(w)), None)
                    if k is None:
                        self.err(f"{sid}: emphasis word «{w}» is not in the text")
                    elif k not in emph:
                        emph.append(k)
                reveal = "line" if typ == "quote_card" else (sc.get("reveal") or self.rm.get("reveal", "word"))
                e = self.text_el(sid, 1, typ, "text", sc["text"], theme, tokens=toks, emphasis=emph, reveal=reveal)
                if e and reveal == "line":
                    e["line_cues"], k = [], 0
                    for ln in e["lines"]:
                        e["line_cues"].append(toks[min(k, len(toks) - 1)]["cue_frame"])
                        k += len(ln.split())
                add(e)
            if typ == "quote_card":
                who = sc.get("attribution")
                name = person_name(self.sheet.get(who)) if who in ("host", "guest") else ""
                if not name:
                    self.err(f"{sid}: attribution {who!r} has no name in the episode sheet")
                else:
                    add(self.text_el(sid, 1, typ, "attribution", f"— {name}", theme))
        elif typ == "title_card":
            add(either("title", sc["title"], "title"))
            for fld in ("eyebrow", "subtitle"):
                if sc.get(fld):
                    add(self.text_el(sid, 1, typ, fld, self.editorial_text(sid, fld, sc[fld]), theme))
        elif typ == "stat_counter":
            k = self.find_at(sc["evidence"], pool)
            if k is None:
                self.err(f"{sid}: evidence «{sc['evidence']}» is not said in this scene")
            else:
                cues_ms.append(self.words[k]["start_ms"])
                if not check_number(sc["value"], sc["evidence"]):
                    self.approvals.append(f"{sid}: number {sc['value']} written from the spoken words «{sc['evidence']}»"
                                          " — confirm it")
                add(self._counter(sid, sc, theme, self.frame(self.words[k]["start_ms"])))
            if sc.get("label"):
                add(either("label", sc["label"], "label"))
            if sc.get("icon"):
                add(self.icon_el(sid, sc["icon"], theme, scene_type="stat_counter", element="icon",
                                 size=int(self.fmt["w"] * 0.12), mirror=sc.get("mirror")))
        elif typ == "icon_point":
            add(self.icon_el(sid, sc["icon"], theme, mirror=sc.get("mirror")))
            add(either("text", sc["text"], "text"))
        elif typ == "list_steps":
            self._list(sid, sc, theme, pool, els, cues_ms)
        elif typ == "comparison":
            self._comparison(sid, sc, theme, pool, els)
        elif typ == "timeline":
            self._timeline(sid, sc, theme, pool, els, cues_ms)
        elif typ == "context_card":
            add(self.text_el(sid, 1, typ, "text", self.editorial_text(sid, "text", sc["text"]), theme))
        elif typ == "person_card":
            self._person(sid, sc, theme, els)
        elif typ == "illustration_scene":
            self._illustration(sid, sc, theme, els)
            if sc.get("text"):
                add(either("text", sc["text"], "text"))
        elif typ == "outro":
            self._outro(sid, sc, theme, els)
        return els, sorted(set(cues_ms))

    def _ms_of(self, tok: dict) -> int:
        wid = tok.get("word_id")
        w = next((x for x in self.words if x.get("id") == wid), None)
        return w["start_ms"] if w else 0

    def _counter(self, sid, sc, theme, from_frame) -> dict | None:
        v = str(sc["value"])
        m = NUM_IN.search(v.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
        if not m:
            self.err(f"{sid}: value {v!r} has no number to count")
            return None
        num = re.sub(r"[,٬]", "", m.group(0)).replace("٫", ".")
        target = float(num) if "." in num else int(num)
        suffix = v[m.end():] + (f" {sc['unit']}" if sc.get("unit") else "")
        text = v + (f" {sc['unit']}" if sc.get("unit") else "")
        e = self.text_el(sid, 1, "stat_counter", "value", text, theme)
        if not e:
            return None
        e.update(kind="counter", name=f"{sid}_counter_1", target=target, prefix=v[:m.start()], suffix=suffix,
                 group=bool(re.search(r"[,٬]", m.group(0))), decimals=len(num.split(".")[1]) if "." in num else 0,
                 digits="arabic_indic" if re.search("[٠-٩]", v) else "western", from_frame=from_frame,
                 to_frame=from_frame + ms_to_frame(800, self.fps))
        return e

    def _list(self, sid, sc, theme, pool, els, cues_ms):
        items = sc.get("items") or []
        if sc.get("title"):
            e = self.text_el(sid, 1, "list_steps", "title", self.editorial_text(sid, "title", sc["title"]), theme)
            if e:
                els.append(e)
        x0, y0 = place("list_steps", "number", self.fmt, self.direction)
        usable = self.fmt["w"] - 2 * self.fmt["safe"]["side"]
        bottom = self.fmt["h"] - self.fmt["safe"]["bottom"]
        after, y, ats = -1, y0, []
        for it in items:
            k = self.find_at(it.get("at", ""), pool, after)
            if k is None:
                self.err(f"{sid}: item «{it.get('text', '')[:30]}» — its `at` words «{it.get('at')}» are not said here "
                         "(in order)")
            ats.append(k)
            after = k if k is not None else after
        for n, (it, k) in enumerate(zip(items, ats), 1):
            if k is None:
                continue
            nxt = next((a for a in ats[n:] if a is not None), None)
            sub = [i for i in pool if i >= k and (nxt is None or i < nxt)]
            toks = self.speech(sid, f"items[{n - 1}]", it["text"], sub or pool)
            if toks is None:
                continue
            cue = self.frame(self.words[k]["start_ms"])
            cues_ms.append(self.words[k]["start_ms"])
            item = self.text_el(sid, n, "list_steps", "item", it["text"], theme, tokens=toks, reveal="item",
                                appear=cue, box_w=usable - 150, x=x0 + self.dir * 90, y=y, anchor="start",
                                name=f"{sid}_item_{n}")
            num = self.text_el(sid, n, "list_steps", "number", str(n), theme, appear=cue, x=x0, y=y,
                               name=f"{sid}_number_{n}")
            if not item or not num:
                continue
            num["color"] = num["accent"]
            els += [num, item]
            y += item["size"] * 1.3 * len(item["lines"]) + 40
            if y > bottom:
                self.err(f"{sid}: the items do not fit above the bottom safe area: fewer or shorter items")
                break

    def _comparison(self, sid, sc, theme, pool, els):
        usable = self.fmt["w"] - 2 * self.fmt["safe"]["side"]
        for side in ("first", "second"):
            part = sc.get(side) or {}
            x, y = place("comparison", side, self.fmt, self.direction)
            box = usable / 2 - 40
            texts = [("label", part.get("label", ""))] + [(f"points[{k}]", p) for k, p in enumerate(part.get("points") or [])]
            for n, (fld, t) in enumerate([x_ for x_ in texts if x_[1]], 1):
                if source_of(sc, f"{side}.label") == "speech":
                    toks = self.speech(sid, f"{side}.{fld}", t, pool)
                    if toks is None:
                        continue
                    shown = t
                else:
                    shown = self.editorial_text(sid, f"{side}.{fld}", t)
                e = self.text_el(sid, n, "comparison", side, shown, theme, box_w=box, x=x,
                                 y=y + (n - 1) * self.fmt["sizes"]["body"][0] * 1.6, name=f"{sid}_{side}_{n}")
                if e:
                    if n == 1:
                        e["color"] = e["accent"]
                    els.append(e)
        if sc.get("verdict"):
            if source_of(sc, "verdict") == "speech":       # not said: that error only, never an editorial line too
                v = sc["verdict"] if self.speech(sid, "verdict", sc["verdict"], pool) is not None else None
            else:
                v = self.editorial_text(sid, "verdict", sc["verdict"])
            e = self.text_el(sid, 1, "comparison", "verdict", v, theme) if v else None
            if e:
                els.append(e)

    def _timeline(self, sid, sc, theme, pool, els, cues_ms):
        pts = sc.get("points") or []
        side = self.fmt["safe"]["side"] + 40
        x_start = self.fmt["w"] - side if self.direction == "rtl" else side
        span = self.fmt["w"] - 2 * side
        ly = place("timeline", "line", self.fmt, self.direction)[1]
        col = self.colors(theme, 64)
        cues, after = [], -1
        for n, p in enumerate(pts, 1):
            k = self.find_at(p.get("at", ""), pool, after)
            if k is None:
                self.err(f"{sid}: point «{p.get('label', '')[:30]}» — its `at` words are not said here (in order)")
                continue
            after = k
            cue = self.frame(self.words[k]["start_ms"])
            cues.append(cue)
            cues_ms.append(self.words[k]["start_ms"])
            x = x_start + self.dir * (n - 1) * span / max(1, len(pts) - 1)
            box = max(200, span / max(1, len(pts) - 1) * 0.9)
            toks = self.speech(sid, f"points[{n - 1}].label", p["label"], pool)
            if toks is not None:
                lab = self.text_el(sid, n, "timeline", "label", p["label"], theme, tokens=toks, reveal="item", appear=cue,
                                   box_w=box, x=x, name=f"{sid}_label_{n}")
                if lab:
                    els.append(lab)
            if p.get("when"):
                fld = f"points[{n - 1}].when"
                if digit_runs(p["when"]) and not check_number(p["when"], p.get("at", "")):
                    self.approvals.append(f"{sid}: number {p['when']} in {fld} written from the spoken words "
                                          f"«{p.get('at', '')}» — confirm it")
                wh = self.text_el(sid, n, "timeline", "when", self.editorial_text(sid, fld, p["when"], digits_ok=True),
                                  theme, appear=cue, box_w=box, x=x, name=f"{sid}_when_{n}")
                if wh:
                    wh["color"] = wh["accent"]
                    els.append(wh)
            els.append({"kind": "dot", "name": f"{sid}_dot_{n}", "x": round(x, 1), "y": ly, "r": 18,
                        "color": _f01(col["accent"]), "appear_frame": cue})
        if cues:
            els.insert(0, {"kind": "line", "name": f"{sid}_line_1", "from": [x_start, ly],
                           "to": [x_start + self.dir * span, ly], "width": 6, "color": _f01(col["text"]),
                           "draw_frames": [None, cues[-1]]})

    def _manifest(self) -> list[dict]:
        from . import client_db
        return (client_db.load(self.paths, "asset-manifest.json", {"assets": []}) or {}).get("assets", [])

    def _client_file(self, a: dict) -> str | None:
        """The file of an asset manifest entry for the comp: its display copy, else its own file, both through
        client_db (never a raw `root / rel`, review d224a9a P2-1); None when it is missing or its final real path is
        outside the client (client_db.inside_file, review c84f652 P2)."""
        from . import client_db
        p = a.get("display_derivative") or client_db.resolve(self.paths.root, a.get("rel"))
        return client_db.inside_file(self.paths.root, p)

    def _person(self, sid, sc, theme, els):
        who = sc.get("who")
        raw = str(self.sheet.get(who) or "") if who in ("host", "guest") else ""
        name = person_name(raw)
        if not name:
            self.err(f"{sid}: person_card {who!r} has no name in the episode sheet")
            return
        role = re.split(r"\s+[—–-]\s+", raw, maxsplit=1)[1].strip() if re.search(r"\s+[—–-]\s+", raw) else ""
        if sc.get("photo"):
            a = next((x for x in self._manifest() if x.get("rel") == sc["photo"]), None)
            f = self._client_file(a) if a else None
            if not a:
                self.err(f"{sid}: photo {sc['photo']!r} is not in the client's asset manifest (run `reel client-db`)")
            elif not f:
                self.err(f"{sid}: photo {sc['photo']!r} is missing or outside the client folder: put it under assets/ "
                         f"and run `reel client-db` (الصورة {sc['photo']} مش موجودة أو برة فولدر العميل: حطّها جوّه "
                         "assets/ وشغّل reel client-db)")
            else:
                x, y = place("person_card", "photo", self.fmt, self.direction)
                d = int(self.fmt["w"] * 0.42)
                els.append({"kind": "image", "name": f"{sid}_image_1", "path": f,
                            "x": x, "y": y, "w": d, "h": d, "radius": d / 2})
                self.assets.append({"ref": a["rel"], "license": "client", "attribution": ""})
        for n, (el, t) in enumerate((("name", name), ("role", role)), 1):
            if t:
                e = self.text_el(sid, n, "person_card", el, t, theme)
                if e:
                    els.append(e)

    def _illustration(self, sid, sc, theme, els):
        from .motion_library import resolve
        try:
            r = resolve(sc["illustration"])
        except ValueError as e:
            self.err(f"{sid}: {e}")
            return
        x, y = place("illustration_scene", "image", self.fmt, self.direction)
        size = int(self.fmt["w"] * 0.6)
        if r["kind"] == "png":
            els.append({"kind": "image", "name": f"{sid}_image_1", "path": r["path"], "x": x, "y": y, "w": size, "h": size,
                        "radius": 0})
        else:
            from .motion_icons import svg_to_shapes
            col = self.colors(theme, 200)
            els.append({"kind": "vector", "name": f"{sid}_vector_1", "shapes": svg_to_shapes(Path(r["path"]).read_text(
                encoding="utf-8"), size), "x": x, "y": y, "size": size, "fill": _f01(col["accent"])})
        self.assets.append({"ref": sc["illustration"], "license": r["license"], "attribution": r["attribution"]})

    def _outro(self, sid, sc, theme, els):
        logo = next((a for a in self._manifest() if a.get("category") == "logo"), None)
        f = self._client_file(logo) if logo and sc.get("show_logo", True) else None
        if logo and sc.get("show_logo", True) and not f:
            self.warnings.append(f"{sid}: the client logo {logo.get('rel')!r} is missing or outside the client folder: "
                                 "the outro shows no logo. Put it under assets/ and run `reel client-db` (اللوجو "
                                 f"{logo.get('rel')} مش موجود أو برة فولدر العميل: الختام من غير لوجو. حطّه جوّه "
                                 "assets/ وشغّل reel client-db)")
        if f:
            x, y = place("outro", "logo", self.fmt, self.direction)
            w = int(self.fmt["w"] * 0.35)
            els.append({"kind": "image", "name": f"{sid}_image_1", "path": f, "x": x, "y": y, "w": w, "h": w,
                        "radius": 0, "fit": "contain"})
        e = self.text_el(sid, 1, "outro", "cta", self.editorial_text(sid, "cta", sc["cta"]), theme)
        if e:
            els.append(e)
        show = str(self.sheet.get("show") or "").strip()
        if show and sc.get("show_name", True) and (not e or show not in " ".join(e.get("lines") or [])):
            e = self.text_el(sid, 1, "outro", "show", show, theme)
            if e:
                els.append(e)

    # ------------------------------------------------------------------ persistent layers
    def captions(self, scenes: list[dict], modes: list[str], theme: str) -> dict | None:
        """modes: per scene, "subtitles" or "off" (the scene's own `captions`, else the video's; spec §3.4)."""
        if "subtitles" not in modes:
            return None
        from . import srt as srtlib
        f = self.paths.p("02_transcription/captions-short.srt")
        if not f.exists():
            self.warnings.append("captions requested but 02_transcription/captions-short.srt is missing")
            return None
        # hidden where captions are off and wherever the scene already shows the spoken words (quotes, list items,
        # timeline labels, speech text)
        blocked = [(s["start_frame"], s["end_frame"]) for s, m in zip(scenes, modes)
                   if m != "subtitles" or s["type"] in REPLAYS_SPEECH or s["type"] in ("list_steps", "timeline")
                   or any(e.get("tokens") for e in s["elements"])]
        cues = []
        for c in srtlib.read_srt(f):
            a, b = self.frame(c["start_ms"]), self.frame(c["end_ms"])
            for x, y in blocked:
                if x <= a < y:
                    a = y
                elif a < x < b:
                    b = x
            if b - a >= 6:
                cues.append({"text": c["text"].replace("\n", " "), "start_frame": a, "end_frame": b})
        col = self.colors(theme, self.fmt["sizes"]["caption"][0])
        h, s = self.fmt["h"], self.fmt["safe"]
        return {"cues": cues, "size": self.fmt["sizes"]["caption"][0], "font_ps": self.fonts["caption"]["ps"],
                "color": _f01(col["text"]), "y": h - s["bottom"] - 30, "x": self.fmt["w"] / 2,
                "box_w": self.fmt["text_box_w"]}

    def badge(self, theme: str) -> dict | None:
        if not self.rm.get("speaker_badge", True):
            return None
        sp = read_json(self.paths.p("00_inputs/speakers.json"), {}) or {}
        turns = badge_turns(self.rm, sp)
        if not turns:
            return None
        names = {r: person_name(self.sheet.get(r)) or ((sp.get("people") or {}).get(r) or {}).get("name")
                 for r in {t.get("speaker") for t in turns}}
        unnamed = sorted(str(r) for r, n in names.items() if not n)
        if unnamed:             # never a raw role id such as "guest_2" on screen (review a1c14fc P1-1): fail closed
            self.err(f"speaker badge: {', '.join(unnamed)} has no name in the episode sheet or in "
                     f"00_inputs/speakers.json people: add `{unnamed[0]}: <name>` to the episode sheet "
                     "(data/Episodes/<episode>.md), then run `reel episode-prep` and `reel motion-plan` again")
            return None
        segs = []
        for t in turns:
            a, b = self.frame(t["start_ms"]), self.frame(t["end_ms"])
            if b <= a:
                continue
            if segs and segs[-1]["name"] == names[t["speaker"]]:
                segs[-1]["end_frame"] = b
            else:
                segs.append({"name": names[t["speaker"]], "start_frame": a, "end_frame": b})
        x, y = place("_persistent", "badge", self.fmt, self.direction)
        col = self.colors(theme, 40)
        return {"segments": segs, "x": x, "y": y, "size": self.fmt["sizes"]["label"][1], "font_ps": self.fonts["label"]["ps"],
                "color": _f01(col["text"]), "accent": _f01(col["accent"])}


def compile_motion(paths, font_override: dict | None = None, write: bool = True) -> dict:
    """write=False compiles without touching the approved plan, validation, motion-plan.md or the status, and returns
    the plan as `plan_data` (motion-build's re-fit with a fallback font)."""
    from .reels import window_stale
    from .motion_config import is_motion
    if not is_motion(paths):
        raise SystemExit(f"{paths.video_id} is not a motion project (pick it with `reels-select --as motion`)")
    stale = window_stale(paths)
    if stale:
        raise SystemExit(stale)
    script = load_script(paths)
    C = _Compiler(paths, font_override)
    C.write = write
    out_val = paths.p("01_analysis/motion-validation.json")
    errs = check_fields(script, C.cfg)
    if errs:
        return _finish(paths, C, script, None, errs)
    anchored, errs = anchor_scenes(script["scenes"], C.words, dict(C.cfg, total_ms=C.total_ms))
    if errs:
        return _finish(paths, C, script, None, errs)
    beats = {b.get("id"): b.get("role") for b in script.get("beats") or []}
    g_theme = script.get("theme") or C.rm.get("theme", "dark")
    tms = C.cfg.get("transition_ms") or {}
    built = []
    for k, (sc, an) in enumerate(zip(script["scenes"], anchored)):
        theme = sc.get("theme") or g_theme
        els, cues_ms = C.build_scene(sc, an, theme)
        ttype = "cut" if k == 0 else (sc.get("transition_in") or C.rm.get("transition", "cut"))
        built.append((sc, dict(an, cues_ms=cues_ms), els, theme, ttype, ms_to_frame(int(tms.get(ttype, 0)), C.fps)))
    trans_next = [built[k + 1][5] if k + 1 < len(built) else 0 for k in range(len(built))]
    framed, ferrs = frame_scenes([b[1] for b in built], C.tmap, C.fps, C.cfg, trans_next)
    C.errors += ferrs
    scenes = []
    for (sc, an, els, theme, ttype, tfr), fr in zip(built, framed):
        start = fr["start_frame"]
        for n, e in enumerate(els):
            if e.get("appear_frame") is None and e.get("kind") not in ("line",):
                e["appear_frame"] = start + 4 + 4 * n
            if e.get("kind") == "icon" and e.get("draw_on_frame") is None:
                e["draw_on_frame"] = start + 4
            if e.get("kind") == "line":
                e["draw_frames"][0] = start + 4
            if e.get("kind") == "counter":
                e["to_frame"] = max(e["from_frame"] + 1, min(e["to_frame"], fr["hero_frame"] - 1))
        col = C.colors(theme, 64)
        scenes.append({"id": sc["id"], "type": sc["type"], "beat": sc.get("beat"), "beat_role": beats.get(sc.get("beat")),
                       "start_frame": start, "end_frame": fr["end_frame"], "hero_frame": fr["hero_frame"],
                       "transition_in": {"type": ttype, "frames": tfr}, "theme": theme,
                       "bg": _f01(col["bg"]), "elements": els, "recipe_note": sc.get("recipe_note", ""),
                       "sfx": list(sc.get("sfx") or []), "outro": bool(an.get("outro"))})
    _recipe_checks(C, scenes, script)
    return _finish(paths, C, script, scenes, [])


def scene_words(sc: dict) -> int:
    """Words a scene puts on screen, counted from its script fields (laid out or not)."""
    texts = [sc.get(k) for k in ("text", "title", "eyebrow", "subtitle", "label", "cta", "verdict")]
    texts += [f"{sc.get('value', '')} {sc.get('unit', '')}" if sc.get("type") == "stat_counter" else ""]
    texts += [it.get("text") for it in sc.get("items") or []]
    texts += [x for p in sc.get("points") or [] for x in (p.get("label"), p.get("when"))]
    for side in ("first", "second"):
        part = sc.get(side) or {}
        texts += [part.get("label")] + list(part.get("points") or [])
    return sum(len(str(t).split()) for t in texts if t)


def _recipe_checks(C: _Compiler, scenes: list[dict], script: dict):
    rm, fps = C.rm, C.fps
    grammar = rm.get("beats") or []
    mx = int(rm.get("max_words_on_screen", 12))
    by_id = {sc["id"]: sc for sc in script["scenes"]}
    for k, s in enumerate(scenes):
        warns = []
        words = scene_words(by_id[s["id"]])
        if words > mx * 1.5:
            C.err(f"{s['id']}: {words} words on screen (the {C.recipe_type} recipe allows {mx}; at most {int(mx * 1.5)}): "
                  "split the scene")
        elif words > mx:
            warns.append(f"{s['id']}: {words} words on screen (the {C.recipe_type} recipe aims for ≤ {mx})")
        if not s["outro"] and rm.get("scene_s"):
            d = (s["end_frame"] - s["start_frame"]) / fps
            lo, hi = rm["scene_s"].get("min", 0), rm["scene_s"].get("max", 999)
            if d < lo or d > hi:
                warns.append(f"{s['id']}: {d:.1f} s (the {C.recipe_type} recipe keeps scenes {lo}-{hi} s)")
        if s["type"] in (rm.get("avoid") or []):
            warns.append(f"{s['id']}: {s['type']} is avoided in {C.recipe_type} videos")
        if s.get("beat_role") and grammar and s["beat_role"] not in grammar:
            warns.append(f"{s['id']}: beat {s['beat_role']!r} is not in the {C.recipe_type} beats ({', '.join(grammar)})")
        if k == 0 and s.get("beat_role") and grammar and s["beat_role"] != grammar[0]:
            warns.append(f"{s['id']}: the first scene usually carries the {grammar[0]!r} beat")
        emph = sum(len(e.get("emphasis") or []) for e in s["elements"])
        if emph > int(rm.get("emphasis_per_scene", 2)):
            warns.append(f"{s['id']}: {emph} emphasised words (recipe: {rm.get('emphasis_per_scene')})")
        if warns and s.get("recipe_note"):
            C.notes.append({"scene": s["id"], "note": s["recipe_note"], "silenced": warns})
        else:
            C.warnings += warns


def _audio(C: _Compiler, scenes: list[dict], script: dict, duration: int) -> dict:
    from .motion_audio import envelope, music_plan, sequence_dialogue, sfx_files, speech_frames
    dia = sequence_dialogue(C.paths, C.tmap)
    # T4.6: a licensed data/Music track (the script's choice, else the recipe's mood), ducked under the words; no
    # usable licence -> no music and one NEEDS-YOU item (never an invented licence, never a write into data/)
    mp = music_plan(C.paths.root, script.get("music"), C.src.get("recipe"), speech_frames(C.words, C.tmap), duration,
                    C.fps, drafts_dir=C.paths.p("06_audio/licence-drafts") if getattr(C, "write", True) else None)
    for e in mp["errors"]:
        C.err(e)
    C.warnings += mp["warnings"]
    C.needs_you = [n for n in getattr(C, "needs_you", []) if n.get("kind") != "music"] + mp["needs_you"]
    if mp["asset"]:
        C.assets.append(mp["asset"])
    music = mp["music"]
    cues = []
    tr = C.rm.get("sfx_on_transition")
    for k, s in enumerate(scenes):
        if tr and k > 0 and s["transition_in"]["frames"] > 0:
            cues.append((tr, s["start_frame"]))
        for kind in s.get("sfx") or []:
            cues.append((kind, s["start_frame"]))
        for rule in C.rm.get("sfx_rules") or []:
            on, kind = rule.get("on", ""), rule.get("kind")
            if on == f"beat:{s.get('beat_role')}" or on == f"type:{s['type']}":
                cues.append((kind, s["start_frame"]))
            elif on == "item":
                cues += [(kind, e["appear_frame"]) for e in s["elements"] if e["name"].startswith(f"{s['id']}_item_")]
            elif on == "count_end":
                cues += [(kind, e["to_frame"]) for e in s["elements"] if e.get("kind") == "counter"]
    from .sfx import RECIPES
    bad = sorted({k for k, _ in cues if k not in RECIPES})
    for k in bad:
        C.err(f"sfx {k!r} is not one of the built-in sounds ({', '.join(RECIPES)}); motion mode uses only the built-in "
              "procedural sounds, not the client's 06_audio/sfx-map.json library — use one of those kinds")
    files = sfx_files({k for k, _ in cues if k in RECIPES}, C.paths.p("06_audio/sfx"))
    return {"dialogue": str(dia), "music": music,
            "sfx": [{"kind": k, "file": str(files[k]), "frame": f} for k, f in sorted(cues, key=lambda c: c[1]) if k in files],
            "voice_values": envelope(dia, C.fps, duration)}


def _finish(paths, C: _Compiler, script: dict, scenes: list[dict] | None, early: list[str]) -> dict:
    C.errors = early + C.errors
    plan = None
    if scenes is not None:
        duration = max(s["end_frame"] for s in scenes)
        g_theme = script.get("theme") or C.rm.get("theme", "dark")
        video = _caption_mode(script.get("captions")) or _caption_mode(C.rm.get("captions", "off"))
        by_id = {sc["id"]: sc for sc in script["scenes"]}
        caps = C.captions(scenes, [_caption_mode(by_id[s["id"]].get("captions")) or video for s in scenes], g_theme)
        audio = _audio(C, scenes, script, duration)
        voice = audio.pop("voice_values")
        gcol = C.colors(g_theme, 64)
        plan = {"reel_id": paths.video_id, "format": C.fmt["name"], "w": C.fmt["w"], "h": C.fmt["h"],
                "safe": C.fmt["safe"], "fps": C.fps, "dir": C.dir, "direction": C.direction,
                "duration_frames": duration, "content_type": C.recipe_type, "recipe_motion": C.rm,
                "theme": {"name": g_theme, "bg": _f01(gcol["bg"]), "text": _f01(gcol["text"]), "accent": _f01(gcol["accent"])},
                "fonts": C.fonts, "scenes": scenes,
                "persistent": {"background": {"theme": g_theme}, "captions": caps, "speaker_badge": C.badge(g_theme),
                               "progress": bool(C.rm.get("progress")),
                               "voice_pulse": {"values": voice} if (C.rm.get("voice_pulse") or C.src.get("media") == "audio") else None},
                "audio": audio, "assets": _dedupe(C.assets), "editorial_lines": C.editorial, "approvals": C.approvals,
                "needs_you": list(getattr(C, "needs_you", [])),
                "generated": now_iso()}
        from .ae_builder import brand_controls
        plan["brand"] = brand_controls(paths.client_db)
    ok = not C.errors and plan is not None
    fp = fingerprint(paths)
    if plan is not None:
        plan["fingerprint"] = fp
        from .stamps import stamp
        plan = stamp(plan)
    if not getattr(C, "write", True):
        return {"ok": ok, "errors": C.errors, "warnings": C.warnings, "plan_data": plan}
    if plan is not None:
        write_json(paths.p("01_analysis/motion-plan.json"), plan)
    val = {"ok": ok, "errors": C.errors, "warnings": C.warnings, "approvals": C.approvals,
           "editorial_lines": C.editorial, "recipe_notes": C.notes, "fingerprint": fp,
           "plan_sha1": plan_sha1(paths) if plan is not None else None, "generated": now_iso()}
    write_json(paths.p("01_analysis/motion-validation.json"), val)
    md = write_motion_md(paths, plan, val, C)
    if ok:
        set_status(paths, "ANALYZED", f"motion plan compiled ({len(plan['scenes'])} scenes)", "motion_plan", [md])
    return dict(val, plan=str(paths.p("01_analysis/motion-plan.json")) if plan else None, md=str(md))


def _music_line(plan: dict) -> str:
    m = plan["audio"].get("music")
    if m:
        return (f"{m.get('rel') or Path(m['file']).name} at {m['level_db']} dB under the dialogue, ducked with "
                f"{len(m.get('keyframes') or [])} level keys ({(m.get('license') or {}).get('license', '?')})")
    need = next((n for n in plan.get("needs_you") or [] if n.get("kind") == "music"), None)
    return f"none — {need['text']}" if need else "none (off in the motion script)"


# review 91b6b44 P2-1: what the editor reads when the compiled plan is not the one `reel motion-plan` wrote
PLAN_EDITED = {"en": "The motion plan file was changed by hand after it was made. It has to be made again before anything "
                     "is built.",
               "ar": "ملف خطة الموشن اتعدّل بإيد بعد ما اتعمل. لازم يتعمل تاني قبل ما أي حاجة تتبني."}
PLAN_EDITED_WHY = ("01_analysis/motion-plan.json is not the plan `reel motion-plan` wrote (edited by hand, or compiled "
                   "by an older WhyNot Cut): run `reel motion-plan` again")


def plan_sha1(paths) -> str:
    """The sha1 of 01_analysis/motion-plan.json as it is on disk."""
    return hashlib.sha1(paths.p("01_analysis/motion-plan.json").read_bytes()).hexdigest()


def plan_edited(paths) -> str | None:
    """Review 91b6b44 P2-1: PLAN_EDITED_WHY when the compiled plan on disk is not the file `reel motion-plan` wrote
    (motion-validation.json `plan_sha1`, recorded when it was written; a record without one is from an older engine);
    None when it is, or when there is no compiled plan or validation to compare (the callers refuse those already).
    The approval binds the plan's inputs (fingerprint), and this binds the compiled file to them: a caption, name or
    any scene text edited straight in motion-plan.json never reaches a build with a current approval."""
    f = paths.p("01_analysis/motion-plan.json")
    val = read_json(paths.p("01_analysis/motion-validation.json"), {}) or {}
    if not f.exists() or not val:
        return None
    return None if val.get("plan_sha1") == plan_sha1(paths) else PLAN_EDITED_WHY


def _caption_mode(v: str | None) -> str | None:
    """A script/recipe `captions` value (checked: on|subtitles|off) as "subtitles" | "off"; None when not set."""
    return None if v is None else ("off" if v == "off" else "subtitles")


def _dedupe(assets: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in assets:
        if a["ref"] not in seen:
            seen.add(a["ref"])
            out.append(a)
    return out


def write_motion_md(paths, plan: dict | None, val: dict, C: _Compiler) -> Path:
    fps = C.fps
    L = [f"# Motion plan — {paths.video_id} (approve the plan before After Effects)", "",
         f"{C.recipe_type} · {C.fmt['name']} · {C.direction.upper()} · " +
         (f"{plan['duration_frames'] / fps:.1f} s · {len(plan['scenes'])} scenes" if plan else "not compiled"), ""]
    if val["errors"]:
        L += ["## Errors (fix before approval)", ""] + [f"- {e}" for e in val["errors"]] + [""]
    if plan:
        L += ["| Scene | Time | Beat | Type | On screen | Source |", "|---|---|---|---|---|---|"]
        eds = {(e["scene"], e["text"]) for e in val["editorial_lines"]}
        for s in plan["scenes"]:
            texts = [" ".join(e.get("text", "").split()) for e in s["elements"] if e.get("kind") in ("text", "counter")]
            icons = [e.get("icon") for e in s["elements"] if e.get("kind") == "icon"]
            srcs = ["editorial" if (s["id"], t) in eds else "speech" for t in texts]
            t0 = fmt_ts(int(s["start_frame"] * 1000 / fps), ".")[3:11]
            L.append(f"| {s['id']} | {t0} | {s.get('beat_role') or '—'} | {s['type']}"
                     f"{' (' + ', '.join(icons) + ')' if icons else ''} | {' / '.join(texts)[:120] or '—'} | "
                     f"{', '.join(sorted(set(srcs))) or '—'} |")
        # the table column is short; the reviewer (claims / religious content) reads the complete words here
        L += ["", "## On-screen text (full)", "",
              "Every scene's complete on-screen words, uncut (the table above shortens long lines).", ""]
        full = []
        for s in plan["scenes"]:
            for e in s["elements"]:
                if e.get("kind") in ("text", "counter") and e.get("text"):
                    who = "editorial" if (s["id"], e["text"]) in eds else "speech"
                    full.append(f"- {s['id']} · {who} · {' '.join(e['text'].split())}")
        L += full or ["- none"]
        L += ["", "## Editorial lines (Claude's words, not the speaker's)", ""]
        L += [f"- {e['scene']} {e['field']}: {e['text']}" for e in val["editorial_lines"]] or ["- none"]
        a = plan["audio"]
        L += ["", "## Audio", "", f"- Dialogue: pauses removed ({Path(a['dialogue']).name})",
              f"- Music: {_music_line(plan)}",
              f"- SFX: {', '.join(sorted({c['kind'] for c in a['sfx']})) or 'none'}"]
        if plan["assets"]:
            L += ["", "## Assets and licenses", ""] + [f"- {x['ref']} ({x['license']}){' — ' + x['attribution'] if x['attribution'] else ''}"
                                                       for x in plan["assets"]]
    if val["approvals"]:
        L += ["", "## Needs the editor's confirmation", ""] + [f"- {x}" for x in val["approvals"]]
    if val["recipe_notes"]:
        L += ["", "## Recipe deviations (noted)", ""] + [f"- {n['scene']}: {n['note']}" for n in val["recipe_notes"]]
    if val["warnings"]:
        L += ["", "## Warnings", ""] + [f"- {w}" for w in val["warnings"]]
    anim = paths.p(f"08_quality_control/animatic/{paths.video_id}_animatic.mp4")
    L += ["", f"Animatic: {anim if anim.exists() else 'not rendered yet (`reel motion-animatic`)'}", "",
          "**To approve:** the editor says so; the lead records `reel approve-plan --by editor`."]
    return write_text(paths.p("01_analysis/motion-plan.md"), "\n".join(L) + "\n")
