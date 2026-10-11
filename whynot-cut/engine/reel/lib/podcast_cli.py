"""Podcast-mode commands of the `reel` CLI (registered by cli.py: subparser names, arguments, dispatch).

Episode commands take `--episode <EP>` (the id from `reel episodes`); when a client has exactly one episode it is used.
"""
from __future__ import annotations

import json
from pathlib import Path

ARGS: dict = {
    "episodes": [],
    "episode-prep": [],
    "episode-transcribe": [
        (("--model",), {"default": None, "help": "default: preferences whisper_model, else large-v3"}),
        (("--language",), {"default": None, "help": "e.g. ar; default: detected on the first chunk"}),
        (("--force",), {"action": "store_true", "help": "discard the chunk checkpoints and transcribe again"}),
    ],
    "reels-plan": [],
    "reels-preview": [(("--ids",), {"default": None, "help": "e.g. R01,R03 (default: every candidate)"})],
    "reels-select": [
        (("--pick",), {"default": "", "help": "the editor's choice, e.g. R01,R03"}),
        (("--adjust",), {"action": "append", "default": [], "help": "R03:in=00:12:04.000 or R03:out=00:13:05 (repeatable)"}),
        (("--by",), {"required": True, "choices": ["editor", "delegated"],
                     "help": "editor = the editor picked in chat; delegated = they told you to choose"}),
        (("--note",), {"default": "", "help": "the editor's words (required with --by delegated)"}),
        (("--confirm-avoid",), {"action": "append", "default": [], "help": "a candidate id the editor OKs despite an avoid-topic hit"}),
        (("--force",), {"action": "store_true", "help": "re-slice a reel whose window changed"}),
        (("--resync",), {"action": "store_true", "help": "re-slice selected reels' transcripts after episode corrections"}),
    ],
    "music": [(("--list",), {"action": "store_true", "help": "list the licensed tracks in data/Music with mood tags"})],
    "publish-check": [],
    "episode-next": [],
    "publish-thumbnail": [
        (("--candidates",), {"action": "store_true", "help": "pick frames worth a thumbnail (faces, sharp, contrast)"}),
        (("--render",), {"action": "store_true", "help": "render publish.json thumbnail.designs as 1280x720 images"}),
        (("--n",), {"type": int, "default": 12, "help": "how many candidate frames"}),
    ],
}
NO_EPISODE = {"episodes", "music"}


def add_args(name: str, sp) -> None:
    for flags, kw in ARGS.get(name, []):
        sp.add_argument(*flags, **kw)


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def EP(a):
    from .episode import EpisodePaths
    return EpisodePaths(a.root, a.episode)


def resolve_episode(a) -> None:
    """Fill a.episode when the command needs one and the client has exactly one episode."""
    if a.cmd in NO_EPISODE or getattr(a, "episode", None):
        return
    from .episode import list_episodes
    eps = list_episodes(Path(a.root))
    if len(eps) == 1:
        a.episode = eps[0]["episode_id"]
        return
    raise SystemExit("--episode required (" + (f"episodes: {', '.join(e['episode_id'] for e in eps)}"
                                               if eps else "no episode in data/Episodes") + ")")


def cmd_episodes(a):
    from .episode import list_episodes
    out({"episodes": list_episodes(Path(a.root), refresh=True)})


def cmd_episode_prep(a):
    from .episode import prep
    out(prep(EP(a)))


def cmd_episode_transcribe(a):
    from .episode import transcribe_episode
    from . import settings as S
    ep = EP(a)
    if ep.p("02_transcription/transcript.json").exists() and not a.force and not _chunks_missing(ep):
        out({"skipped": "episode transcript exists (use --force to redo)", "transcript": str(ep.p("02_transcription/transcript.txt"))})
        return
    model = a.model or S.load(ep.root).get("whisper_model") or "large-v3"
    r = transcribe_episode(ep, model, language=a.language, force=a.force)
    r["next"] = ("transcript-editor reviews 02_transcription/subtitle-review.md (`reel transcript-correct --episode "
                 f"{ep.episode_id}`), then episode-analyst authors topics/speakers/reels-plan")
    out(r)


