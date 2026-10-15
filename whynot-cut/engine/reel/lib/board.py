"""`reel board` (3.0 T3.10): one table of every client under the clients folder, their items, state and next step.

Read-only and bounded: one listing of the clients folder (at most MAX_CLIENTS client folders), per client one listing
of output/projects and output/episodes (at most MAX_ITEMS each) and one walk of data/ (at most MAX_FILES files), and a
time budget (default 5 s) that covers every per-client step (the prefix check, the projects' next steps, the data/
walk and the new-clip lookup). An item read after the deadline carries only its recorded status (`partial: true`); a
client reached after it is listed with `skipped: "time budget"` and no items, and nothing of it is read. Nothing is
written: new raw clips get the id `reel inbox` would give them (lib/clip_ids.assign, pure; one map per client, looked
up by dict), the stored map is only read. Arabic client names are kept as they are (NFC).

The JSON document (`reel board --json`) is the same data the WhyNot Cut panel in Premiere shows; it is stable
(`board: 1`; fields are only ever added). Its values are machine values (English); the plain table (`reel board`) is
in the editor's language (settings `language`, ar by default; `--lang`):

    {"ok": true, "board": 1, "clients_root": "<folder>" | null, "generated": "<ISO time>", "elapsed_ms": 12,
     "truncated": false,                      # a cap or the time budget cut the scan short
     "totals": {"clients": 2, "items": 3, "new": 1, "working": 1, "waiting_for_you": 1, "blocked": 0, "done": 0,
                "not_scanned": 0},            # not_scanned: clients the time budget skipped
     "clients": [
       {"name": "Dr Mona Adel", "path": "<folder>",
        "prefix": "MA" | null,                 # null when skipped, or when the time budget ran out during the prefix
                                               # check: an optional field for the panel (a string otherwise)
        "profile": "dr-mona" | null,
        "counts": {"new": 1, "working": 0, "waiting_for_you": 1, "blocked": 0, "done": 0},
        "truncated": false, "error": null,     # error: the client could not be read (the others still are)
        "skipped": null | "time budget",       # reached after the deadline: listed, not read
        "busy": false,                         # a live writer lease (output/.whynot-lock): a session works here now
        "items": [
          {"id": "C0239", "kind": "clip" | "reel" | "motion" | "episode",
           "state": "new" | "working" | "waiting_for_you" | "blocked" | "done",
           "status": "<the engine's recorded status, e.g. PLAN_APPROVED>" | null,
           "next": "<the engine's next step (`reel next` / `reel episode-next`)>" | null,
           "next_step": "<the next step in the editor's words: approve the plan, pick the reels, ...>",
           "step": "approve_plan",             # the same as a key (STEP_TEXT), for a panel that shows its own words
           "stale": 0,                         # steps whose inputs changed after they ran
           "updated": "<ISO time of the last recorded status>" | null,
           "file": "data/Raw/C0239.MP4" | null, # new items: the raw file
           "partial": false,                   # the time budget ran out before this item's next step was read
           "error": null}]}]}                  # this item's next step could not be read (state blocked); the card stays

States: `waiting_for_you` = the editor's move: approve the plan, pick the reels, or (no session is working in the
client, `busy` false) say "continue <id>" for the next step; `working` = a session holds the client's writer lease
(`busy` true) and the item is mid-pipeline (G3 review M3: an item never shows "in progress" while nothing runs).
`next_step` never contains a command: the panel shows it as it is. The plain table has one row per item, finished
items folded into one "+N done" row per client (`--all` lists them).
"""
from __future__ import annotations

import os
import time
import unicodedata
from pathlib import Path

from .common import (DONE_STATUSES, Context, Paths, client_folders, derived_prefix, is_junk, load_status, now_iso,
                     current_context, read_json, stored_prefix, use_context)

