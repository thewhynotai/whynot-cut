#!/usr/bin/env python3
"""R-T8 security watch (3.0 Phase 4, Task 20): turn a GitHub event payload into plain-English findings.

Run by .github/workflows/security-watch.yml on a Linux runner; stdlib only, Python 3.12.

    findings(event_name, payload, allow, changed=None) -> list[str]     pure; [] when all is as expected
    main(argv, env=None) -> int

Rules (logins and emails compare case-insensitively):
  push     the pusher is not in allow["pushers"]; a commit (commits[] and head_commit) has an author or committer
           email outside allow["emails"]; the push was forced (history rewritten) or deleted a ref: ALWAYS a
           finding, even from an allowed pusher. `<id>+<login>@users.noreply.github.com` matches only when <login> is
           an allowed pusher. GitHub's own web committer (noreply@github.com, on merges and web edits) is not
           checked as a committer, because the AUTHOR of those commits still is.
           A push that changes anything under .github/ or tools/ci/security_watch.py is ALWAYS a finding too, even
           from the owner: the owner then hears about every change to the watch itself. The file lists come from
           `changed` (the workflow asks the API, because the Actions push payload has no added/modified/removed) and,
           when a recorded webhook payload has them, from the commits.
  public   the repository was made public: ALWAYS a finding.
  delete   a branch or tag was deleted: ALWAYS a finding. (The workflow does not subscribe to `delete`: a push with
           deleted=true covers it. Kept for a payload fed by hand.)
  member   a collaborator was added or edited: ALWAYS a finding. For a future trigger; GitHub has no `member`
           workflow event today, so the shipped workflow never feeds this.
  anything else: no finding.

Every value taken from the payload is shown inside a markdown code span with backticks removed, so a hostile
email, name or ref cannot render a link, an @-mention or a #reference in the issue.

main reads GITHUB_EVENT_NAME and GITHUB_EVENT_PATH (or --event NAME --payload FILE), the allowlist
(.github/security-allowlist.json, or --allowlist FILE) and optionally --changed-files FILE (one path per line; the
single line `!unavailable` means the list could not be fetched). With findings it appends `title=` and a heredoc
`body<<DELIM` to $GITHUB_OUTPUT (or prints them with --dry-run). Exit 0 on any well-formed payload (findings are not
errors); exit 2 when the payload, the allowlist or the changed-files list cannot be read, so the workflow can still say
the watch itself broke.
"""
import argparse
import json
import os
import re
import secrets
import sys
from pathlib import Path

WEB_COMMITTER = "noreply@github.com"   # the committer GitHub itself puts on web-UI merges and edits
NOREPLY_RE = re.compile(r"^(?:[0-9]+\+)?([A-Za-z0-9-]+)@users\.noreply\.github\.com$", re.IGNORECASE)
CHANGED_UNAVAILABLE = "!unavailable"
FILE_LIST_CAP = 300     # the compare API stops listing files here, so a list this long may be incomplete
SHOW_PATHS = 5
MAX_BODY = 20000
MAX_TITLE = 120
MAX_FIELD = 200
_SEPARATORS = "  \x85"


def _clean(v, limit=MAX_FIELD) -> str:
    """One printable line, bounded, with no backtick: payload text is attacker-controlled and ends up in an issue
    body and in $GITHUB_OUTPUT. (A backtick would let it close the code span it is shown in.)"""
    s = "" if v is None else str(v)
    s = "".join(" " if (ord(c) < 32 or ord(c) == 127 or c in _SEPARATORS) else c for c in s)
    s = s.replace("`", "'")
    s = re.sub(r" {2,}", " ", s).strip()
    return s if len(s) <= limit else s[: limit - 3] + "..."


def _c(v, limit=MAX_FIELD, empty="") -> str:
    """A payload value as a markdown code span: inside one, GitHub renders no link, no @-mention and no #ref."""
    s = _clean(v, limit)
    if s:
        return f"`{s}`"
    return f"`{empty}`" if empty else ""


def _short(sha) -> str:
    s = _clean(sha, 64)
    return s[:7] if s else "unknown"


def _low(v) -> str:
    return ("" if v is None else str(v)).strip().casefold()


def _norm_path(p) -> str:
    s = str(p or "").strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def _is_watched_path(p) -> bool:
    """The watch itself: anything under .github/ (workflows, allowlist) and the decision script."""
    s = _norm_path(p).casefold()
    return s.startswith(".github/") or s == "tools/ci/security_watch.py"


def _email_ok(email, pushers: set, emails: set) -> bool:
    e = _low(email)
    if not e:
        return False
    if e in emails:
        return True
    m = NOREPLY_RE.match(e)
    return bool(m) and m.group(1) in pushers


