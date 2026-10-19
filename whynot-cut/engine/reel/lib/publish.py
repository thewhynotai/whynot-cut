"""Podcast mode: the PUBLISH PACKAGE of an episode — YouTube titles/description/chapters/tags/SRT for the episode,
captions and hashtags for each reel (Instagram, TikTok, YouTube Shorts) and thumbnail designs.

The copy is authored by the publish-writer agent (publish/publish.json, publish/reels/<REEL>.json); this module
checks it against platform limits (config/defaults/platform-limits.json) and the episode's own facts, then renders
the files the editor copies from. Nothing is uploaded anywhere.
  * every URL must appear in the episode sheet (names and links are never invented)
  * every quoted line («…» or “…”) must be the speaker's words (found in the transcript); straight "…" marks emphasis
    or a term in copy, so it is not checked
  * an honorific next to a person's name agrees with that person's gender in the profile's people[] (lib/people.py)
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .common import fmt_ts, load_config, now_iso, read_json, write_json, write_text

QUOTE = re.compile(r"«([^»]+)»|“([^”]+)”")
HASHTAG = re.compile(r"#[^\s#]+")
URL = re.compile(r"(?:https?://|www\.)[^\s<>«»\"'()]+|(?<![@\w.])(?P<host>(?:[a-z0-9-]+\.)+[a-z]{2,})(?:/[^\s<>«»\"'()]*)?",
                 re.I)
TLDS = {"com", "net", "org", "io", "me", "tv", "co", "ai", "eg", "sa", "ae", "ly", "gg", "app", "link", "page",
        "be", "ee", "gl", "dev", "info", "uk"}           # youtu.be, linktr.ee, goo.gl ...
SLDS = {"co", "com", "net", "org", "ac", "gov", "edu"}  # second-level labels under a country code (example.co.uk)


def limits() -> dict:
    return load_config("platform-limits.json")


# --------------------------------------------------------------------------- helpers
def parse_time(v) -> int:
    """'00:40', '1:02:03', '00:00:40.500', 40.5 -> ms (a bare number is seconds): media_util.parse_time."""
    from .media_util import parse_time as _pt
    return _pt(v)


def fmt_chapter(ms: int, first: bool = False) -> str:
    if first:
        return "00:00"
    s = int(ms // 1000)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def norm_url(u: str) -> str:
    """Comparable form: no scheme, no www., lower-case, no trailing punctuation or slash."""
    u = str(u or "").strip().strip("()<>«»\"'")
    u = re.sub(r"^[a-z][a-z0-9+.-]*://", "", u, flags=re.I)
    u = re.sub(r"^www\.", "", u, flags=re.I)
    return u.rstrip(".,;:!?)»\"'/").lower()


def _bare_host(host: str) -> str | None:
    """The dotted name when it ends in a known TLD, or a second-level label + a 2-letter country code (example.co.uk,
    shop.com.eg); None for file names and the like (notes.txt, file.app.js)."""
    def site(ls: list) -> bool:
        last = ls[-1].lower()
        return last in TLDS or (len(ls) > 2 and len(last) == 2 and ls[-2].lower() in SLDS)
    labels = host.split(".")
    if site(labels):
        return host
    while len(labels) > 2 and labels[-1][:1].isupper():     # "example.com.Then": the next sentence, missing a space
        labels = labels[:-1]
        if site(labels):
            return ".".join(labels)
    return None


def urls_in(text: str) -> list[str]:
    out = []
    for m in URL.finditer(text or ""):
        if not m.group("host"):
            out.append(m.group(0))
            continue
        host = _bare_host(m.group("host"))
        if host:
            out.append(m.group(0) if host == m.group("host") else host)
    return out


def count_tags_chars(tags: list[str]) -> int:
    """YouTube's 500-character tag budget: tags joined by commas, a tag with a space counts its quotes."""
    tags = [str(t).strip() for t in tags if str(t).strip()]
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)


