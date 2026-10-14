"""The job journal of `reel serve` (3.0 Addendum G2, hardening H1): every routed command, on disk, so a result outlives
the session that asked for it and the daemon that ran it.

    <home>/serve/jobs/<request_id>.json   one entry per request id (user-only folder, security.private_dir):
        {request_id, action, session_kind, route: cep|uxp, lane?, state, submitted_at, updated_at, job_id?, result?,
         data_sha?, expires_at?}
        state: received (routed) -> queued (its <jid>.job.json is in the CEP queue) -> claimed (the bridge took it) ->
               done | failed (the v4 result is stored) | interrupted (it can no longer finish: a stored ok:false result
               says why). A UXP-routed entry goes received -> done | failed | interrupted.
Rules:
  * the file name IS the request id, so the id must pass valid_id (a letter or digit first, then letters, digits,
    `.`, `_`, `-`, at most 64, no `..`, no Windows device name); path() also checks that the file resolves inside the
    folder. Nothing else names a file here;
  * every write is atomic (a private temp file in the same folder, then os.replace) and size-capped (ENTRY_MAX): an
    over-size result is replaced by its summary (ok, error, how; an ok:true readback becomes {} and the entry says
    result_truncated). The engine token never reaches an entry: nothing here is given it;
  * retention (prune): entries older than KEEP_S (7 days) go, then all but the newest KEEP (200);
  * the snapshot shows summaries() (the newest SNAPSHOT_JOBS): request_id, action, state, the two instants and, once
    settled, result {ok, code?} (docs/adobe/eng-data-contract.md 2.6). No host text, no path, no data, no token.
The CEP queue files are only READ here (lib/cep_queue.py owns them): find_job() matches a request to its queue job by
the CEP name and a hash of its data (the queue's <jid>.data.json is {...data, action, job_id, submitted}); job_state()
and read_result() follow it. reconcile() runs once at daemon start: an active entry whose result file exists becomes
done / failed, one still in a live bridge's queue is returned for the router to follow, everything else becomes
interrupted.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from contract import validate_result
from contract.cep import from_cep

from . import security

__all__ = ["Journal", "STATES", "ACTIVE", "FINAL", "ENTRY_MAX", "KEEP", "KEEP_S", "SNAPSHOT_JOBS", "valid_id",
           "data_sha", "find_job", "job_state", "read_result", "reconcile", "interrupted_result", "summary"]

log = logging.getLogger(__name__)

STATES = ("received", "queued", "claimed", "done", "failed", "interrupted")
ACTIVE = frozenset({"received", "queued", "claimed"})
FINAL = frozenset({"done", "failed", "interrupted"})
ENTRY_MAX = 256 * 1024             # bytes per entry on disk
KEEP = 200                         # entries kept (newest first)
KEEP_S = 7 * 24 * 3600             # ... and none older than this
SNAPSHOT_JOBS = 20                 # summaries in a panel state
TEXT_MAX = 2000                    # error / how in a summary (session.schema.json maxLength)
TMP_STALE_S = 3600                 # a temp file older than this is a crashed write's leftover
DATA_MAX = 8 * 1024 * 1024         # a queue data file bigger than this is never read
_RID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_DEVICES = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))})
_QUEUE_KEYS = ("action", "job_id", "submitted")      # what cep_queue.submit adds to the data file


def valid_id(rid) -> bool:
    """A request id that can name a journal file on every platform."""
    if not isinstance(rid, str) or not _RID_RE.fullmatch(rid) or ".." in rid:
        return False
    return rid.split(".", 1)[0].upper() not in _DEVICES


def _now() -> tuple[str, float]:
    t = time.time()
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="milliseconds"), t


def _clip(text, n: int = TEXT_MAX):
    if not isinstance(text, str):
        return None
    return text if len(text) <= n else text[:n - 1] + "…"


def data_sha(data) -> str:
    """The hash find_job matches a queue data file by (the keys cep_queue adds are left out on both sides)."""
    d = {k: v for k, v in (data or {}).items() if k not in _QUEUE_KEYS} if isinstance(data, dict) else {}
    raw = json.dumps(d, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def interrupted_result(action: str, rid: str, why: str, how: str) -> dict:
    """The ok:false v4 result an interrupted entry stores (and replays)."""
    return {"ok": False, "action": action, "id": rid, "error": why, "how": how}


def summary(entry: dict) -> dict:
    """What the panel state shows of one entry (session.schema.json $defs/job_summary, eng-data-contract.md 2.6):
    request_id, action, state, the two instants and, once settled, result {ok, code?}. Never the host's text."""
    stamp = _now()[0]
    out = {"request_id": entry["request_id"], "action": entry["action"], "state": entry["state"],
           "submitted_at": entry.get("submitted_at") or stamp, "updated_at": entry.get("updated_at") or stamp}
    res = entry.get("result")
    if isinstance(res, dict) and entry["state"] in FINAL:
        out["result"] = {"ok": bool(res.get("ok"))}
        if entry["state"] == "interrupted":
            out["result"]["code"] = "interrupted"
    return out