def _touched_paths(p: dict, changed) -> list:
    """Watched paths this push changes: from the commits' added/modified/removed (a recorded webhook payload) and
    from `changed` (the compare API's list). Ordered, no repeats."""
    seen, out = set(), []
    paths = []
    for c in list(p.get("commits") or []) + ([p["head_commit"]] if p.get("head_commit") else []):
        if isinstance(c, dict):
            for key in ("added", "modified", "removed"):
                paths += [x for x in (c.get(key) or []) if isinstance(x, str)]
    paths += [x for x in (changed or []) if isinstance(x, str)]
    for x in paths:
        n = _norm_path(x)
        if n and n != CHANGED_UNAVAILABLE and _is_watched_path(n) and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _push_findings(p: dict, allow: dict, changed=None) -> list:
    pushers = {_low(x) for x in allow["pushers"]}
    emails = {_low(x) for x in allow["emails"]}
    ref = _c(p.get("ref"), empty="(unknown ref)")
    span = _c(f"{_short(p.get('before'))}..{_short(p.get('after'))}")
    pusher = (p.get("pusher") or {}).get("name") or (p.get("sender") or {}).get("login")
    who = _c(pusher, empty="an unknown pusher")
    out = []
    if p.get("deleted"):
        out.append(f"The ref {ref} was deleted (it pointed at {_c(_short(p.get('before')))}), by {who}.")
    if p.get("forced"):
        out.append(f"The ref {ref} was force-pushed, which rewrites history ({span}), by {who}.")
    if not pusher:
        out.append(f"A push to {ref} ({span}) has no pusher name in the event, so it cannot be checked.")
    elif _low(pusher) not in pushers:
        out.append(f"The pusher {who} is not on the allowlist (push to {ref}, {span}).")
    bad = {}      # email (lower-case) -> [shown email, roles in order, first commit]; one finding per email
    commits = list(p.get("commits") or [])
    if p.get("head_commit"):
        commits.append(p["head_commit"])
    for c in commits:
        if not isinstance(c, dict):
            continue
        for role in ("author", "committer"):
            email = (c.get(role) or {}).get("email")
            if role == "committer" and _low(email) == WEB_COMMITTER:
                continue
            if _email_ok(email, pushers, emails):
                continue
            entry = bad.setdefault(_low(email), [_c(email, empty="(empty)"), [], _c(_short(c.get("id")))])
            if role not in entry[1]:
                entry[1].append(role)
    for shown, roles, sha in bad.values():
        out.append(f"A commit in the push to {ref} ({span}) has an {' and '.join(roles)} email that is not on the "
                   f"allowlist: {shown} (first seen in commit {sha}).")
    if changed is not None and CHANGED_UNAVAILABLE in [str(x).strip() for x in changed]:
        out.append(f"The push to {ref} ({span}) could not be checked for changes to the watch or CI, because "
                   "the list of changed files could not be fetched.")
    elif changed is not None and len([x for x in changed if str(x).strip()]) >= FILE_LIST_CAP:
        out.append(f"The push to {ref} ({span}) changes {FILE_LIST_CAP} or more files, so GitHub's list is cut "
                   "and it cannot be fully checked for changes to the watch or CI.")
    touched = _touched_paths(p, changed)
    if touched:
        shown = ", ".join(_c(x, 80) for x in touched[:SHOW_PATHS])
        more = f" and {len(touched) - SHOW_PATHS} more" if len(touched) > SHOW_PATHS else ""
        out.append(f"The push to {ref} ({span}) changes the watch or CI itself: {shown}{more}. "
                   "Expected only if you made that change.")
    return out


def findings(event_name: str, payload: dict, allow: dict, changed=None) -> list:
    """Plain-English findings for one event; [] when nothing needs the owner's eyes. Every line is a single line.
    `changed` (push only): the files the push changed, one path per entry, or [CHANGED_UNAVAILABLE]."""
    ev = _low(event_name)
    p = payload if isinstance(payload, dict) else {}
    if ev == "push":
        return _push_findings(p, allow, changed)
    if ev == "delete":
        who = (p.get("sender") or {}).get("login")
        return [f"A {_c(p.get('ref_type'), empty='ref')} named {_c(p.get('ref'), empty='(unknown)')} was deleted"
                f"{', by ' + _c(who) if who else ''}."]
    if ev == "member":     # for a future trigger: GitHub has no `member` workflow event today
        if _low(p.get("action")) not in ("added", "edited"):
            return []
        m = p.get("member") or {}
        perm = m.get("permission") or ((p.get("changes") or {}).get("permission") or {}).get("to")
        verb = "added as a collaborator" if _low(p.get("action")) == "added" else "had their collaborator access changed"
        return [f"{_c(m.get('login'), empty='A user')} was {verb}"
                f"{' with permission ' + _c(perm) if perm else ''}."]
    if ev == "public":
        return ["The repository was made PUBLIC."]
    return []