def chapters(ep, pub: dict) -> list[tuple[int, str]]:
    """YouTube chapters: publish.json youtube.chapters, else the episode-analyst's topic map."""
    from .plan import to_ms
    ch = (pub.get("youtube") or {}).get("chapters")
    if ch:
        return [(parse_time(c["at"]), str(c.get("title", "")).strip()) for c in ch]
    topics = (read_json(ep.p("01_analysis/topics.json"), {}) or {}).get("topics") or []
    return [(to_ms(t["start"]), str(t.get("title", "")).strip()) for t in topics]


def validate_chapters(chs: list, total_ms: int, lim: dict) -> list[str]:
    errs = []
    if not chs:
        return ["no chapters: add youtube.chapters or the topic map (01_analysis/topics.json)"]
    if chs[0][0] != 0:
        errs.append(f"the first chapter must start at 00:00 (it starts at {fmt_ts(chs[0][0], '.')})")
    if len(chs) < lim["chapters_min"]:
        errs.append(f"YouTube needs at least {lim['chapters_min']} chapters ({len(chs)} given)")
    for (a, t), nxt in zip(chs, chs[1:] + [(total_ms, None)]):
        if not t:
            errs.append(f"chapter at {fmt_chapter(a)} has no title")
        if nxt[0] <= a:
            errs.append(f"chapters are not in ascending order at {fmt_chapter(a)}")
        elif nxt[0] - a < lim["chapter_min_s"] * 1000:
            errs.append(f"chapter at {fmt_chapter(a)} is {(nxt[0] - a) / 1000:.0f} s (each must be >= {lim['chapter_min_s']} s)")
        if a >= total_ms:
            errs.append(f"chapter at {fmt_chapter(a)} is after the end of the episode")
    return errs


def assemble_description(pub: dict, chs: list, lang: str = "ar") -> str:
    d = (pub.get("youtube") or {}).get("description") or {}
    parts = [d.get("hook"), d.get("summary"), d.get("guest")]
    if chs:
        head = "الفصول" if lang == "ar" else "Chapters"
        parts.append(head + "\n" + "\n".join(f"{fmt_chapter(a, k == 0)} {t}" for k, (a, t) in enumerate(chs)))
    links = [f"{lk.get('label', '').strip()}: {lk.get('url', '').strip()}".strip(": ") for lk in d.get("links") or []]
    parts += ["\n".join(links) if links else None, d.get("sponsor"), d.get("cta"),
              " ".join(d.get("hashtags") or []) or None]
    return "\n\n".join(str(p).strip() for p in parts if p and str(p).strip())


# --------------------------------------------------------------------------- thumbnails
def _sharpness(gray) -> float:
    import numpy as np
    g = gray.astype(np.float32)
    lap = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]
    return float(lap.var())


def frame_at(src: Path, t_s: float, w: int, h: int):
    """One frame at t_s seconds, letterboxed into w x h RGB, or None past the end (media_util.grab_frame)."""
    from .media_util import grab_frame
    return grab_frame(src, t_s, w, h, fit="pad")


