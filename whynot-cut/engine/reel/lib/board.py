"""`reel board` (3.0 T3.10): one table of every client under the clients folder, their items, state and next step.

Read-only and bounded: one listing of the clients folder (at most MAX_CLIENTS client folders), per client one listing
of output/projects and output/episodes (at most MAX_ITEMS each) and one walk of data/ (at most MAX_FILES files), and a
time budget (default 5 s) after which the remaining items carry only their recorded status (`partial: true`). Nothing
is written: new raw clips get the id `reel inbox` would give them (lib/clip_ids.assign, pure), the stored map is only
read. Arabic client names are kept as they are (NFC).

The JSON document (`reel board --json`) is the same data the WhyNot Cut panel in Premiere shows; it is stable
(`board: 1`; fields are only ever added):

    {"ok": true, "board": 1, "clients_root": "<folder>" | null, "generated": "<ISO time>", "elapsed_ms": 12,
     "truncated": false,                      # a cap or the time budget cut the scan short
     "totals": {"clients": 2, "items": 3, "new": 1, "working": 1, "waiting_for_you": 1, "blocked": 0, "done": 0},
     "clients": [
       {"name": "Dr Mona Adel", "path": "<folder>", "prefix": "MA", "profile": "dr-mona" | null,
        "counts": {"new": 1, "working": 0, "waiting_for_you": 1, "blocked": 0, "done": 0},
        "truncated": false, "error": null,     # error: the client could not be read (the others still are)
        "items": [
          {"id": "C0239", "kind": "clip" | "reel" | "motion" | "episode",
           "state": "new" | "working" | "waiting_for_you" | "blocked" | "done",
           "status": "<the engine's recorded status, e.g. PLAN_APPROVED>" | null,
           "next": "<the engine's next step (`reel next` / `reel episode-next`)>" | null,
           "next_step": "<the next step in the editor's words: approve the plan, pick the reels, ...>",
           "stale": 0,                         # steps whose inputs changed after they ran
           "updated": "<ISO time of the last recorded status>" | null,
           "file": "data/Raw/C0239.MP4" | null, # new items: the raw file
           "partial": false}]}]}               # the time budget ran out before this item's next step was read

`next_step` never contains a command: the panel shows it as it is. The plain table (`reel board`) has one row per item.
"""
from __future__ import annotations

import os
import time
import unicodedata
from pathlib import Path

from .common import (DONE_STATUSES, Context, Paths, client_folders, is_junk, load_status, now_iso, project_prefix,
                     read_json, use_context)

BOARD_VERSION = 1
MAX_CLIENTS = 200
MAX_ITEMS = 200
MAX_FILES = 5000
DEFAULT_BUDGET_S = 5.0
STATES = ("new", "working", "waiting_for_you", "blocked", "done")
STATE_WORDS = {"new": "new", "working": "in progress", "waiting_for_you": "waiting for you", "blocked": "blocked",
               "done": "done"}


def _nfc(s) -> str:
    return unicodedata.normalize("NFC", str(s))


def plain_step(next_step: str | None, item_id: str, kind: str, state: str) -> str:
    """The engine's next step in the editor's words (the three verbs: drop files · say what you want · approve the
    plan). Never a command."""
    n = (next_step or "").strip()
    low = n.lower()
    if state == "new":
        return ("say “make reels from this episode”" if kind == "episode"
                else "say “edit the new videos”")
    if state == "done" or low == "done":
        return "nothing: finished"
    if state == "blocked":
        return f"say “status of {item_id}” to see what blocks it"
    if low.startswith(("playback", "approve-plan")):
        return "approve the plan"
    if low.startswith(("select reels", "reels-select")):
        return "pick the reels"
    if not n:
        return f"say “status of {item_id}”"
    if low.startswith(("ppro-frames", "motion-frames", "verify", "qc")):
        return f"proof check: say “continue {item_id}”"
    if low.startswith(("ppro-build", "premiere", "sfx")):
        return f"build in Premiere: say “continue {item_id}”"
    if low.startswith(("ae-probe", "motion-build", "motion-render")):
        return f"build in After Effects: say “continue {item_id}”"
    if low.startswith("handoff"):
        return f"handoff: say “continue {item_id}”"
    if "publish" in low:
        return f"publish copy: say “continue {item_id}”"
    return f"say “continue {item_id}”"


