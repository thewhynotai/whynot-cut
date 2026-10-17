# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""What gitleaks does not look at by itself (Phase 4 Task 40 / L-T2). Stdlib only.

gitleaks `git` scans the diffs of every commit, but NOT commit or tag messages, and gitleaks skips binary files. All of
these are real places a key ends up (a pasted `export KEY=...` in a message, a key inside a .db or .pyc, a PowerShell
`>` file that is UTF-16). This module builds plain text from those places so `gitleaks stdin` can read it:
  * commit messages of every ref (`git log --all`) and annotated tag messages, with the commit / tag of each line;
  * printable runs (8+ characters, ASCII and UTF-16 either byte order) of binary files in the working tree and of every
    binary blob in history.
It fails closed: a git command that fails or returns a truncated answer raises SweepError (the caller reports FAILED),
never an empty "nothing to scan". Nothing here prints or stores a value: callers get (label, line, rule) back.
Not covered, and stated in the report note: compressed content in history blobs, files and blobs over 64 MB (counted),
unreachable objects, `git notes`, submodule history.
"""
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fsutil import walk_files, which_safe  # noqa: E402

ASCII_RUN = re.compile(rb"[\x20-\x7e]{8,}")
UTF16LE_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){8,}")
UTF16BE_RUN = re.compile(rb"(?:\x00[\x20-\x7e]){8,}")
MAX_BLOB = 64 * 1024 * 1024
BATCH_BYTES = 256 * 1024 * 1024
BATCH_COUNT = 2000
SKIP_SWEEP_DIRS = {".git"}  # everything else is read, ignored folders included: a `.env` in an ignored folder is a secret too


class SweepError(Exception):
    pass


def git_exe():
    g = which_safe("git")
    if not g:
        raise SweepError("git was not found on PATH (an absolute PATH entry): history cannot be read")
    return g


def head_info(root, run):
    """'HEAD <sha>, <n> commits (all refs)' of the scanned repository, or '' when git cannot say (never fatal: the
    scan itself already ran). The report uses it to show WHICH commit a history scan covered."""
    try:
        git = git_exe()
        rc, sha, _ = run([git, "rev-parse", "HEAD"], cwd=str(root))
        rc2, n, _ = run([git, "rev-list", "--all", "--count"], cwd=str(root))
    except (SweepError, OSError):
        return ""
    if rc != 0 or rc2 != 0 or not sha.strip() or not n.strip().isdigit():
        return ""
    return "HEAD %s, %s commits (all refs)" % (sha.strip(), n.strip())


def require_repo(root, run):
    """The git dir of root, or SweepError. Uses git itself (a worktree or submodule has a `.git` FILE, not a folder)."""
    rc, out, err = run([git_exe(), "rev-parse", "--git-dir"], cwd=str(root))
    if rc != 0:
        raise SweepError("%s is not a git repository that git can read (%s)" % (root, (err or out).strip()[:120]))
    return out.strip()


def printable_runs(data):
    parts = [m.group(0).decode("ascii") for m in ASCII_RUN.finditer(data)]
    parts += [m.group(0).decode("utf-16-le") for m in UTF16LE_RUN.finditer(data)]
    parts += [m.group(0).decode("utf-16-be") for m in UTF16BE_RUN.finditer(data)]
    return "\n".join(parts)


def is_binary(data):
    return b"\0" in data[:8192]


def tree_binary_text(root, allow_sha256=frozenset()):
    """-> (parts [(relative label, text)], skipped_big, allowed): every binary file of the working tree (<= 64 MB each).
    A file whose sha256 is in `allow_sha256` (docs/security/baseline-binaries.json: path + exact bytes reviewed) is skipped."""
    parts, big, allowed = [], 0, 0
    for p in walk_files(root, skip_dirs=SKIP_SWEEP_DIRS):
        try:
            if os.path.getsize(p) > MAX_BLOB:
                big += 1
                continue
            with open(p, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if not is_binary(data):
            continue
        if hashlib.sha256(data).hexdigest() in allow_sha256:
            allowed += 1
            continue
        txt = printable_runs(data)
        if txt:
            parts.append((os.path.relpath(p, root).replace("\\", "/"), txt))
    return parts, big, allowed


def commit_message_text(root, run):
    """One text of every commit message of every ref plus every annotated tag message. Returns (text, owners): line n of
    the text belongs to owners[n-1] (a short commit id, or `tag:<name>`). SweepError if git fails."""
    git = git_exe()
    require_repo(root, run)
    rc, out, err = run([git, "log", "--all", "--format=%x00%H%n%B"], cwd=str(root))
    if rc != 0:
        raise SweepError("git log --all failed: %s" % (err or out).strip()[:160])
    lines, owners, cur = [], [], ""
    for ln in out.split("\n"):
        if ln.startswith("\x00"):  # git forbids NUL in a message, so a header can never be forged by one
            cur = ln[1:].strip()[:12]
            continue
        lines.append(ln)
        owners.append(cur)
    rc, out, err = run([git, "for-each-ref", "--format=%(objecttype) %(objectname) %(refname:short)", "refs/tags"], cwd=str(root))
    if rc != 0:
        raise SweepError("git for-each-ref failed: %s" % (err or out).strip()[:160])
    for ln in out.splitlines():  # annotated tags only; each tag object is read whole (and the tag objects it points to)
        parts = ln.split(" ", 2)
        if len(parts) != 3 or parts[0] != "tag":
            continue
        sha, name = parts[1], parts[2]
        for _hop in range(8):  # a tag of a tag of a tag ...
            rc, body, err = run([git, "cat-file", "tag", sha], cwd=str(root))
            if rc != 0:
                raise SweepError("git cat-file tag %s failed: %s" % (name[:40], (err or body).strip()[:120]))
            head, _, message = body.partition("\n\n")
            for mln in message.split("\n"):
                lines.append(mln)
                owners.append("tag:" + name[:40])
            fields = dict(h.split(" ", 1) for h in head.split("\n") if " " in h)
            if fields.get("type") != "tag" or not fields.get("object"):
                break
            sha = fields["object"]
    return "\n".join(lines), owners


def history_binary_text(root, run, run_bytes, allow_blobs=frozenset()):
    """-> (parts [(blob sha, text)], skipped_big, allowed, unreadable): printable runs of every binary blob of every commit.
    SweepError if git fails or answers with a malformed or short stream."""
    git = git_exe()
    require_repo(root, run)
    rc, out, err = run([git, "cat-file", "--batch-all-objects", "--batch-check=%(objecttype) %(objectname) %(objectsize)"], cwd=str(root))
    if rc != 0:
        raise SweepError("git cat-file --batch-check failed: %s" % (err or out).strip()[:160])
    shas, big, allowed = [], 0, 0
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) == 3 and parts[0] == "blob":
            if not parts[2].isdigit():
                raise SweepError("git cat-file --batch-check answered a malformed line")
            if int(parts[2]) > MAX_BLOB:
                big += 1
            elif parts[1] in allow_blobs:
                allowed += 1
            else:
                shas.append((parts[1], int(parts[2])))
    res, unreadable = [], 0
    batch, size = [], 0
    for sha, n in shas + [(None, 0)]:
        if sha is not None:
            batch.append(sha)
            size += n
        if batch and (sha is None or size >= BATCH_BYTES or len(batch) >= BATCH_COUNT):
            rc, data = run_bytes([git, "cat-file", "--batch"], str(root), ("\n".join(batch) + "\n").encode())
            if rc != 0:
                raise SweepError("git cat-file --batch failed (exit %s) on a batch of %d blobs" % (rc, len(batch)))
            pos = 0
            for want in batch:
                nl = data.find(b"\n", pos)
                if nl < 0:
                    raise SweepError("git cat-file --batch ended early (%d of %d blobs read)" % (batch.index(want), len(batch)))
                head = data[pos:nl].split()
                if len(head) == 2 and head[1] == b"missing":
                    unreadable += 1
                    pos = nl + 1
                    continue
                if len(head) != 3 or head[0].decode("ascii", "replace") != want:
                    raise SweepError("git cat-file --batch answered out of order or malformed at blob %s" % want[:12])
                if not head[2].isdigit():
                    raise SweepError("git cat-file --batch answered a malformed size at blob %s" % want[:12])
                n_ = int(head[2])
                blob = data[nl + 1:nl + 1 + n_]
                if len(blob) != n_:
                    raise SweepError("git cat-file --batch truncated blob %s" % want[:12])
                pos = nl + 1 + n_ + 1
                if is_binary(blob):
                    txt = printable_runs(blob)
                    if txt:
                        res.append((want, txt))
            batch, size = [], 0
    return res, big, allowed, unreadable


def where_is_blob(root, sha, run):
    """'<commit> <path>' of the first commit that holds this blob (never its content); 'unknown' when git cannot say."""
    try:
        git = git_exe()
    except SweepError:
        return "unknown"
    rc, out, err = run([git, "log", "--all", "--reverse", "--diff-filter=A", "--format=%h", "--name-only", "--find-object=" + sha], cwd=str(root))
    lines = [l for l in out.splitlines() if l.strip()]
    return (lines[0] + " " + (lines[1] if len(lines) > 1 else "?")) if rc == 0 and lines else "unknown"