def thumbnail_candidates(ep, n: int = 12, faces_fn=None, every_s: float | None = None, min_gap_ms: int = 30000) -> dict:
    """Frames worth a thumbnail: sampled across the episode (about 150 samples, each one seek, so a 90-min episode
    takes seconds), kept only with a face, scored on face size, sharpness and contrast; the best n at least min_gap_ms
    apart, extracted at full resolution and labelled on publish/thumbnail/_candidates.jpg for the publish-writer."""
    from concurrent.futures import ThreadPoolExecutor
    import numpy as np
    from PIL import Image
    from .episode import episode_file, load_episode
    from .media_util import contact_sheet, grab_frame_file
    if faces_fn is None:
        from .shots import face_boxes as faces_fn
    info = load_episode(ep)
    src = episode_file(ep)
    dur_s = info["duration_ms"] / 1000
    step = float(every_s or max(10.0, dur_s / 150))
    W, H = 640, 360
    times = [k * step for k in range(int(dur_s / step) + 1) if k * step < dur_s]
    rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:            # a few ffmpeg seeks at a time
        for t, im in zip(times, pool.map(lambda t_: frame_at(src, t_, W, H), times)):
            faces = faces_fn(im) if im is not None else None
            if not faces:
                continue
            g = np.asarray(im.convert("L"))
            rows.append({"frame_ms": int(round(t * 1000)), "face": max(f[2] * f[3] for f in faces), "sharp": _sharpness(g),
                         "contrast": float(g.std()) / 128, "faces": len(faces)})

    def nz(key):
        vals = [r[key] for r in rows]
        lo, hi = (min(vals), max(vals)) if vals else (0, 1)
        for r in rows:
            r[key + "_n"] = (r[key] - lo) / (hi - lo) if hi > lo else 1.0
    for key in ("face", "sharp", "contrast"):
        nz(key)
    for r in rows:
        r["score"] = round(float(0.5 * r["face_n"] + 0.3 * r["sharp_n"] + 0.2 * r["contrast_n"]), 4)
    picked = []
    for r in sorted(rows, key=lambda r: -r["score"]):
        if all(abs(r["frame_ms"] - q["frame_ms"]) >= min_gap_ms for q in picked):
            picked.append(r)
        if len(picked) >= n:
            break
    picked.sort(key=lambda r: r["frame_ms"])
    d = ep.p("publish/thumbnail/candidates")
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("T*.jpg"):
        old.unlink()
    for i, r in enumerate(picked, 1):
        f = d / f"T{i:02d}_{r['frame_ms']}.jpg"
        grab_frame_file(src, r["frame_ms"] / 1000, f, quality=2)
        r.update(id=f"T{i:02d}", file=str(f))
    sheet = ep.p("publish/thumbnail/_candidates.jpg")
    if picked:
        blank = Image.new("RGB", (1, 1), "black")       # a frame ffmpeg could not write keeps its labelled cell
        contact_sheet([(r["file"] if Path(r["file"]).exists() else blank,
                        f"{r['id']}  {fmt_ts(r['frame_ms'], '.')[:8]}  score {r['score']}") for r in picked],
                      sheet, cols=4, tile_w=400, tile_h=225, label_h=24, fit="contain")
    res = {"generated": now_iso(), "sampled_every_s": step, "with_face": len(rows),
           "candidates": [{k_: r[k_] for k_ in ("id", "frame_ms", "score", "faces", "file")} for r in picked],
           "sheet": str(sheet) if picked else None}
    write_json(ep.p("publish/thumbnail/candidates.json"), res)
    return res


def _text_width(font, s: str) -> float:
    if getattr(font, "engine", None) in ("coretext", "harfbuzz"):
        return float(font.render(s, (255, 255, 255, 255))[2])
    from PIL import Image, ImageDraw
    from .previews import _shape
    return float(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(_shape(s), font=font))


def highlight_spans(text: str, phrase: str, boxes: list, font, max_chars: int) -> list[tuple[int, int, int, int]]:
    """Screen boxes of the words of `phrase` inside a text block drawn by previews._text_block (same wrap, one box per
    line). Arabic lines run right to left, so a word's offset is measured from the right edge (logical order: a run of
    several Latin words inside an Arabic line is laid out LTR, so their boxes would swap; one Latin word is fine)."""
    from .ae_builder import wrap_lines
    from .plan import norm
    font = font.for_text(text) if hasattr(font, "for_text") else font     # the font _text_block drew with (G72)
    want = set(norm(phrase).split())
    spans = []
    for line, (x0, y0, x1, y1) in zip(wrap_lines(text, max_chars).split("\r"), boxes):
        words = line.split(" ")
        rtl = bool(re.search("[؀-ۿ]", line))
        for k, w in enumerate(words):
            if not norm(w) or norm(w) not in want:
                continue
            before = _text_width(font, " ".join(words[:k]) + " ") if k else 0.0
            ww = _text_width(font, w)
            a = x1 - before - ww if rtl else x0 + before
            spans.append((int(a) - 4, int(y0) - 10, int(a + ww) + 4, int(y1) + 10))
    return spans