def load_allowlist(path) -> dict:
    """The allowlist file, validated. Raises ValueError (message safe to print) when it cannot be trusted."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read allowlist {path}: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("allowlist must be a JSON object")
    out = {}
    for key in ("pushers", "emails"):
        v = data.get(key)
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x.strip() for x in v):
            raise ValueError(f"allowlist '{key}' must be a non-empty list of strings")
        out[key] = [x.strip() for x in v]
    return out


def _load_payload(path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read event payload {path}: {e}") from None
    if not isinstance(data, dict):
        raise ValueError("event payload must be a JSON object")
    return data


def _load_changed(path) -> list:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ValueError(f"cannot read changed-files list {path}: {e}") from None
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def write_github_output(path, title: str, body: str, token=secrets.token_hex) -> None:
    """Append `title=` and a heredoc `body` to a $GITHUB_OUTPUT file. The delimiter is random and is redrawn until
    it is not any line of the body, so no payload text can end the heredoc early or add output keys."""
    title = _clean(title, MAX_TITLE)
    if not isinstance(body, str):
        body = str(body)
    lines = set(body.replace("\r", "").split("\n"))
    delim = "WATCH_" + token(16)
    while delim in lines:
        delim = "WATCH_" + token(16)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(f"title={title}\n")
        f.write(f"body<<{delim}\n{body.replace(chr(13), '')}\n{delim}\n")


def build_issue(event_name: str, payload: dict, found: list, env: dict):
    ref = _clean(payload.get("ref")) if isinstance(payload, dict) else ""
    where = f" on {ref}" if ref else ""
    n = len(found)
    title = _clean(f"Security watch: {n} finding{'s' if n != 1 else ''} ({event_name}{where})", MAX_TITLE)
    repo = env.get("GITHUB_REPOSITORY", "")
    run = ""
    if repo and env.get("GITHUB_RUN_ID"):
        run = f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/{repo}/actions/runs/{env['GITHUB_RUN_ID']}"
    parts = [f"The security watch saw a `{_clean(event_name, 40)}` event that needs a look:", ""]
    parts += [f"- {x}" for x in found]
    parts += ["", "What to do: if this was you, close the issue. If it was not, change your GitHub password and "
              "revoke the tokens and SSH keys in Settings, then check Settings > Collaborators and Deploy keys."]
    if run:
        parts += ["", f"Run: {run}"]
    body = "\n".join(parts)
    if len(body) > MAX_BODY:
        body = body[: MAX_BODY - 40].rstrip() + "\n\n(truncated)"
    return title, body


def main(argv=None, env=None) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="R-T8 security watch: findings for one GitHub event.")
    ap.add_argument("--event", help="event name (default: $GITHUB_EVENT_NAME)")
    ap.add_argument("--payload", help="event payload JSON file (default: $GITHUB_EVENT_PATH)")
    ap.add_argument("--allowlist", help="allowlist JSON (default: .github/security-allowlist.json in this repo)")
    ap.add_argument("--changed-files", help="files the push changed, one per line ('!unavailable' = list not fetched)")
    ap.add_argument("--dry-run", action="store_true", help="print the findings; do not write $GITHUB_OUTPUT")
    args = ap.parse_args(argv)
    event = args.event or env.get("GITHUB_EVENT_NAME") or ""
    payload_path = args.payload or env.get("GITHUB_EVENT_PATH") or ""
    allow_path = args.allowlist or str(Path(__file__).resolve().parents[2] / ".github" / "security-allowlist.json")
    try:
        if not event:
            raise ValueError("no event name (GITHUB_EVENT_NAME or --event)")
        if not payload_path:
            raise ValueError("no event payload (GITHUB_EVENT_PATH or --payload)")
        payload = _load_payload(payload_path)
        allow = load_allowlist(allow_path)
        changed = _load_changed(args.changed_files) if args.changed_files else None
    except ValueError as e:
        print(f"security_watch: {e}", file=sys.stderr)
        return 2
    found = findings(event, payload, allow, changed)
    if not found:
        if args.dry_run:
            print(f"security_watch: no findings for the {event} event.")
        return 0
    title, body = build_issue(event, payload, found, env)
    if args.dry_run:
        print(title)
        print(body)
        return 0
    out = env.get("GITHUB_OUTPUT")
    if out:
        write_github_output(out, title, body)
    else:
        print(title)
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