def _state(status: str | None, nxt: str | None) -> str:
    st = str(status or "").split(" (")[0]
    low = str(nxt or "").lower()
    if low == "done" or (st in DONE_STATUSES and nxt is None):
        return "done"
    if st == "BLOCKED":
        return "blocked"
    if low.startswith(("playback", "approve-plan", "select reels", "reels-select")):
        return "waiting_for_you"
    return "working"


def _dirs(folder: Path) -> list[Path]:
    try:
        return sorted(d for d in folder.iterdir() if d.is_dir() and not d.name.startswith((".", "_")))
    except OSError:
        return []


def _data_files(root: Path, cap: int = MAX_FILES) -> tuple[list[tuple[Path, str]], bool]:
    """(file, relative path) under data/, hidden folders skipped, at most cap files; (files, cut short)."""
    out, data = [], root / "data"
    for dirpath, dirnames, filenames in os.walk(data):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if len(out) >= cap:
                return out, True
            f = Path(dirpath) / name
            out.append((f, f.relative_to(root).as_posix()))
    return out, False


def _new_items(root: Path) -> tuple[list[dict], bool]:
    """Raw clips with no started project and episodes with no episode folder (read-only)."""
    from . import clip_ids
    from .discover import classify
    from .episode import episode_id_for
    files, cut = _data_files(root)
    clips, eps = [], []
    for f, rel in files:
        if is_junk(f) or f.name.startswith("."):
            continue
        try:
            role = classify(f, rel)["role"]
        except OSError:
            continue
        if role == "source_footage":
            clips.append(rel)
        elif role == "episode":
            eps.append(f)
    items = []
    ids = clip_ids.assign(root, clips, clip_ids.load(root))
    for rel in clips:
        vid = clip_ids.id_of(ids, rel)
        if vid and not (root / "output" / "projects" / vid).is_dir():
            items.append({"id": vid, "kind": "clip", "file": rel})
    seen = set()
    for f in eps:
        eid = episode_id_for(f)
        if eid in seen or (root / "output" / "episodes" / eid).is_dir():
            continue
        seen.add(eid)
        items.append({"id": eid, "kind": "episode", "file": f.relative_to(root).as_posix()})
    return items, cut


def _item(id_: str, kind: str, status=None, nxt=None, stale=0, updated=None, file=None, partial=False) -> dict:
    state = "new" if status is None and nxt is None and file else _state(status, nxt)
    return {"id": id_, "kind": kind, "state": state, "status": status, "next": nxt,
            "next_step": plain_step(nxt, id_, kind, state), "stale": int(stale or 0), "updated": updated,
            "file": file, "partial": bool(partial)}


def _project_item(root: Path, d: Path, next_fn, light: bool) -> dict:
    from .motion_config import is_motion
    p = Paths(root, d.name)
    st = load_status(p)
    kind = "motion" if is_motion(p) else ("reel" if p.p("00_inputs/source.json").exists() else "clip")
    upd = st.get("updated") if st.get("history") else None
    if light or next_fn is None:            # the time budget ran out: the recorded status only
        return _item(d.name, kind, status=st.get("status"), updated=upd, partial=True)
    doc = next_fn(p)
    return _item(d.name, kind, status=st.get("status"), nxt=doc.get("next"), stale=len(doc.get("stale") or []),
                 updated=upd)


def _episode_item(root: Path, d: Path, light: bool) -> dict:
    from .episode import EpisodePaths, _episode_state, episode_next
    ep = EpisodePaths(root, d.name)
    if light:
        return _item(d.name, "episode", status=_episode_state(ep), partial=True)
    doc = episode_next(ep)
    return _item(d.name, "episode", status=doc.get("state"), nxt=doc.get("next"), stale=len(doc.get("stale") or []))