def render_thumbnails(ep) -> dict:
    """publish.json thumbnail.designs -> 1280x720 images: face-aware cover crop, a dark gradient on the text side, the
    client's headline font (HarfBuzz/CoreText) with a brand-primary bar, the design's `highlight` word(s) in the brand
    colour, the logo when available; <= 2 MB. At most thumbnail.designs_max designs (YouTube tests up to 3).
    The highlight colour is measured (WCAG contrast) against the frame pixels behind the word; when it is too faint
    (a brown primary on a warm set) the word is drawn in white/paper instead, with a warning and a `highlights` entry."""
    import io
    from PIL import Image, ImageDraw
    from .episode import episode_file, load_episode
    from .media_util import grab_frame_file, open_rgb
    from .previews import Brand, _face_center, _text_block
    lim = limits()["thumbnail"]
    TW, TH = lim["width"], lim["height"]
    pub = read_json(ep.p("publish/publish.json"), {}) or {}
    given = (pub.get("thumbnail") or {}).get("designs") or []
    dmax = int(lim.get("designs_max", 3))
    designs = given[:dmax]
    if not designs:
        return {"ok": False, "error": "publish.json thumbnail.designs is empty (pick frames from _candidates.jpg)"}
    info = load_episode(ep)
    src = episode_file(ep)
    b = Brand(ep.client_db)
    from . import client_db
    man = client_db.load(ep, "asset-manifest.json", {"assets": []}) or {"assets": []}
    logo = next((a.get("display_derivative") for a in man.get("assets", []) if a.get("category") == "logo"), None)
    out_dir = ep.p("publish/thumbnail")
    files, warnings, errors, highlights = [], [], [], []
    if len(given) > dmax:
        warnings.append(f"thumbnail.designs has {len(given)} designs: only the first {dmax} are rendered (YouTube tests up "
                        f"to {dmax} thumbnails per video); drop or reorder the rest")
    for i, dz in enumerate(designs, 1):
        t_ms, text = int(dz.get("frame_ms", 0)), str(dz.get("text") or "").strip()
        if not 0 <= t_ms < info["duration_ms"]:
            errors.append(f"design {i}: frame_ms {t_ms} is outside the episode")
            continue
        if len(text.split()) > lim.get("text_words_warn", 5):
            warnings.append(f"design {i}: {len(text.split())} words — thumbnail text reads best at 5 words or fewer")
        tmp = grab_frame_file(src, t_ms / 1000, out_dir / f"_frame_{i}.png")
        if not tmp:
            errors.append(f"design {i}: could not read the frame at {fmt_ts(t_ms, '.')}")
            continue
        fr = open_rgb(tmp)                     # loaded and closed: the temp frame can be deleted at once (Windows)
        tmp.unlink(missing_ok=True)
        fc = _face_center(fr) or (0.5, 0.4)
        # zoom in a little (a 16:9 frame into a 16:9 thumbnail has no room to move the face otherwise)
        sc = max(TW / fr.width, TH / fr.height) * float(dz.get("zoom", 1.35))
        big = fr.resize((max(TW, round(fr.width * sc)), max(TH, round(fr.height * sc))), Image.LANCZOS)
        # the face in one third, the text in the other two (text on the right reads first in Arabic); mirrored when
        # the source can't move the face that far
        x0 = int(min(max(0, fc[0] * big.width - TW * 0.30), big.width - TW))
        y0 = int(min(max(0, fc[1] * big.height - TH * 0.42), big.height - TH))
        im = big.crop((x0, y0, x0 + TW, y0 + TH)).convert("RGBA")
        text_right = (fc[0] * big.width - x0) <= TW * 0.5
        grad = Image.new("L", (TW, 1))
        for x in range(TW):
            u = 1 - x / TW if text_right else x / TW          # 0 at the text edge
            grad.putpixel((x, 0), int(210 * max(0.0, 1 - u * 1.8)))
        shade = Image.new("RGBA", (TW, TH), (0, 0, 0, 255))
        shade.putalpha(grad.resize((TW, TH)))
        im.alpha_composite(shade)
        behind = im.copy()                                  # the frame as the text will sit on it (contrast is measured here)
        face_right = not text_right
        cx = int(TW * (0.69 if text_right else 0.31))
        f = b.font("headline", int(dz.get("size", 104)))
        probe = _text_block(ImageDraw.Draw(Image.new("RGBA", (1, 1))), text, f, cx, TH // 2, b.white, max_chars=14,
                            shadow=False)
        y_bot = max(bx[3] for bx in probe)
        bw = min(TW // 2 - 40, max(bx[2] - bx[0] for bx in probe))
        bar = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
        ImageDraw.Draw(bar).rounded_rectangle((cx - bw // 2, y_bot + 14, cx + bw // 2, y_bot + 30), 8, fill=b.teal + (255,))
        im.alpha_composite(bar)
        boxes = _text_block(ImageDraw.Draw(im), text, f, cx, TH // 2, b.white, max_chars=14, shadow=True)
        hl = str(dz.get("highlight") or "").strip()
        spans = highlight_spans(text, hl, boxes, f, 14) if hl else []
        if hl and not spans:
            warnings.append(f"design {i}: highlight «{hl}» is not a word of the text, so nothing is highlighted")
        if spans:   # the same text in the brand colour, kept only inside the highlighted words' boxes
            from .legibility import legible, region_mean
            lg_ = legible(b.teal, [region_mean(behind, sp) for sp in spans], int(dz.get("size", 104)),
                          [("white", b.white), ("paper", b.paper)])
            hex_ = lambda c: "#%02X%02X%02X" % tuple(c[:3])
            highlights.append({"design": i, "word": hl, "color": hex_(lg_["rgb"]), "contrast": lg_["ratio"],
                               "brand_contrast": lg_["original_ratio"], "fallback": lg_["fallback"]})
            if lg_["fallback"] or lg_["ratio"] < lg_["need"]:
                warnings.append(f"design {i}: highlight colour {hex_(b.teal)} (brand primary) has contrast "
                                f"{lg_['original_ratio']:.1f}:1 against the frame behind «{hl}» (needs {lg_['need']:.1f}:1)"
                                + (f" - drawn in {lg_['name']} ({lg_['ratio']:.1f}:1) instead; pick another frame to keep the "
                                   f"brand highlight" if lg_["fallback"] else " - kept, white is no better on this frame; "
                                   "pick another frame"))
            col = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
            _text_block(ImageDraw.Draw(col), text, f, cx, TH // 2, lg_["rgb"], max_chars=14, shadow=False)
            mask = Image.new("L", (TW, TH), 0)
            for sp in spans:
                ImageDraw.Draw(mask).rectangle(sp, fill=255)
            im.alpha_composite(Image.composite(col, Image.new("RGBA", (TW, TH), (0, 0, 0, 0)), mask))
        if logo and Path(logo).exists():
            lg = Image.open(logo).convert("RGBA")
            lg.thumbnail((150, 150))
            im.alpha_composite(lg, (TW - lg.width - 30 if not face_right else 30, 30))
        rgb = im.convert("RGB")
        out = out_dir / f"thumb_{i}.png"
        buf = io.BytesIO()
        rgb.save(buf, "PNG", optimize=True)
        if buf.tell() > lim["max_bytes"]:
            out = out_dir / f"thumb_{i}.jpg"
            rgb.save(out, "JPEG", quality=90)
        else:
            out.write_bytes(buf.getvalue())
        files.append(str(out))
    warnings += [w for w in b.font_warnings() if w not in warnings]       # G72: Arabic text without an Arabic font
    return {"ok": not errors and bool(files), "files": files, "errors": errors, "warnings": warnings,
            "highlights": highlights, "engines": sorted(b.engines)}


# --------------------------------------------------------------------------- check + render
def check(ep) -> dict:
    from .plan import norm
    from . import srt as srtlib
    lim = limits()
    yl, il, tl, sl = lim["youtube"], lim["instagram"], lim["tiktok"], lim["shorts"]
    pub = read_json(ep.p("publish/publish.json"))
    if not pub:
        raise SystemExit("publish/publish.json missing — the publish-writer authors it (see publish-craft)")
    info = read_json(ep.p("00_inputs/episode.json"), {}) or {}
    tj = read_json(ep.p("02_transcription/transcript.json"))
    if not tj:
        raise SystemExit(f"episode transcript missing — run `reel episode-transcribe --episode {ep.episode_id}`")
    total = int(tj["meta"]["duration_ms"])
    spoken = norm(" ".join(s["text"] for s in tj["segments"]))
    sheet_text = info.get("sheet_text") or ""
    sheet_urls = {norm_url(u) for u in urls_in(sheet_text)}
    lang = pub.get("language") or (info.get("sheet") or {}).get("language") or "ar"
    errors, warnings, approvals = [], [], list(pub.get("approval_required") or [])
    bad = set(yl.get("forbidden_chars", "<>"))
    from .people import check_text, load_people
    ppl, p_issues = load_people()
    warnings += p_issues

    def gender(where: str, text: str):
        e, w = check_text(where, text, ppl)          # «الدكتورة <name>» for a man in people[] -> error
        errors.extend(e)
        warnings.extend(w)

    # manual verse: the episode's recited verses (lib/manual_verse) are never quoted in the copy nor uploaded as captions
    from . import manual_verse as mv
    ep_words = (read_json(ep.p("02_transcription/words.json"), {}) or {}).get("words") or []
    vcfg = mv.config(load_config("profile.json"))
    verses = mv.detect(ep_words, vcfg)
    warnings += vcfg["warnings"]
    verse_words = mv.span_words(verses, ep_words)

    def no_verse(where: str, text: str):
        if verse_words and mv.repeats(text or "", verse_words):
            errors.append(f"{where}: repeats the words of a recited verse in the episode — WhyNot Cut never writes Quran "
                          "text: leave the verse out of the copy (the editor adds verses by hand)")

    def facts(where: str, text: str):
        gender(where, text)
        no_verse(where, text)
        for m in QUOTE.finditer(text or ""):
            q = next(g for g in m.groups() if g)
            if norm(q) and norm(q) not in spoken:
                errors.append(f"{where}: quote «{q}» is not the speaker's words (not in the transcript)")
        for u in urls_in(text):
            if norm_url(u) not in sheet_urls:
                errors.append(f"{where}: link {u} is not in the episode sheet (links are never invented)")

    yt = pub.get("youtube") or {}
    titles = [str(t) for t in yt.get("titles") or []]
    if len(titles) < yl["titles_min"]:
        errors.append(f"youtube.titles: give at least {yl['titles_min']} titles to choose from ({len(titles)} given)")
    for k, t in enumerate(titles, 1):
        if not t.strip() or len(t) > yl["title_max"]:
            errors.append(f"title {k}: {len(t)} characters (YouTube allows 1-{yl['title_max']})")
        elif len(t) > yl["title_warn"]:
            warnings.append(f"title {k}: {len(t)} characters — over ~{yl['title_warn']} it is cut off in search and on phones")
        if bad & set(t):
            errors.append(f"title {k}: contains {''.join(sorted(bad & set(t)))} (YouTube rejects < and >)")
        facts(f"title {k}", t)
    chs = chapters(ep, pub)
    errors += [f"chapters: {e}" for e in validate_chapters(chs, total, yl)]
    for k, (_a, t) in enumerate(chs, 1):
        gender(f"chapter {k}", t)
        no_verse(f"chapter {k}", t)
    desc = assemble_description(pub, chs, lang)
    if len(desc) > yl["description_max"]:
        errors.append(f"description: {len(desc)} characters (YouTube allows {yl['description_max']})")
    if bad & set(desc):
        errors.append(f"description: contains {''.join(sorted(bad & set(desc)))} (YouTube rejects < and >)")
    d = yt.get("description") or {}
    for lk in d.get("links") or []:
        gender(f"description link {lk.get('label') or lk.get('url')}", str(lk.get("label") or ""))
        if norm_url(lk.get("url", "")) not in sheet_urls:
            errors.append(f"description link {lk.get('url')} is not in the episode sheet (links are never invented)")
    facts("description", "\n".join(str(d.get(k) or "") for k in ("hook", "summary", "guest", "sponsor", "cta")))
    tags_ = d.get("hashtags") or []
    if len(tags_) > yl["hashtags_max"]:
        errors.append(f"description: {len(tags_)} hashtags (more than {yl['hashtags_max']} and YouTube ignores them)")
    for h in tags_:
        if not re.fullmatch(r"#[^\s#]+", str(h)):
            errors.append(f"hashtag {h!r} must start with # and contain no spaces (use _)")
    guest = str((info.get("sheet") or {}).get("guest") or "")
    gname = re.split(r"\s+[—–-]\s+", guest)[0].strip()
    if gname and gname not in " ".join(str(d.get(k) or "") for k in ("hook", "summary", "guest")):
        warnings.append(f"the guest's name from the sheet ({gname}) is not in the description")
    ytags = yt.get("tags") or []
    if count_tags_chars(ytags) > yl["tags_total_max"]:
        errors.append(f"tags: {count_tags_chars(ytags)} characters (YouTube allows {yl['tags_total_max']})")
    for t in list(ytags) + list(tags_):
        gender(f"tag {t}", str(t))
    for k, dsg in enumerate((pub.get("thumbnail") or {}).get("designs") or [], 1):
        gender(f"thumbnail {k}", str(dsg.get("text") or ""))
        no_verse(f"thumbnail {k}", str(dsg.get("text") or ""))

    reels = []
    for f in sorted(ep.p("publish/reels").glob("*.json")):
        r = read_json(f, {}) or {}
        rid = r.get("reel_id") or f.stem
        ig, tt, sh = r.get("instagram") or {}, r.get("tiktok") or {}, r.get("shorts") or {}
        cap = str(ig.get("caption") or "")
        if len(cap) > il["caption_max"]:
            errors.append(f"{rid} instagram caption: {len(cap)} characters (max {il['caption_max']})")
        n_h = len(set(HASHTAG.findall(cap)) | set(ig.get("hashtags") or []))
        if n_h > il["hashtags_max"]:
            errors.append(f"{rid} instagram: {n_h} hashtags (max {il['hashtags_max']})")
        tcap = (str(tt.get("caption") or "") + " " + " ".join(tt.get("hashtags") or [])).strip()
        if len(tcap) > tl["caption_max"]:
            errors.append(f"{rid} tiktok caption: {len(tcap)} characters (max {tl['caption_max']})")
        st = str(sh.get("title") or "")
        if not st.strip() or len(st) > sl["title_max"]:
            errors.append(f"{rid} shorts title: {len(st)} characters (1-{sl['title_max']})")
        if bad & set(st + str(sh.get("description") or "")):
            errors.append(f"{rid} shorts: contains < or > (YouTube rejects them)")
        ig_all = cap + "\n" + " ".join(map(str, ig.get("hashtags") or []))
        for where, text in (("instagram", ig_all), ("tiktok", tcap), ("shorts", st + "\n" + str(sh.get("description") or ""))):
            facts(f"{rid} {where}", text)
        approvals += [f"{rid}: {a}" for a in r.get("approval_required") or []]
        if str(rid).endswith("_MO"):           # motion video (2.2): CC-BY art must be credited where it is posted
            from .common import Paths
            from .stamps import read_compiled
            mplan = read_compiled(Paths(ep.root, rid).p("01_analysis/motion-plan.json"), {}) or {}
            posted = "\n".join([cap, tcap, str(sh.get("description") or "")])
            for a in mplan.get("assets") or []:
                if a.get("license") == "CC-BY-4.0" and a.get("attribution") and a["attribution"] not in posted:
                    errors.append(f"{rid}: the CC-BY attribution «{a['attribution']}» is missing from the captions "
                                  "(it must be published with the video)")
        reels.append((rid, r))

    files = []
    out = ep.p("publish")
    srt_src = ep.p("02_transcription/subtitles.srt")
    if srt_src.exists():
        dst = out / f"{ep.episode_id}.srt"
        if verses:             # the upload SRT without a word of any recited verse (an empty gap, never a placeholder)
            srtlib.write_srt(dst, mv.filter_cues(srtlib.read_srt(srt_src),
                                                 [(s["src_start_ms"], s["src_end_ms"]) for s in verses], ep_words))
        else:
            shutil.copyfile(srt_src, dst)
        errs = srtlib.validate_cues(srtlib.read_srt(dst), total)
        if errs:
            errors.append(f"{dst.name}: " + "; ".join(errs[:3]))
        files.append(str(dst))
    else:
        warnings.append("no episode SRT yet (02_transcription/subtitles.srt)")
    ok = not errors
    if ok:
        L = [f"# YouTube — {ep.episode_id}", "", "Copy-paste ready. Checked by `reel publish-check` "
             f"({now_iso()}). Review before posting; nothing was uploaded.", "", "## Titles (pick one)", ""]
        L += [f"{k}. {t}" for k, t in enumerate(titles, 1)]
        L += ["", "## Description", "", "```text", desc, "```", "", "## Chapters", "", "```text"]
        L += [f"{fmt_chapter(a, k == 0)} {t}" for k, (a, t) in enumerate(chs)] + ["```", "", "## Tags", "", "```text",
                                                                                  ", ".join(ytags), "```"]
        if approvals:
            L += ["", "## Needs approval before posting", ""] + [f"- {a}" for a in approvals]
        files.append(str(write_text(out / "youtube.md", "\n".join(L) + "\n")))
        files.append(str(write_text(out / "chapters.txt", "\n".join(f"{fmt_chapter(a, k == 0)} {t}"
                                                                   for k, (a, t) in enumerate(chs)) + "\n")))
        files.append(str(write_text(out / "tags.txt", ", ".join(ytags) + "\n")))
        for rid, r in reels:
            ig, tt, sh = r.get("instagram") or {}, r.get("tiktok") or {}, r.get("shorts") or {}
            R = [f"# {rid} — captions", "", "## Instagram Reels", "", "```text", str(ig.get("caption") or ""),
                 "", " ".join(ig.get("hashtags") or []), "```", "", "## TikTok", "", "```text", str(tt.get("caption") or ""),
                 "", " ".join(tt.get("hashtags") or []), "```", "", "## YouTube Shorts", "", f"**Title:** {sh.get('title', '')}",
                 "", "```text", str(sh.get("description") or ""), "```"]
            if r.get("approval_required"):
                R += ["", "## Needs approval", ""] + [f"- {a}" for a in r["approval_required"]]
            files.append(str(write_text(out / "reels" / f"{rid}.md", "\n".join(R) + "\n")))
    res = {"generated": now_iso(), "ok": ok, "errors": errors, "warnings": warnings, "approvals": approvals,
           "files": files, "reels": [rid for rid, _ in reels]}
    write_json(out / "publish-validation.json", res)
    return res
