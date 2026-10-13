"""CEP -> v4: the pure adapter between the legacy bridge's queue and the command contract.

Today the engine talks to Premiere / After Effects through the CEP file queue (lib/cep_queue.py): a flat data file
`{...data, action, job_id, submitted}` out, a parsed response `{ok, action, result}` or `{ok: false, action, error, line}`
back. Contract v4 is `{protocol, id, action, data, expires_at}` out and `{ok, action, readback, error?, how?, id?}` back.
These functions convert between the two; they do no I/O and keep no state, so the engine daemon and the tests share them.

    to_request(action_v4, data, *, id, expires_at)   the v4 request for a command
    data_from_cep(cep_data)                          a queue data file without its bookkeeping keys
    from_cep(action_v4, cep_response, *, id=None)    the parsed queue response -> a v4 result
    CEP_NAME[action_v4] / V4_NAME[cep_name]          the legacy action names (protocol.json); v4-only actions have none

What from_cep decides (the legacy bridge reported failures in several shapes; v4 has one):

* `{ok: true, result: {error: "...", ...}}` is a failure, whatever else the result holds: Premiere's CEP `build_project`
  said "project exists (set overwrite_existing)" this way, and "sequence not found after XML import" with a `log`. It is
  `ok: false` with that error; the other keys travel as `readback` only when they validate as the action's
  `readback_failure` (any object when the action defines none), otherwise they are left out.
* `{ok: false, error, line?}` (a script exception, "bridge not running", a timeout) is `ok: false` with the error; the
  script line is folded into the sentence.
* `"EvalScript error."` (the panel's `{ok: false, result: "EvalScript error."}` when the script fails inside the host;
  cep_queue hands the bare string on) is `ok: false` quoting the string, with a `how` about the host script.
* `{ok: false, result: {ok: false, reason, ...}}` (After Effects refusing to touch unsaved work, a failed read-back) is
  `ok: false` with the whole result as `readback`: motion_build.build tells REFUSED from FAILED by `readback.reason`.
* `{ok: false, result: {failed: [...], ...}}` (scenes that did not build) is `ok: false` with the partial result as `readback`.
* A top-level `how` on an `{ok: false, error}` answer is forwarded as the result's `how`; without one it is derived from
  the bridge status or the timeout.
* Anything else with ok true is `ok: true` and the result is the `readback`. The host's own top-level `ok` flag inside the
  result belongs to the envelope and is not copied.

Every failure it builds validates with `contract.validate_result`; an ok answer validates when the host's readback does
(the point of the golden fixtures).
"""
from __future__ import annotations

import copy

from . import ACTIONS, PROTOCOL
from .validator import load, validate

CEP_NAME: dict[str, str] = {a: e["cep"] for a, e in load("protocol")["actions"].items() if e["cep"]}
V4_NAME: dict[str, str] = {c: a for a, c in CEP_NAME.items()}
BOOKKEEPING = ("action", "job_id", "submitted")           # what cep_queue.submit adds to every data file


def to_request(action_v4: str, data: dict | None, *, id: str, expires_at: str) -> dict:
    """The v4 request envelope for `action_v4` with a copy of `data` (validate it with contract.validate_request)."""
    if action_v4 not in ACTIONS:
        raise ValueError(f"unknown action {action_v4!r}")
    return {"protocol": PROTOCOL, "id": id, "action": action_v4, "data": copy.deepcopy(data) if data is not None else {},
            "expires_at": expires_at}


def data_from_cep(cep_data: dict) -> dict:
    """The queue's flat data file without the keys cep_queue.submit adds (action, job_id, submitted): the v4 `data`."""
    return {k: copy.deepcopy(v) for k, v in cep_data.items() if k not in BOOKKEEPING}


def _fail(action: str, id: str | None, error: str, how: str | None = None, readback: dict | None = None) -> dict:
    out: dict = {"ok": False, "action": action}
    if id is not None:
        out["id"] = id
    if readback is not None:
        out["readback"] = readback
    out["error"] = error
    if how:
        out["how"] = how
    return out


