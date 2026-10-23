# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Episode sheet template (3.0 Phase 4 T4.4, `reel episode-sheet --init <EP>`).

A podcast episode's sheet (show, host, guest, links, sponsor, avoid ...) lives next to the episode file in
data/Episodes/, under the same name (episode.list_episodes matches it by folder and stem). data/ is the editor's: the
engine never writes there. So `--init` writes a template to output/episodes/<EP>/, named like the episode file, and
says where to move it.

The template is what `episode.parse_sheet` reads (flat frontmatter, `#` lines are comments). Every value is empty
until the editor fills it in, and the comments hold no name, link or URL of any kind: `episode-prep` keeps the whole
sheet text (`sheet_text`), the publish writer takes names from it and publish-check builds its allowed-links list
from it, so an untouched template must give them nothing. Genders start as `unknown`, the people[] vocabulary: never
guessed. The host and guest fields mirror a people[] entry (name, gender, honorific_ar, honorific_en);
`sheet_people()` turns a filled sheet into people[] entries, checked the same way (an honorific that contradicts the
gender is reported). The client's own people[] come back in the command's result for the editor to copy from; they
are not written into the sheet.

Refusals (nothing written): a strict episode id only; a sheet already in data/Episodes for that episode or with the
template's name (`--force` writes a fresh template to output/ anyway); an output template whose values the editor
already changed (`--force` replaces it and keeps the old one as `<name>.before-<time>.md`); any write that would land in
the client's data/ or assets/ through a link (lib/client_move_paths.py), checked before discovery runs and again right
before the file is written.
"""
from __future__ import annotations

import os
import re
import secrets
import time
from pathlib import Path, PurePosixPath

from .client_move_paths import first_refusal
from .common import Context, Paths, _retry, check_project_id, current_context, read_json

PERSON_KEYS = ("name", "role", "gender", "honorific_ar", "honorific_en")
SHEET_PEOPLE = ("host", "guest") + tuple(f"guest_{n}" for n in range(2, 10))


SHEET_NAMES = SHEET_PEOPLE + ("show",)


def _one_line(v) -> str:
    return " ".join(str(v or "").split())


def sheet_text(value) -> str:
    """Review c963132 P2-1: a sheet name (SHEET_NAMES) as it may be shown: plain text only. Anything else (a list, a
    mapping, a number, true/false, null) is "" here, never its Python form on screen; name_problems() says why."""
    return value.strip() if isinstance(value, str) else ""


def name_problems(sheet: dict) -> list[str]:
    """Review c963132 P2-1 (executor ruling): one plain line (English and Arabic) for each host, guest, guest_2 …
    guest_9 or show value that is given but is not one name written as text. An empty value is "not given"."""
    out = []
    for k in SHEET_NAMES:
        if not isinstance(sheet, dict) or k not in sheet or isinstance(sheet[k], str):
            continue
        eg = "My Show" if k == "show" else "Ahmed"
        v = sheet[k]
        if isinstance(v, list):
            out.append(f"{k} in the episode sheet is a list, not one name: it must be one name written as text, "
                       f"e.g. `{k}: {eg}`; each guest has its own field (guest, guest_2 … guest_9) "
                       f"({k} في شيت الحلقة مكتوب كقائمة: لازم يكون اسم واحد مكتوب كنص، زي `{k}: {eg}`؛ وكل ضيف "
                       "في خانة لوحده)")
        else:
            out.append(f"{k} in the episode sheet must be one name written as text, e.g. `{k}: {eg}` (a name made of "
                       f"digits goes in quotes) ({k} في شيت الحلقة لازم يكون اسم واحد مكتوب كنص، زي `{k}: {eg}`؛ "
                       "ولو الاسم أرقام حطه بين علامتين تنصيص)")
    return out


def _context(paths: Paths, ctx) -> Context:
    if ctx is not None:
        return ctx
    cur = current_context()                          # the CLI's (it carries --profile) when it is for this client
    return cur if cur.root == paths.root else Context(paths.root)


def _people(ctx: Context) -> tuple[list[dict], list[str]]:
    from .people import load_people
    cfg = ctx.config("profile.json")
    raw = cfg.get("people") or []
    _ok, issues = load_people(cfg)
    listed = [{k: _one_line(p.get(k)) for k in PERSON_KEYS} for p in raw if isinstance(p, dict) and
              _one_line(p.get("name"))] if isinstance(raw, list) else []
    return listed, issues


def sheet_people(sheet: dict) -> tuple[list[dict], list[str]]:
    """A parsed sheet's host and guests as people[] entries ({name, role, gender, honorific_ar, honorific_en}), plus
    problems (a gender that is not male | female | unknown, an honorific that contradicts the gender). The name is the
    part before « — » («د. منى سالم — استشاري» -> «د. منى سالم»)."""
    from .people import load_people
    entries = []
    for role in SHEET_PEOPLE:
        bad = name_problems({role: sheet.get(role)}) if role in sheet else []
        if bad:                                     # review c963132 P2-1: a list, number ... is never a name
            entries.append({"name": "", "role": role, "_issues": bad})
            continue
        name = re.split(r"\s+[—–-]\s+", _one_line(sheet_text(sheet.get(role))))[0].strip()
        if not name:
            continue
        entries.append({"name": name, "role": role, "gender": _one_line(sheet.get(f"{role}_gender")) or "unknown",
                        "honorific_ar": _one_line(sheet.get(f"{role}_honorific_ar")),
                        "honorific_en": _one_line(sheet.get(f"{role}_honorific_en"))})
    issues = [i for e in entries for i in e.get("_issues", [])]
    entries = [e for e in entries if e["name"]]
    for e in entries:                               # one at a time: each problem names the sheet field it is about
        checked, found = load_people({"people": [e]})
        e["gender"] = checked[0]["gender"] if checked else "unknown"
        issues += [i.replace("profile.json people[0]", f"the sheet's {e['role']}") for i in found]
    return entries, issues


def render(episode_id: str, episode_rel: str | None, move_to: str) -> str:
    src = f" ({_one_line(episode_rel)})" if episode_rel else ""
    lines = [
        "---",
        f"# WhyNot Cut episode sheet for {episode_id}{src}.",
        "# Fill in what you know and leave the rest empty: names, links and the sponsor in the publish package come",
        "# ONLY from this sheet. Lines that start with # are notes for you; WhyNot Cut ignores them.",
        f"# When it is filled in, move this file to {_one_line(move_to)} (next to the episode, the same name).",
        f"episode: {episode_id}",
        "# show: the programme's name as it is written on screen",
        "show:",
        "# host and guest: «<name> — <short title>». gender: male | female | unknown (never guessed from a name).",
        "# Honorifics as they are written for this person (Arabic, English); they must match the gender.",
        "# If the person is in the client's people list (the `reel episode-sheet` result shows it), copy those values.",
        "host:",
        "host_gender: unknown",
        "host_honorific_ar:",
        "host_honorific_en:",
        "guest:",
        "guest_gender: unknown",
        "guest_honorific_ar:",
        "guest_honorific_en:",
        "# a second guest: add guest_2, guest_2_gender, guest_2_honorific_ar and guest_2_honorific_en the same way",
        "# topics: [<topic>, <topic>], or one per line: a dash, a space, then the topic",
        "topics:",
        "sponsor:",
        "# links: one per line: a dash, a space, then the full link",
        "links:",
        "# publish_date: year-month-day, e.g. 2026-11-05",
        "publish_date:",
        "# avoid: topics or moments that must not become reels, one per line like links",
        "avoid:",
        "---",
    ]
    return "\n".join(lines) + "\n"


def _values(text: str) -> dict:
    from .episode import parse_sheet
    return {k: v for k, v in parse_sheet(text).items() if k != "_text"}


def _write(target: Path, text: str) -> None:
    tmp = target.with_name(f"{target.name}.{os.getpid()}-{secrets.token_hex(4)}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        _retry(lambda: os.replace(tmp, target))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _backup_name(target: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for n in range(1, 1000):                         # two backups in one second never share a name
        cand = target.with_name(f"{target.stem}.before-{stamp}{'' if n == 1 else f'-{n}'}.md")
        if not os.path.lexists(cand):
            return cand
    raise OSError(f"no free backup name next to {target}")


def _keep_aside(target: Path, backup: Path) -> None:
    """Copy the old text to `backup` with an exclusive create (never over an existing file), then the caller writes the
    new template over `target`."""
    data = target.read_bytes()
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def _sheets(inv: dict) -> list[PurePosixPath]:
    from .episode import SHEET_EXT
    return [PurePosixPath(f["rel"].replace("\\", "/")) for f in (inv or {}).get("files", [])
            if f.get("role") == "episode_sheet" and Path(f["rel"]).suffix.lower() in SHEET_EXT]


def _other_documents(inv: dict, stem: str) -> list[str]:
    from .episode import SHEET_EXT
    return [f["rel"] for f in (inv or {}).get("files", []) if f.get("role") == "episode_sheet"
            and Path(f["rel"]).suffix.lower() not in SHEET_EXT and Path(f["rel"]).stem.casefold() == stem.casefold()]


def init(root, episode_id: str, force: bool = False, ctx: Context | None = None) -> dict:
    """Write the template for `episode_id` into output/episodes/<EP>/; a dict for `reel` (`refused` = nothing written)."""
    check_project_id(episode_id, "episode id", strict=True)          # never a path out of output/episodes
    paths = Paths(root)
    out = paths.output
    r = first_refusal(paths.root, (out, out / "discovery", out / "logs", out / "episodes"))   # before discovery writes
    if r:
        return r
    from .episode import list_episodes
    eps = list_episodes(paths.root, refresh=True)
    warnings = []
    hit = next((e for e in eps if e["episode_id"] == episode_id), None)
    if not hit:
        same = [e for e in eps if e["episode_id"].casefold() == episode_id.casefold()]
        if len(same) == 1:
            hit = same[0]
            warnings.append(f"episode id {episode_id!r} is {hit['episode_id']}: using {hit['episode_id']}")
            episode_id = hit["episode_id"]
    inv = read_json(out / "discovery/input-inventory.json", {}) or {}
    sheets = _sheets(inv)
    if hit:
        rel = PurePosixPath(hit["rel"].replace("\\", "/"))
        name = rel.stem + ".md"
        move_to = (rel.parent / name).as_posix()
        if hit.get("warning"):
            warnings.append(hit["warning"])
        existing = hit.get("sheet")
        elsewhere = [s.as_posix() for s in sheets if s.stem.casefold() == rel.stem.casefold() and
                     s.parent != rel.parent]
        if elsewhere:
            warnings.append(f"{', '.join(elsewhere)} is in another folder than the episode: episode-prep reads only "
                            f"a sheet next to it ({move_to})")
        others = _other_documents(inv, rel.stem)
        if others:
            warnings.append(f"{', '.join(others)} is not read as the sheet (only .md, .markdown or .txt are)")
    else:
        name = f"{episode_id}.md"
        move_to = f"data/Episodes/{name}"
        known = sorted(e["episode_id"] for e in eps)
        warnings.append(f"no episode file with id {episode_id} in data/Episodes yet (known: {', '.join(known) or 'none'})"
                        f": name it like the episode file when you move it (EP12.mp4 -> EP12.md, in the same folder)")
        existing = next((s.as_posix() for s in sheets if s.stem.casefold() == episode_id.casefold()), None)
    if existing:
        if not force:
            return {"refused": f"{existing} already exists: this episode has its sheet (nothing was written)",
                    "how": f"The editor edits {existing} itself (data/ is theirs). For a fresh template in output/ "
                           f"anyway: `reel episode-sheet --init {episode_id} --force` (moving it there would replace "
                           "the editor's sheet)."}
        warnings.append(f"{existing} already exists: the template in output/ does not replace it; moving it there would")
    project = out / "episodes" / episode_id
    target = project / name
    r = first_refusal(paths.root, (project, target))
    if r:
        return r
    sheet_rel = target.relative_to(paths.root).as_posix()
    if project.exists() and not project.is_dir():
        return {"refused": f"{project.relative_to(paths.root).as_posix()} is a file, not the episode's folder "
                           "(nothing was written)", "how": "Move that file out of the way, then run it again."}
    if target.is_dir():
        return {"refused": f"{sheet_rel} is a folder (nothing was written)", "how": "Move that folder out of the way."}
    people, issues = _people(_context(paths, ctx))
    warnings += issues
    text = render(episode_id, hit["rel"] if hit else None, move_to)
    unchanged, refreshed, backup = False, False, None
    if target.is_file():
        old = target.read_bytes().decode("utf-8", "replace")
        if old == text:
            unchanged = True
        elif _values(old) == _values(text):
            refreshed = True             # no value changed (a newer template, or the editor's own # notes): refreshed,
            backup = _backup_name(target)  # the old text kept next to it all the same
        elif not force:
            return {"refused": f"{sheet_rel} already exists and the editor's values are in it: it was kept as it is",
                    "how": f"Move it to {move_to} if it is filled in, or `reel episode-sheet --init {episode_id} "
                           "--force` to start again from a fresh template (the old one is kept next to it)."}
        else:
            backup = _backup_name(target)
    if not unchanged:
        project.mkdir(parents=True, exist_ok=True)
        r = first_refusal(paths.root, (project, target) + ((backup,) if backup else ()))   # a link swapped in
        if r:
            return r
        if backup:
            _keep_aside(target, backup)
        _write(target, text)
    return {"ok": True, "episode_id": episode_id, "sheet": str(target), "sheet_rel": sheet_rel, "move_to": move_to,
            "episode_file": hit["rel"] if hit else None, "unchanged": unchanged, "refreshed": refreshed,
            "backup": backup.relative_to(paths.root).as_posix() if backup else None, "people": people,
            "warnings": warnings,
            "next": f"give the editor {sheet_rel} to fill in (show them `people` to copy a person's name, gender and "
                    f"honorifics) and to move to {move_to} (data/ is theirs; WhyNot Cut never writes there); then "
                    f"`reel episode-prep --episode {episode_id}` reads it"}