def cmd_reels_plan(a):
    from .reels import compile_reels_plan
    ep = EP(a)
    r = compile_reels_plan(ep)
    out({"ok": r["ok"], "errors": r["errors"], "warnings": r["warnings"], "candidates": len(r["candidates"]),
         "top": [{k: c.get(k) for k in ("id", "total", "type", "in_ms", "out_ms", "title")} for c in r["candidates"][:5]],
         "plan": str(ep.p("01_analysis/reels-plan.md")) if r["ok"] else None,
         "next": (f"reel reels-preview --episode {ep.episode_id}, then show reels-plan.md to the editor (Gate 0)"
                  if r["ok"] else "fix the errors in 01_analysis/reels-plan.json and run reels-plan again")})


def cmd_reels_preview(a):
    from .reels import render_candidates
    ep = EP(a)
    ids = [x.strip() for x in a.ids.split(",") if x.strip()] if a.ids else None
    r = render_candidates(ep, ids)
    r["plan"] = str(ep.p("01_analysis/reels-plan.md"))
    r["next"] = "VIEW the sheet, then show the editor reels-plan.md + previews and wait for their pick (Gate 0)"
    out(r)


def cmd_reels_select(a):
    from .reels import select
    picks = [x.strip() for x in a.pick.split(",") if x.strip()]
    if not picks and not a.resync:
        raise SystemExit("--pick required (the editor's choice), or --resync")
    if a.by == "delegated" and not a.note.strip():
        raise SystemExit("--by delegated needs --note with the editor's own words")
    out(select(EP(a), picks, a.adjust, a.by, note=a.note, confirm_avoid=a.confirm_avoid, force=a.force, resync=a.resync))


def cmd_music(a):
    from .recipes import music_library, types
    lib = music_library(Path(a.root))
    out({"tracks": lib, "recipe_moods": {t: r.get("music", {}).get("mood") for t, r in types().items()},
         "how": "pick a track whose moods fit the reel's recipe and set edit-decisions music.file (licensed tracks only; "
                "no track fits -> leave music for the editor)" if lib else
                "no licensed music in data/Music: the music track stays for the editor (Needs you: music)"})


def cmd_publish_check(a):
    from .publish import check
    ep = EP(a)
    r = check(ep)
    r["next"] = (f"show the editor {ep.p('publish/youtube.md')} and publish/reels/*.md (they post it themselves)"
                 if r["ok"] else "fix publish/publish.json or publish/reels/*.json and run publish-check again")
    out(r)


def cmd_publish_thumbnail(a):
    from .publish import render_thumbnails, thumbnail_candidates
    ep = EP(a)
    if not a.candidates and not a.render:
        raise SystemExit("--candidates (pick frames) or --render (draw publish.json thumbnail.designs)")
    res = {}
    if a.candidates:
        res["candidates"] = thumbnail_candidates(ep, n=a.n)
        res["next"] = "VIEW publish/thumbnail/_candidates.jpg, then write 3 designs (frame_ms + text) in publish.json"
    if a.render:
        res["render"] = render_thumbnails(ep)
        res["next"] = "VIEW each thumb_*.png (text readable, face clear, logo not over the face) before showing the editor"
    out(res)


def cmd_episode_next(a):
    from .episode import episode_next
    out(episode_next(EP(a)))


def _chunks_missing(ep) -> bool:
    from .common import read_json
    plan = read_json(ep.p("02_transcription/chunks/plan.json"), {}) or {}
    return any(not ep.p(f"02_transcription/chunks/chunk_{i:03d}.json").exists() for i in range(len(plan.get("chunks", []))))


def dispatch(a) -> bool:
    fn = globals().get("cmd_" + a.cmd.replace("-", "_"))
    if a.cmd not in ARGS or fn is None:
        return False
    resolve_episode(a)
    fn(a)
    return True