def client_card(root: Path, next_fn=None, deadline: float | None = None) -> tuple[dict, bool]:
    """One client's card (see the module docstring) and whether the time budget ran out while reading it."""
    root = Path(root)
    card = {"name": _nfc(root.name), "path": str(root), "prefix": None, "profile": None,
            "counts": dict.fromkeys(STATES, 0), "truncated": False, "error": None, "items": []}
    over = False
    with use_context(Context(root)):
        try:
            card["prefix"] = project_prefix()
            card["profile"] = (read_json(root / "output/client_database/reel-profile/profile.json", {}) or {}).get("id")
            projects = _dirs(root / "output" / "projects")
            episodes = _dirs(root / "output" / "episodes")
            card["truncated"] = len(projects) > MAX_ITEMS or len(episodes) > MAX_ITEMS
            for d in episodes[:MAX_ITEMS]:
                over = over or (deadline is not None and time.monotonic() >= deadline)
                card["items"].append(_episode_item(root, d, over))
            for d in projects[:MAX_ITEMS]:
                over = over or (deadline is not None and time.monotonic() >= deadline)
                card["items"].append(_project_item(root, d, next_fn, over))
            new, cut = _new_items(root)
            card["truncated"] = card["truncated"] or cut
            card["items"] += [_item(n["id"], n["kind"], file=n["file"]) for n in new[:MAX_ITEMS]]
        except Exception as e:  # noqa: BLE001 — one unreadable client never hides the others
            card["error"] = f"{type(e).__name__}: {e}"
    order = {s: i for i, s in enumerate(("waiting_for_you", "blocked", "new", "working", "done"))}
    card["items"].sort(key=lambda it: (order.get(it["state"], 9), it["id"]))
    for it in card["items"]:
        card["counts"][it["state"]] += 1
    return card, over


def board(base: Path | None, only: Path | None = None, next_fn=None, budget: float = DEFAULT_BUDGET_S) -> dict:
    """The board of every client folder in base (or of the one client `only`)."""
    t0 = time.monotonic()
    deadline = t0 + max(0.0, float(budget))
    folders = [Path(only)] if only else client_folders(base)
    truncated = len(folders) > MAX_CLIENTS
    clients, over = [], False
    for f in folders[:MAX_CLIENTS]:
        card, hit = client_card(f, next_fn, deadline)
        over = over or hit
        truncated = truncated or card["truncated"] or hit
        clients.append(card)
    totals = {"clients": len(clients), "items": sum(len(c["items"]) for c in clients),
              **{s: sum(c["counts"][s] for c in clients) for s in STATES}}
    return {"ok": True, "board": BOARD_VERSION, "clients_root": str(base) if base else None, "generated": now_iso(),
            "elapsed_ms": int((time.monotonic() - t0) * 1000), "truncated": truncated, "totals": totals,
            "clients": clients}


def _cell(s) -> str:
    return str(s if s is not None else "").replace("|", "/").replace("\n", " ")


def table(doc: dict) -> str:
    """The plain table (Markdown): one row per item, a row per client without items."""
    rows = ["| Client · العميل | Item · الفيديو | State · الحالة | Next step · الخطوة الجاية |", "|---|---|---|---|"]
    for c in doc.get("clients", []):
        if c.get("error"):
            rows.append(f"| {_cell(c['name'])} | — | could not be read | {_cell(c['error'])} |")
            continue
        if not c.get("items"):
            rows.append(f"| {_cell(c['name'])} | — | no videos yet | drop raw clips into data/Raw |")
        for it in c.get("items", []):
            kind = "" if it["kind"] == "clip" else f" ({it['kind']})"
            rows.append(f"| {_cell(c['name'])} | {_cell(it['id'])}{kind} | {STATE_WORDS.get(it['state'], it['state'])}"
                        f" | {_cell(it['next_step'])} |")
    t = doc.get("totals", {})
    foot = (f"{t.get('clients', 0)} clients · {t.get('items', 0)} videos · {t.get('waiting_for_you', 0)} waiting for "
            f"you · {t.get('new', 0)} new · {t.get('working', 0)} in progress · {t.get('done', 0)} done")
    if doc.get("truncated"):
        foot += " · (scan cut short: ask for one client to see all of it)"
    return "\n".join(rows + ["", foot])
