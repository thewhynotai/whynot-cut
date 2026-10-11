"""Podcast mode: the PUBLISH PACKAGE of an episode — YouTube titles/description/chapters/tags/SRT for the episode,
captions and hashtags for each reel (Instagram, TikTok, YouTube Shorts) and thumbnail designs.

The copy is authored by the publish-writer agent (publish/publish.json, publish/reels/<REEL>.json); this module
checks it against platform limits (config/defaults/platform-limits.json) and the episode's own facts, then renders
the files the editor copies from. Nothing is uploaded anywhere.
  * every URL must appear in the episode sheet (names and links are never invented)
  * every quoted line («…», "…", “…”) must be the speaker's words (found in the transcript)
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .common import fmt_ts, load_config, now_iso, read_json, write_json, write_text

QUOTE = re.compile(r"«([^»]+)»|“([^”]+)”|\"([^\"]+)\"")
HASHTAG = re.compile(r"#[^\s#]+")
URL = re.compile(r"(?:https?://|www\.)[^\s<>«»\"'()]+|(?<![@\w.])(?:[a-z0-9-]+\.)+(?:com|net|org|io|me|tv|co|ai|eg|sa|ae|"
                 r"ly|gg|app|link|page)(?:/[^\s<>«»\"'()]*)?", re.I)


def limits() -> dict:
    return load_config("platform-limits.json")


# --------------------------------------------------------------------------- helpers
def parse_time(v) -> int:
    """'00:40', '1:02:03', '00:00:40.500', 40.5 -> ms."""
    if isinstance(v, (int, float)):
        return int(round(float(v) * 1000))
    s = str(v).strip()
    frac = 0
    if re.search(r"[.,]\d{1,3}$", s) and s.count(":") >= 1:
        s, f = re.split(r"[.,](?=\d{1,3}$)", s)
        frac = int(f.ljust(3, "0"))
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return ((parts[0] * 60 + parts[1]) * 60 + parts[2]) * 1000 + frac


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


def urls_in(text: str) -> list[str]:
    return [m.group(0) for m in URL.finditer(text or "")]


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

    def facts(where: str, text: str):
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
    desc = assemble_description(pub, chs, lang)
    if len(desc) > yl["description_max"]:
        errors.append(f"description: {len(desc)} characters (YouTube allows {yl['description_max']})")
    if bad & set(desc):
        errors.append(f"description: contains {''.join(sorted(bad & set(desc)))} (YouTube rejects < and >)")
    d = yt.get("description") or {}
    for lk in d.get("links") or []:
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
        for where, text in (("instagram", cap), ("tiktok", tcap), ("shorts", st + "\n" + str(sh.get("description") or ""))):
            facts(f"{rid} {where}", text)
        approvals += [f"{rid}: {a}" for a in r.get("approval_required") or []]
        reels.append((rid, r))

    files = []
    out = ep.p("publish")
    srt_src = ep.p("02_transcription/subtitles.srt")
    if srt_src.exists():
        dst = out / f"{ep.episode_id}.srt"
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