BOARD_VERSION = 1
MAX_CLIENTS = 200
MAX_ITEMS = 200
MAX_FILES = 5000
DEFAULT_BUDGET_S = 5.0
CHECK_EVERY = 128                  # files between two deadline checks in the data/ walk and the new-clip lookup
STATES = ("new", "working", "waiting_for_you", "blocked", "done")
STATE_WORDS = {
    "en": {"new": "new", "working": "in progress", "waiting_for_you": "waiting for you", "blocked": "blocked",
           "done": "done"},
    "ar": {"new": "جديد", "working": "شغّالين عليه", "waiting_for_you": "مستنيك", "blocked": "واقف", "done": "خلص"},
}
STEP_TEXT = {
    "en": {"new_episode": "say “make reels from this episode”", "new_clip": "say “edit the new videos”",
           "done": "nothing: finished", "blocked": "say “status of {id}” to see what blocks it",
           "approve_plan": "approve the plan", "pick_reels": "pick the reels", "status": "say “status of {id}”",
           "proof_check": "proof check: say “continue {id}”",
           "build_premiere": "build in Premiere: say “continue {id}”",
           "build_ae": "build in After Effects: say “continue {id}”", "handoff": "handoff: say “continue {id}”",
           "publish": "publish copy: say “continue {id}”", "continue": "say “continue {id}”"},
    "ar": {"new_episode": "قول «طلّع ريلز من الحلقة»", "new_clip": "قول «عدّل الفيديوهات الجديدة»",
           "done": "مفيش: خلص", "blocked": "قول «حالة {id}» عشان تعرف إيه اللي موقفه",
           "approve_plan": "وافق على الخطة", "pick_reels": "اختار الريلز", "status": "قول «حالة {id}»",
           "proof_check": "فحص الجودة: قول «كمّل {id}»",
           "build_premiere": "البناء في Premiere: قول «كمّل {id}»",
           "build_ae": "البناء في After Effects: قول «كمّل {id}»", "handoff": "التسليم: قول «كمّل {id}»",
           "publish": "نصوص النشر: قول «كمّل {id}»", "continue": "قول «كمّل {id}»"},
}
TABLE_TEXT = {
    "en": {"unreadable": "could not be read", "empty": "no videos yet", "drop": "drop raw clips into data/Raw",
           "skipped": "not scanned (time budget)", "ask_one": "ask for this client alone", "done_n": "+{n} done",
           "foot": "{clients} clients · {items} videos · {waiting_for_you} waiting for you · {new} new · "
                   "{working} in progress · {done} done",
           "not_scanned": " · {n} not scanned", "cut": " · (scan cut short: ask for one client to see all of it)"},
    "ar": {"unreadable": "مقدرتش أقرأه", "empty": "لسه مفيش فيديوهات", "drop": "حط الفيديوهات الخام في data/Raw",
           "skipped": "متفحصش (الوقت خلص)", "ask_one": "اطلب العميل ده لوحده", "done_n": "+{n} خلصوا",
           "foot": "{clients} عميل · {items} فيديو · {waiting_for_you} مستنيينك · {new} جداد · "
                   "{working} شغّالين عليهم · {done} خلصوا",
           "not_scanned": " · {n} متفحصوش", "cut": " · (الفحص اتقطع: اطلب عميل واحد عشان تشوفه كله)"},
}


def _lang(lang) -> str:
    return lang if lang in STEP_TEXT else "en"


def _nfc(s) -> str:
    return unicodedata.normalize("NFC", str(s))


def step_key(next_step: str | None, kind: str, state: str) -> str:
    """The engine's next step as one of the editor's steps (a STEP_TEXT key; the three verbs: drop files · say what
    you want · approve the plan)."""
    n = (next_step or "").strip()
    low = n.lower()
    if state == "new":
        return "new_episode" if kind == "episode" else "new_clip"
    if state == "done" or low == "done":
        return "done"
    if state == "blocked":
        return "blocked"
    if low.startswith(("playback", "approve-plan")):
        return "approve_plan"
    if low.startswith(("select reels", "reels-select")):
        return "pick_reels"
    if not n:
        return "status"
    if low.startswith(("ppro-frames", "motion-frames", "verify", "qc")):
        return "proof_check"
    if low.startswith(("ppro-build", "premiere", "sfx")):
        return "build_premiere"
    if low.startswith(("ae-probe", "motion-build", "motion-render")):
        return "build_ae"
    if low.startswith("handoff"):
        return "handoff"
    if "publish" in low:
        return "publish"
    return "continue"


def plain_step(next_step: str | None, item_id: str, kind: str, state: str, lang: str = "en") -> str:
    """The engine's next step in the editor's words. Never a command."""
    return STEP_TEXT[_lang(lang)][step_key(next_step, kind, state)].format(id=item_id)


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


def _held(root: Path) -> bool:
    """A live writer lease on the client (output/.whynot-lock): a Claude Code session is working there now. Read-only;
    an unreadable lock counts as held (never claims an item waits for the editor while a session may run it)."""
    from . import writer_lock
    try:
        rec = writer_lock.read(root)
        return rec is not None and writer_lock.stale_reason(root, rec) is None
    except Exception:  # noqa: BLE001
        return True


