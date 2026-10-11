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
SYSTEM_FONTS = ("arial.ttf", "segoeui.ttf", "tahoma.ttf", "dejavusans.ttf", "notosansarabic-regular.ttf")
NEAREST = {"headline": ["black", "heavy", "extrabold", "bold", "semibold", "medium", "regular"],
           "caption": ["bold", "semibold", "extrabold", "black", "medium", "regular"],
           "body": ["medium", "regular", "book", "semibold", "light", "bold"],
           "small": ["regular", "book", "medium", "light", "semibold"]}


def _f01(rgb) -> list:
    return [round(c / 255, 4) for c in rgb[:3]]


def _hash(frames: list[int]) -> str:
    return hashlib.sha1(json.dumps(frames).encode()).hexdigest()[:12]


def _system_font() -> str | None:
    from .plat import font_dirs
    for d in font_dirs():
        if d.exists():
            for f in sorted(d.glob("*.ttf")):
                if f.name.lower() in SYSTEM_FONTS:
                    return str(f)
    return None


def fingerprint(paths) -> str:
    """Changes when anything the compiled plan depends on changes (script, words, pauses, recipe, motion.json, brand)."""
    src = msource(paths)
    h = hashlib.sha1()
    for rel in ("01_analysis/motion-script.json", "02_transcription/words.json", "06_audio/dialogue/pauses.json"):
        f = paths.p(rel)
        h.update(f.read_bytes() if f.exists() else b"-")
    bt = paths.client_db / "branding/brand-tokens.json"
    h.update(bt.read_bytes() if bt.exists() else b"-")
    h.update(json.dumps([src.get("recipe"), src.get("format"), src.get("direction"), motion_cfg()], sort_keys=True,
                        ensure_ascii=True).encode())
    return h.hexdigest()