def _shrunk(result: dict) -> dict:
    """An over-size result's summary: still a valid v4 result shape (ok:true keeps an empty readback)."""
    out = {k: result[k] for k in ("ok", "action", "id") if k in result}
    if result.get("ok"):
        out["readback"] = {}
    else:
        out["error"] = _clip(result.get("error")) or "failed"
        if _clip(result.get("how")):
            out["how"] = _clip(result.get("how"))
    return out


class Journal:
    """The journal of one engine home. One daemon per home (serve.lock), so the in-memory index is authoritative once
    load() ran; every method is thread-safe (reconcile runs on a worker thread)."""

    def __init__(self, home):
        self.dir = Path(home) / "serve" / "jobs"
        self._lock = threading.RLock()
        self._index: dict[str, dict] = {}            # request id -> summary + "_t" (submitted, epoch)
        self._loaded = False

    # ------------------------------------------------------------------------------------------------ files
    def path(self, rid: str) -> Path:
        """<dir>/<rid>.json, refused (ValueError) unless the id is valid and the file resolves inside the folder."""
        if not valid_id(rid):
            raise ValueError("this request id cannot name a journal entry")
        p = self.dir / f"{rid}.json"
        if p.resolve().parent != self.dir.resolve():
            raise ValueError("a journal entry must stay inside the jobs folder")
        return p

    def _ensure_dir(self) -> None:
        if not self.dir.is_dir():
            security.private_dir(self.dir)

    def _read(self, p: Path) -> dict | None:
        try:
            if p.stat().st_size > ENTRY_MAX:
                return None
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(doc, dict) or doc.get("request_id") != p.name[:-5] or doc.get("state") not in STATES \
                or not isinstance(doc.get("action"), str):
            return None
        return doc

    def _write(self, entry: dict) -> dict:
        p = self.path(entry["request_id"])
        text = json.dumps(entry, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(text.encode("utf-8")) > ENTRY_MAX and isinstance(entry.get("result"), dict):
            entry = dict(entry, result=_shrunk(entry["result"]), result_truncated=True)
            text = json.dumps(entry, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(text.encode("utf-8")) > ENTRY_MAX:
            raise ValueError("a journal entry is over its size cap")
        self._ensure_dir()
        tmp = self.dir / f".{uuid.uuid4().hex}.tmp"
        try:
            fd = security.open_private(tmp, os.O_WRONLY | os.O_TRUNC)
            with os.fdopen(fd, "wb") as f:
                f.write(text.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            for i in range(20):                 # Windows: a reader holding the old file refuses the replace briefly
                try:
                    os.replace(tmp, p)
                    break
                except PermissionError:
                    if i == 19:
                        raise
                    time.sleep(0.01)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise
        self._index[entry["request_id"]] = dict(summary(entry), _t=entry.get("_t", 0.0))
        return entry

    # ------------------------------------------------------------------------------------------------ entries
    def load(self) -> None:
        """Index every entry on disk (once; the daemon calls it at start through reconcile)."""
        with self._lock:
            self._index.clear()
            try:
                files = list(self.dir.glob("*.json"))
            except OSError:
                files = []
            for p in files:
                if not valid_id(p.name[:-5]):
                    continue
                doc = self._read(p)
                if doc is not None:
                    self._index[doc["request_id"]] = dict(summary(doc), _t=float(doc.get("_t") or 0.0))
            self._loaded = True

    def get(self, rid: str) -> dict | None:
        if not valid_id(rid):
            return None
        with self._lock:
            return self._read(self.path(rid))

    def entries(self) -> list[dict]:
        """Every readable entry, newest first."""
        with self._lock:
            if not self._loaded:
                self.load()
            out = [e for e in (self.get(rid) for rid in list(self._index)) if e is not None]
        return sorted(out, key=lambda e: float(e.get("_t") or 0.0), reverse=True)

    def start(self, rid: str, *, action: str, session_kind: str | None, route: str, lane: str | None = None,
              data=None, expires_at: str | None = None) -> dict:
        """A routed command: a new entry in state received."""
        stamp, t = _now()
        entry = {"request_id": rid, "action": action, "session_kind": session_kind or "unknown", "route": route,
                 "state": "received", "submitted_at": stamp, "updated_at": stamp, "_t": t}
        if lane:
            entry["lane"] = lane
        if route == "cep":
            entry["data_sha"] = data_sha(data)
        if expires_at:
            entry["expires_at"] = str(expires_at)[:64]
        with self._lock:
            out = self._write(entry)
            self.prune()
            return out

    def update(self, rid: str, **fields) -> dict | None:
        with self._lock:
            entry = self.get(rid)
            if entry is None:
                return None
            entry.update(fields)
            entry["updated_at"] = _now()[0]
            return self._write(entry)

    def finish(self, rid: str, result: dict, state: str | None = None) -> dict | None:
        """Store the final result: done (ok:true), failed (ok:false) or the given final state (interrupted)."""
        st = state or ("done" if result.get("ok") else "failed")
        if st not in FINAL:
            raise ValueError(f"{st} is not a final state")
        return self.update(rid, state=st, result=result)

    def summaries(self, n: int = SNAPSHOT_JOBS) -> list[dict]:
        """The newest n entries' summaries (from the index: no file is read)."""
        with self._lock:
            if not self._loaded:
                self.load()
            rows = sorted(self._index.values(), key=lambda s: s["_t"], reverse=True)[:max(0, n)]
            return [{k: v for k, v in s.items() if k != "_t"} for s in rows]

    def prune(self, now: float | None = None) -> list[str]:
        """Retention: entries older than KEEP_S go, then all but the newest KEEP; stale temp files too."""
        now = time.time() if now is None else now
        gone = []
        with self._lock:
            if not self._loaded:
                self.load()
            rows = sorted(self._index.items(), key=lambda kv: kv[1]["_t"], reverse=True)
            for i, (rid, s) in enumerate(rows):
                if i >= KEEP or now - s["_t"] > KEEP_S:
                    with contextlib.suppress(OSError, ValueError):
                        self.path(rid).unlink()
                    self._index.pop(rid, None)
                    gone.append(rid)
            with contextlib.suppress(OSError):
                for tmp in self.dir.glob(".*.tmp"):
                    with contextlib.suppress(OSError):
                        if now - tmp.stat().st_mtime > TMP_STALE_S:
                            tmp.unlink()
        return gone


# ------------------------------------------------------------------------------------------------ the CEP queue (read)
def find_job(queue, cep_name: str, sha: str, since: float = 0.0) -> str | None:
    """The queue job id whose data file is this request's (same CEP action, same data hash), written no earlier than
    `since` (epoch, 2 s of slack); the oldest such when there are several."""
    best = None
    try:
        files = list(Path(queue).glob("*.data.json"))
    except OSError:
        return None
    for f in files:
        try:
            st = f.stat()
            if st.st_mtime < since - 2.0 or st.st_size > DATA_MAX:
                continue
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict) or doc.get("action") != cep_name or data_sha(doc) != sha:
            continue
        if best is None or st.st_mtime < best[0]:
            best = (st.st_mtime, f.name[:-len(".data.json")])
    return best[1] if best else None


def job_state(queue, jid: str) -> str | None:
    """done (a result file), claimed (.running / .claimed), queued (.job.json) or None (no file of it is left)."""
    q = Path(queue)
    if (q / f"{jid}.result.json").exists():
        return "done"
    if (q / f"{jid}.running").exists() or (q / f"{jid}.claimed").exists():
        return "claimed"
    if (q / f"{jid}.job.json").exists():
        return "queued"
    return None


def read_result(queue, jid: str, action: str, rid: str, app: str = "Premiere") -> dict | None:
    """The v4 result of a finished queue job (what cep_queue._wait + the FileQueueAdapter make of <jid>.result.json),
    or None while the file is missing or still being written. The router validates it before anyone sees it."""
    try:
        raw = json.loads((Path(queue) / f"{jid}.result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("error") == "expired":
        res = from_cep(action, {"ok": False, "error": f"timeout: the job expired before {app} could start it",
                                "how": f"{app} was busy (another job or a dialog). Dismiss any dialog, then run the "
                                       "command again."}, id=rid)
    else:
        inner = raw.get("result")
        if isinstance(inner, str):
            with contextlib.suppress(ValueError):
                inner = json.loads(inner)
        if isinstance(inner, dict):
            res = from_cep(action, inner, id=rid)
        else:
            err = raw.get("error") if isinstance(raw.get("error"), str) and raw["error"].strip() else \
                "The bridge queue reported a failure."
            res = from_cep(action, {"ok": False, "error": err}, id=rid)
    if not res.get("ok") and not res.get("how"):
        res["how"] = (f"Check that WhyNot Cut runs in {app} (it starts by itself with {app}; restart {app} if it does "
                      "not answer), then run the command again.")
    res = {**res, "id": rid}
    if res.get("action") != action or validate_result(res):          # the router's own rule (Router.checked)
        res = {"ok": False, "action": action, "id": rid, "error": "host answered outside the contract",
               "how": "Update the WhyNot Cut panel and bridge to this engine's version, then run the command again."}
    return res


APP_NAMES = {"aftereffects": "After Effects", "premiere": "Premiere"}
GONE_WHY = "The job stopped before it finished: {app} or the WhyNot Cut engine was closed while it ran."
GONE_HOW = "Open {app} with the WhyNot Cut panel, check the project, then press Try again."
UXP_WHY = "The command stopped when the WhyNot Cut engine restarted."
UXP_HOW = "Press Try again."


def reconcile(journal: Journal, queue_for, alive_for, cep_name_for) -> list[dict]:
    """Daemon start: settle every active entry against the queue files. `queue_for(lane)` is the lane's queue folder,
    `alive_for(lane)` whether its bridge beats now, `cep_name_for(action)` the CEP name. Returns the entries still
    live in a beating bridge's queue (with their job_id): the router follows them to their result."""
    journal.load()
    live = []
    alive_cache: dict[str, bool] = {}
    for entry in journal.entries():
        if entry["state"] not in ACTIVE:
            continue
        rid, action = entry["request_id"], entry["action"]
        lane = entry.get("lane") or "premiere"
        app = APP_NAMES.get(lane, "Premiere")
        if entry.get("route") != "cep":
            journal.finish(rid, interrupted_result(action, rid, UXP_WHY, UXP_HOW), "interrupted")
            continue
        try:
            queue = Path(queue_for(lane))
        except Exception:                                    # noqa: BLE001 — no queue: nothing can finish it
            queue = None
        jid = entry.get("job_id")
        if queue is not None and not jid and entry.get("data_sha"):
            jid = find_job(queue, cep_name_for(action), entry["data_sha"], float(entry.get("_t") or 0.0))
        state = job_state(queue, jid) if queue is not None and jid else None
        if state == "done":
            res = read_result(queue, jid, action, rid, app)
            if res is not None:
                journal.update(rid, job_id=jid)
                journal.finish(rid, res)
                continue
            state = "claimed"                                # still being written: follow it
        if state in ("queued", "claimed"):
            if lane not in alive_cache:
                try:
                    alive_cache[lane] = bool(alive_for(lane))
                except Exception:                            # noqa: BLE001
                    alive_cache[lane] = False
            if alive_cache[lane]:
                live.append(journal.update(rid, job_id=jid, state=state))
                continue
        journal.finish(rid, interrupted_result(action, rid, GONE_WHY.format(app=app), GONE_HOW.format(app=app)),
                       "interrupted")
    journal.prune()
    return [e for e in live if e is not None]