def _failure_readback(action: str, rest: dict) -> dict | None:
    """`rest` as the readback of a failed result: kept when it validates as the action's `readback_failure` (any object
    when the action defines none), else left out, so the result always validates."""
    if not rest:
        return None
    if "readback_failure" in load(action).get("$defs", {}) and validate(rest, f"{action}#/$defs/readback_failure"):
        return None
    return rest


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _refusal(result: dict) -> tuple[str, str | None]:
    """(error, how) for an `ok: false` result that carries a reason or failed scenes."""
    reason = result.get("reason")
    if reason in ("dirty", "dirty_target"):
        where = result.get("project") or "an untitled project"
        return (f"After Effects has unsaved changes in {where}.",
                "Save or close the project in After Effects, then run the command again.")
    if isinstance(reason, str) and reason:
        return reason, None                                  # the host's own sentence ("MAIN_x not found in the open project")
    failed = result.get("failed")
    if isinstance(failed, list) and failed:
        first = failed[0] if isinstance(failed[0], dict) else {}
        what = f"{first.get('scene')}: {first.get('error')}" if first.get("scene") else str(failed[0])
        return (f"{_plural(len(failed), 'scene')} did not build (first: {what}).",
                "Fix the cause named in the readback and build again.")
    return "The host reported a failure.", None


def _script_failed(action: str, id: str | None, text: str) -> dict:
    return _fail(action, id, f"The bridge script failed in the host ({text.strip()})",
                 "Look at the script or the host, not the panel: restart the app, then run the command again.")


def from_cep(action_v4: str, cep_response, *, id: str | None = None) -> dict:
    """The v4 result for the parsed queue response (the `{ok, action, result | error, line}` that cep_queue.submit
    hands back as `response`; its own failures `{ok: false, error, ...}` are understood too). `id` is the request's id."""
    if action_v4 not in CEP_NAME:
        raise ValueError(f"{action_v4!r} has no CEP equivalent" if action_v4 in ACTIONS else f"unknown action {action_v4!r}")
    name = CEP_NAME[action_v4]
    if isinstance(cep_response, str) and cep_response.strip():       # the panel's {ok:false, result:"EvalScript error."}
        return _script_failed(action_v4, id, cep_response)
    if not isinstance(cep_response, dict):
        return _fail(action_v4, id, "The bridge did not send an answer the engine can read.",
                     "Check that WhyNot Cut runs in the app (restart the app if it does not answer) and run the "
                     "command again.")
    said = cep_response.get("action")
    if isinstance(said, str) and said != name:
        return _fail(action_v4, id, f"The bridge answered {said!r} to {name!r}.",
                     "Run the command again; if it repeats, restart the app.")
    result = cep_response.get("result")
    ok = cep_response.get("ok") is True
    if not ok and isinstance(result, str) and result.strip():          # the same string inside an {ok:false, result} dict
        return _script_failed(action_v4, id, result)
    named = result.get("error") if isinstance(result, dict) else None
    named = named.strip() if isinstance(named, str) else ""
    if isinstance(result, dict) and not (ok and not named):
        rest = {k: copy.deepcopy(v) for k, v in result.items() if k not in ("ok", "error")}
        if named:                                            # ok:true (or false) with an error: the legacy build_project shape
            how = ("Set overwrite_existing to true to replace it (the old file is kept as a backup), or choose another "
                   "project_path." if "overwrite_existing" in named else None)
            return _fail(action_v4, id, result["error"], how, _failure_readback(action_v4, rest))
        error, how = _refusal(result)                        # the action itself answered ok:false: keep its evidence
        return _fail(action_v4, id, error, how, _failure_readback(action_v4, rest))
    if ok:
        if not isinstance(result, dict):
            return _fail(action_v4, id, "The host answered ok without a result.",
                         "Run the command again; if it repeats, restart the app.")
        out: dict = {"ok": True, "action": action_v4}
        if id is not None:
            out["id"] = id
        out["readback"] = {k: copy.deepcopy(v) for k, v in result.items() if k != "ok"}
        return out
    err = cep_response.get("error")
    err = err if isinstance(err, str) and err else "The host reported a failure."
    line = cep_response.get("line")
    if isinstance(line, int) and not isinstance(line, bool):
        err = f"{err} (script line {line})"
    how = cep_response.get("how")                            # an answer that already says what to do keeps it
    how = how if isinstance(how, str) and how.strip() else None
    status = cep_response.get("status")
    if how:
        pass
    elif isinstance(status, dict) and isinstance(status.get("detail"), str) and status["detail"]:
        how = status["detail"]                               # "no heartbeat: start Premiere ..."
    elif err.startswith("timeout"):
        how = "Dismiss any dialog the app is showing, then run the command again."
    return _fail(action_v4, id, err, how)