class _Compiler:
    def __init__(self, paths, font_override: dict | None = None):
        from .episode import EpisodePaths, load_episode
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
            raise SystemExit("02_transcription/words.json missing — the motion project's transcript is sliced at Gate 0")
        self.total_ms = int(self.src.get("duration_ms") or self.words[-1]["end_ms"])
        pz = read_json(paths.p("06_audio/dialogue/pauses.json"))
        if not pz:
            raise SystemExit("06_audio/dialogue/pauses.json missing — run `reel audio-clean` for this motion project first")
        self.tmap = TimeMap(pz.get("keep_ms") or [[0, self.total_ms]])
        self.fps = seq_fps()
        try:
            self.sheet = (load_episode(EpisodePaths(paths.root, self.src["episode_id"])).get("sheet") or {})
        except (SystemExit, KeyError):
            self.sheet = {}
        self.window_digits = set().union(*(digit_runs(w["word"]) for w in self.words)) if self.words else set()
        self.brand = Brand(paths.client_db)
        self.font_override = font_override
        self.fonts = self._fonts()

    # ------------------------------------------------------------------ helpers
    def _fonts(self) -> dict:
        if self.font_override:               # the font After Effects will actually draw (e.g. an approved fallback)
            return {role: dict(self.font_override) for role in ROLE_FONT}
        from .ae_builder import fonts_map
        fm = fonts_map(self.paths.client_db)
        out, fallback = {}, None
        for role, brole in ROLE_FONT.items():
            style = self.brand.role_style.get(brole, "regular")
            # the wanted weight, else the nearest one the brand has: file and PostScript name always from the SAME weight
            order = [style] + NEAREST.get(brole, NEAREST["body"])
            pick = next((w for w in order if w in self.brand.files), next(iter(self.brand.files), None))
            f = self.brand.files.get(pick) if pick else None
            ps = (self.brand.ps_names.get(pick) if pick else None) or fm.get(brole) or ""
            if not ps:
                raise SystemExit(f"no PostScript font name for the {brole} role: run `reel client-db` (typography.json)")
            if not f or not Path(f).exists():
                fallback = fallback or _system_font()
                if not fallback:
                    raise SystemExit("no brand font file (run `reel client-db`) and no system font to measure text with")
                f = fallback
            out[role] = {"ps": ps, "file": str(f)}
        if fallback:
            self.warnings.append(f"brand font files not found: text measured with {Path(fallback).name}; After Effects "
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

    def editorial_text(self, sid: str, field: str, text: str) -> str:
        filled, missing = fill_placeholders(text, self.sheet)
        for m in missing:
            self.err(f"{sid}: {field} uses {{{m}}} but the episode sheet has no {m}")
        for p in check_editorial(filled, self.window_digits):
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
        f = fit(text, self.fonts[role]["file"], box, (hi, lo), MAX_LINES[role])
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
            v = sc["verdict"] if source_of(sc, "verdict") == "speech" and self.speech(sid, "verdict", sc["verdict"], pool) \
                else self.editorial_text(sid, "verdict", sc["verdict"])
            e = self.text_el(sid, 1, "comparison", "verdict", v, theme)
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
                wh = self.text_el(sid, n, "timeline", "when", self.editorial_text(sid, f"points[{n - 1}].when", p["when"]),
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
        return (read_json(self.paths.client_db / "asset-manifest.json", {"assets": []}) or {}).get("assets", [])

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
            if not a:
                self.err(f"{sid}: photo {sc['photo']!r} is not in the client's asset manifest (run `reel client-db`)")
            else:
                x, y = place("person_card", "photo", self.fmt, self.direction)
                d = int(self.fmt["w"] * 0.42)
                els.append({"kind": "image", "name": f"{sid}_image_1", "path": a.get("display_derivative") or str(self.paths.root / a["rel"]),
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
        if logo and sc.get("show_logo", True):
            x, y = place("outro", "logo", self.fmt, self.direction)
            w = int(self.fmt["w"] * 0.35)
            els.append({"kind": "image", "name": f"{sid}_image_1", "path": logo.get("display_derivative") or
                        str(self.paths.root / logo["rel"]), "x": x, "y": y, "w": w, "h": w, "radius": 0, "fit": "contain"})
        e = self.text_el(sid, 1, "outro", "cta", self.editorial_text(sid, "cta", sc["cta"]), theme)
        if e:
            els.append(e)
        show = str(self.sheet.get("show") or "").strip()
        if show and sc.get("show_name", True) and (not e or show not in " ".join(e.get("lines") or [])):
            e = self.text_el(sid, 1, "outro", "show", show, theme)
            if e:
                els.append(e)

    # ------------------------------------------------------------------ persistent layers
    def captions(self, scenes: list[dict], mode: str, theme: str) -> dict | None:
        if mode != "subtitles":
            return None
        from . import srt as srtlib
        f = self.paths.p("02_transcription/captions-short.srt")
        if not f.exists():
            self.warnings.append("captions requested but 02_transcription/captions-short.srt is missing")
            return None
        # hidden wherever the scene already shows the spoken words (quotes, list items, timeline labels, speech text)
        blocked = [(s["start_frame"], s["end_frame"]) for s in scenes
                   if s["type"] in REPLAYS_SPEECH or s["type"] in ("list_steps", "timeline")
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
        turns = sp.get("turns") or []
        if len({t.get("speaker") for t in turns}) < 2:
            return None
        names = {r: person_name(self.sheet.get(r)) or ((sp.get("people") or {}).get(r) or {}).get("name") or r
                 for r in {t.get("speaker") for t in turns}}
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


def compile_motion(paths, font_override: dict | None = None) -> dict:
    from .reels import window_stale
    from .motion_config import is_motion
    if not is_motion(paths):
        raise SystemExit(f"{paths.video_id} is not a motion project (pick it with `reels-select --as motion`)")
    stale = window_stale(paths)
    if stale:
        raise SystemExit(stale)
    script = load_script(paths)
    C = _Compiler(paths, font_override)
    out_val = paths.p("01_analysis/motion-validation.json")
    errs = check_fields(script)
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
    from .motion_audio import envelope, sequence_dialogue, sfx_files
    dia = sequence_dialogue(C.paths, C.tmap)
    music = None
    m = script.get("music") or {}
    if m.get("file"):
        f = (C.paths.root / m["file"]).resolve()
        music_dir = (C.paths.root / "data" / "Music").resolve()
        if not f.exists() or not f.is_relative_to(music_dir):
            C.err(f"music {m['file']!r} must be a licensed file under data/Music")
        else:
            music = {"file": str(f), "level_db": float(m.get("level_db", (C.src.get("recipe") or {}).get("music", {}).get("level_db", -24))),
                     "fade_out_frames": ms_to_frame(2000, C.fps)}
    else:
        C.warnings.append("no music: the music bed stays for the editor (licensed tracks: `reel music --list`)")
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
        C.err(f"sfx {k!r} cannot be synthesised (kinds: {', '.join(RECIPES)})")
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
        caps = C.captions(scenes, script.get("captions") or C.rm.get("captions", "off"), g_theme)
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
                "generated": now_iso()}
        from .ae_builder import brand_controls
        plan["brand"] = brand_controls(paths.client_db)
    ok = not C.errors and plan is not None
    fp = fingerprint(paths)
    if plan is not None:
        plan["fingerprint"] = fp
        write_json(paths.p("01_analysis/motion-plan.json"), plan)
    val = {"ok": ok, "errors": C.errors, "warnings": C.warnings, "approvals": C.approvals,
           "editorial_lines": C.editorial, "recipe_notes": C.notes, "fingerprint": fp, "generated": now_iso()}
    write_json(paths.p("01_analysis/motion-validation.json"), val)
    md = write_motion_md(paths, plan, val, C)
    if ok:
        set_status(paths, "ANALYZED", f"motion plan compiled ({len(plan['scenes'])} scenes)", "motion_plan", [md])
    return dict(val, plan=str(paths.p("01_analysis/motion-plan.json")) if plan else None, md=str(md))


def _dedupe(assets: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in assets:
        if a["ref"] not in seen:
            seen.add(a["ref"])
            out.append(a)
    return out


def write_motion_md(paths, plan: dict | None, val: dict, C: _Compiler) -> Path:
    fps = C.fps
    L = [f"# Motion plan — {paths.video_id} (Gate 1: approve before After Effects)", "",
         f"{C.recipe_type} · {C.fmt['name']} · {C.direction.upper()} · " +
         (f"{plan['duration_frames'] / fps:.1f} s · {len(plan['scenes'])} scenes" if plan else "not compiled"), ""]
    if val["errors"]:
        L += ["## Errors (fix before approval)", ""] + [f"- {e}" for e in val["errors"]] + [""]
    if plan:
        L += ["| Scene | Time | Beat | Type | On screen | Source |", "|---|---|---|---|---|---|"]
        eds = {(e["scene"], e["text"]) for e in val["editorial_lines"]}
        for s in plan["scenes"]:
            texts = [e.get("text", "").replace("\r", " ") for e in s["elements"] if e.get("kind") in ("text", "counter")]
            icons = [e.get("icon") for e in s["elements"] if e.get("kind") == "icon"]
            srcs = ["editorial" if (s["id"], t) in eds else "speech" for t in texts]
            t0 = fmt_ts(int(s["start_frame"] * 1000 / fps), ".")[3:11]
            L.append(f"| {s['id']} | {t0} | {s.get('beat_role') or '—'} | {s['type']}"
                     f"{' (' + ', '.join(icons) + ')' if icons else ''} | {' / '.join(texts)[:120] or '—'} | "
                     f"{', '.join(sorted(set(srcs))) or '—'} |")
        L += ["", "## Editorial lines (Claude's words, not the speaker's)", ""]
        L += [f"- {e['scene']} {e['field']}: {e['text']}" for e in val["editorial_lines"]] or ["- none"]
        a = plan["audio"]
        L += ["", "## Audio", "", f"- Dialogue: pauses removed ({Path(a['dialogue']).name})",
              f"- Music: {Path(a['music']['file']).name + ' at ' + str(a['music']['level_db']) + ' dB' if a['music'] else 'none — for the editor'}",
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