def _over(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _dirs(folder: Path) -> list[Path]:
    try:
        return sorted(d for d in folder.iterdir() if d.is_dir() and not d.name.startswith((".", "_")))
    except OSError:
        return []


def _data_files(root: Path, cap: int = MAX_FILES, deadline: float | None = None) -> tuple[list[tuple[Path, str]], bool]:
    """(file, relative path) under data/, hidden folders skipped, at most cap files, stopped at the deadline;
    (files, cut short)."""
    out, data = [], root / "data"
    for dirpath, dirnames, filenames in os.walk(data):
        if _over(deadline):
            return out, True
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if len(out) >= cap or (len(out) % CHECK_EVERY == 0 and _over(deadline)):
                return out, True
            f = Path(dirpath) / name
            out.append((f, f.relative_to(root).as_posix()))
    return out, False


def _new_items(root: Path, projects: set[str] | None = None, episodes: set[str] | None = None,
               deadline: float | None = None) -> tuple[list[dict], bool]:
    """Raw clips with no started project and episodes with no episode folder (read-only). `projects` / `episodes`:
    the folder names already listed (casefolded), so no clip costs a file-system check. The clip-id map is built once
    and looked up by dict (review I1). (items, cut short by a cap or the deadline)."""
    from . import clip_ids
    from .discover import classify
    from .episode import episode_id_for
    if projects is None:
        projects = {d.name.casefold() for d in _dirs(root / "output" / "projects")}
    if episodes is None:
        episodes = {d.name.casefold() for d in _dirs(root / "output" / "episodes")}
    files, cut = _data_files(root, deadline=deadline)
    clips, eps = [], []
    for n, (f, rel) in enumerate(files):
        if n % CHECK_EVERY == 0 and _over(deadline):
            return [], True
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
    if _over(deadline):
        return [], True
    items = []
    by_rel = clip_ids.index(clip_ids.assign(root, clips, clip_ids.load(root)))
    for rel in clips:
        vid = by_rel.get(clip_ids.key(rel))
        if vid and vid.casefold() not in projects:
            items.append({"id": vid, "kind": "clip", "file": rel})
    seen = set()
    for f in eps:
        eid = episode_id_for(f)
        if eid in seen or eid.casefold() in episodes:
            continue
        seen.add(eid)
        items.append({"id": eid, "kind": "episode", "file": f.relative_to(root).as_posix()})
    return items, cut


def _item(id_: str, kind: str, status=None, nxt=None, stale=0, updated=None, file=None, partial=False,
          error=None) -> dict:
    state = ("blocked" if error else "new" if status is None and nxt is None and file else _state(status, nxt))
    return {"id": id_, "kind": kind, "state": state, "status": status, "next": nxt,
            "next_step": plain_step(nxt, id_, kind, state), "step": step_key(nxt, kind, state),
            "stale": int(stale or 0), "updated": updated, "file": file, "partial": bool(partial), "error": error}


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def _project_item(root: Path, d: Path, next_fn, light: bool) -> dict:
    from .motion_config import is_motion
    p = Paths(root, d.name)
    st = load_status(p)
    kind = "motion" if is_motion(p) else ("reel" if p.p("00_inputs/source.json").exists() else "clip")
    upd = st.get("updated") if st.get("history") else None
    if light or next_fn is None:            # the time budget ran out: the recorded status only
        return _item(d.name, kind, status=st.get("status"), updated=upd, partial=True)
    try:
        doc = next_fn(p)
    except Exception as e:  # noqa: BLE001 — one unreadable project never hides the rest of its client (review M6)
        return _item(d.name, kind, status=st.get("status"), updated=upd, error=_err(e))
    return _item(d.name, kind, status=st.get("status"), nxt=doc.get("next"), stale=len(doc.get("stale") or []),
                 updated=upd)


def _episode_item(root: Path, d: Path, light: bool) -> dict:
    from .episode import EpisodePaths, _episode_state, episode_next
    ep = EpisodePaths(root, d.name)
    if light:
        return _item(d.name, "episode", status=_episode_state(ep), partial=True)
    try:
        doc = episode_next(ep)
    except Exception as e:  # noqa: BLE001 — as for a project (review M6)
        return _item(d.name, "episode", error=_err(e))
    return _item(d.name, "episode", status=doc.get("state"), nxt=doc.get("next"), stale=len(doc.get("stale") or []))


def _guarded(fn, kind: str, root: Path, d: Path, *rest) -> dict:
    """One item; anything that escapes the item's own handling (an unreadable status file) becomes that item's
    error, never the card's (review M6)."""
    try:
        return fn(root, d, *rest)
    except Exception as e:  # noqa: BLE001
        return _item(d.name, kind, error=_err(e))


def client_card(root: Path, next_fn=None, deadline: float | None = None) -> tuple[dict, bool]:
    """One client's card (see the module docstring) and whether the time budget ran out while reading it. A client
    reached after the deadline is not read at all (`skipped`)."""
    root = Path(root)
    card = {"name": _nfc(root.name), "path": str(root), "prefix": None, "profile": None,
            "counts": dict.fromkeys(STATES, 0), "truncated": False, "error": None, "skipped": None, "busy": False,
            "items": []}
    if _over(deadline):
        card["skipped"], card["truncated"] = "time budget", True
        return card, True
    over = False
    with use_context(Context(root)):
        try:
            stored = stored_prefix()
            card["prefix"] = stored or derived_prefix(root, deadline)
            over = card["prefix"] is None       # the project scan for the prefix ran out of time
            if not stored and card["prefix"]:   # next_doc's project_prefix() reuses it: one scan per card (m2)
                ctx = current_context()
                ctx.__dict__.setdefault("_prefix_cache", {})[str(ctx.root) if ctx.root else ""] = card["prefix"]
            card["profile"] = (read_json(root / "output/client_database/reel-profile/profile.json", {}) or {}).get("id")
            projects = _dirs(root / "output" / "projects")
            episodes = _dirs(root / "output" / "episodes")
            card["truncated"] = len(projects) > MAX_ITEMS or len(episodes) > MAX_ITEMS
            for d in episodes[:MAX_ITEMS]:
                over = over or _over(deadline)
                card["items"].append(_guarded(_episode_item, "episode", root, d, over))
            for d in projects[:MAX_ITEMS]:
                over = over or _over(deadline)
                card["items"].append(_guarded(_project_item, "clip", root, d, next_fn, over))
            over = over or _over(deadline)
            if not over:                        # no data/ walk after the deadline
                new, cut = _new_items(root, {d.name.casefold() for d in projects},
                                      {d.name.casefold() for d in episodes}, deadline)
                over = _over(deadline)
                card["truncated"] = card["truncated"] or cut
                card["items"] += [_item(n["id"], n["kind"], file=n["file"]) for n in new[:MAX_ITEMS]]
        except Exception as e:  # noqa: BLE001 — one unreadable client never hides the others
            card["error"] = _err(e)
    card["truncated"] = card["truncated"] or over
    card["busy"] = _held(root)
    if not card["busy"]:                        # G3 review M3: nothing runs until the editor says "continue <id>"
        for it in card["items"]:
            if it["state"] == "working":
                it["state"] = "waiting_for_you"
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
              **{s: sum(c["counts"][s] for c in clients) for s in STATES},
              "not_scanned": sum(1 for c in clients if c["skipped"])}
    return {"ok": True, "board": BOARD_VERSION, "clients_root": str(base) if base else None, "generated": now_iso(),
            "elapsed_ms": int((time.monotonic() - t0) * 1000), "truncated": truncated, "totals": totals,
            "clients": clients}


def _cell(s) -> str:
    return str(s if s is not None else "").replace("|", "/").replace("\n", " ")


def table(doc: dict, lang: str = "ar", show_all: bool = False) -> str:
    """The plain table (Markdown) in the editor's language (ar | en): one row per item, finished items folded into
    one "+N done" row per client unless show_all, one row for a client without items, unread or not scanned."""
    lang = _lang(lang)
    tx, words, steps = TABLE_TEXT[lang], STATE_WORDS[lang], STEP_TEXT[lang]
    rows = ["| Client · العميل | Item · الفيديو | State · الحالة | Next step · الخطوة الجاية |", "|---|---|---|---|"]
    for c in doc.get("clients", []):
        name = _cell(c["name"])
        if c.get("skipped"):
            rows.append(f"| {name} | — | {tx['skipped']} | {tx['ask_one']} |")
            continue
        if c.get("error"):
            rows.append(f"| {name} | — | {tx['unreadable']} | {_cell(c['error'])} |")
            continue
        if not c.get("items"):
            rows.append(f"| {name} | — | {tx['empty']} | {tx['drop']} |")
        done = 0
        for it in c.get("items", []):
            if it["state"] == "done" and not show_all:
                done += 1
                continue
            kind = "" if it["kind"] == "clip" else f" ({it['kind']})"
            key = it.get("step") or step_key(it.get("next"), it["kind"], it["state"])
            step = steps.get(key, steps["continue"]).format(id=it["id"])
            if it.get("error"):
                rows.append(f"| {name} | {_cell(it['id'])}{kind} | {tx['unreadable']} | {_cell(step)} "
                            f"({_cell(it['error'])}) |")
                continue
            rows.append(f"| {name} | {_cell(it['id'])}{kind} | {words.get(it['state'], it['state'])} | {_cell(step)} |")
        if done:
            rows.append(f"| {name} | {tx['done_n'].format(n=done)} | {words['done']} | — |")
    t = {k: 0 for k in ("clients", "items", *STATES)}
    t.update(doc.get("totals") or {})
    foot = tx["foot"].format(**t)
    if t.get("not_scanned"):
        foot += tx["not_scanned"].format(n=t["not_scanned"])
    if doc.get("truncated"):
        foot += tx["cut"]
    return "\n".join(rows + ["", foot])
