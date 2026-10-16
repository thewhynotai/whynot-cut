#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""Identity scan (Addendum H R5.4 / R-T6, Phase 4 Task 19; spec: docs/superpowers/specs/addendum-h/source-r-specs/
R-9-qa-identity-rtl-matrix-distinctiveness.md, R-9.1).

None of Source-R's identity strings may appear in our repo or our release files, and the repo must not contain them
either, not even inside this check. So the repo holds only `tools/identity_hashes.json`: HMAC-SHA256 hashes of
normalised tokens under a SECRET key. The plain list and the key stay outside the repo (the key: a file named by
--key-file or WNC_IDENTITY_KEY_FILE; in CI the hex secret WNC_IDENTITY_KEY). Without a key the scan is skipped
(exit 0) unless --require-key (the release gate and the owner's CI pushes). A wrong key is caught by `key_id`.

Normalisation is the engine's one shared normaliser (`whynot-cut/engine/reel/lib/cut_proposals_norm.py`, loaded from
its file). Besides each line's plain words, a match also tries: CamelCase / letter-digit splits (`VexilorScene`), an
Arabic proclitic stripped (`والـ…`), the line with \\uXXXX, HTML entities and %XX decoded, and a phrase that wraps onto
the next line (unless the line ends in hard punctuation or the next line is blank). File and folder names are scanned
too; any name part that matches is shown as <name:hash> in every report, so a report never carries a token.

    identity_scan.py scan    [--root DIR] [--hashes FILE] [--key-file FILE] [--require-key] [--json]
    identity_scan.py secrets [--root DIR] [--allowlist FILE] [--key-file FILE] [--require-readable] [--json]
    identity_scan.py make-key --out FILE                                  (outside the repo; never overwrites)
    identity_scan.py make-hashes --plain FILE --key-file FILE [--out FILE] (plain list and key outside the repo)

--root must be an existing folder (extract a zip first). Exit: 0 clean (or skipped), 1 findings, 2 usage / key / IO
error, a root with nothing to scan, or (with --require-key / --require-readable) a file that could not be read.
Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import importlib.util
import json
import os
import re
import secrets as _secrets
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]
DEFAULT_HASHES = REPO / "tools" / "identity_hashes.json"
DEFAULT_ALLOWLIST = REPO / "tools" / "secret_allowlist.json"
NORM_FILE = REPO / "whynot-cut" / "engine" / "reel" / "lib" / "cut_proposals_norm.py"
KEY_ENV = "WNC_IDENTITY_KEY_FILE"
KEY_HEX_ENV = "WNC_IDENTITY_KEY"
MAX_BYTES = 20_000_000          # bigger files: only their names are scanned
FORMAT = 2                      # 2: the glued-split spelling of every token is hashed too


def _load_norm():
    spec = importlib.util.spec_from_file_location("wnc_cut_proposals_norm", NORM_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_norm = _load_norm()
normalize = _norm.normalize
segments = _norm.segments


class ScanError(Exception):
    """A refusal or a usage problem (exit 2). Its text never contains a plain token."""


# ------------------------------------------------------------------------------------------------------- key, hashes
def _inside(path: Path, root: Path) -> bool:
    """Is `path` (existing or not) inside `root`? Real paths (links, junctions), case-insensitive disks (samefile)."""
    p, r = os.path.realpath(path), os.path.realpath(root)
    try:
        if os.path.commonpath([os.path.normcase(p), os.path.normcase(r)]) == os.path.normcase(r):
            return True
    except ValueError:          # another drive
        pass
    cur = Path(p)
    for anc in (cur, *cur.parents):
        try:
            if anc.exists() and os.path.samefile(anc, r):
                return True
        except OSError:
            continue
    return False


def _outside_repo(path: Path, repo_root: Path, what: str) -> None:
    if _inside(path, repo_root):
        raise ScanError(f"refused: the {what} must live outside the repo ({repo_root})")


def make_key(out: Path, repo_root: Path = REPO) -> str:
    """A new random 32-byte key as hex in `out` (outside the repo, never overwritten). Returns its key_id."""
    out = Path(out)
    _outside_repo(out, repo_root, "key file")
    if os.path.lexists(out):
        raise ScanError(f"refused: {out} already exists (a key is never overwritten)")
    key = _secrets.token_bytes(32)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(key.hex() + "\n")
    return key_id(key)


def _key_bytes(raw: str, where: str) -> bytes:
    try:
        key = bytes.fromhex(raw.strip())
    except ValueError:
        raise ScanError(f"{where} is not a hex key") from None
    if len(key) < 16:
        raise ScanError(f"{where} is too short to be a key")
    return key


def read_key(path: Path) -> bytes:
    try:
        raw = Path(path).read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as e:
        raise ScanError(f"cannot read the key file {path}: {type(e).__name__}") from None
    return _key_bytes(raw, f"the key file {path}")


def key_from_env() -> bytes | None:
    """The key from WNC_IDENTITY_KEY_FILE, else the hex in WNC_IDENTITY_KEY (CI secret), else None."""
    f = os.environ.get(KEY_ENV)
    if f:
        return read_key(Path(f))
    raw = os.environ.get(KEY_HEX_ENV, "")
    return _key_bytes(raw, KEY_HEX_ENV) if raw.strip() else None


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:8]


def _h(key: bytes, words) -> str:
    return hmac.new(key, " ".join(words).encode("utf-8"), hashlib.sha256).hexdigest()


def make_hashes(plain: Path, key_file: Path, out: Path = DEFAULT_HASHES, repo_root: Path = REPO) -> dict:
    """Read the plain list (one token per line, '#' comments) and the key, both outside the repo, and write only keyed
    hashes to `out`. Returns {"tokens": n, "max_words": m, "key_id": k}; never echoes a token."""
    plain, key_file, out = Path(plain), Path(key_file), Path(out)
    _outside_repo(plain, repo_root, "plain list")
    _outside_repo(key_file, repo_root, "key file")
    key = read_key(key_file)
    try:
        lines = plain.read_text(encoding="utf-8").split("\n")
    except (OSError, UnicodeDecodeError) as e:
        raise ScanError(f"cannot read the plain list: {type(e).__name__}") from None
    tokens, first, first2, longest = set(), set(), set(), 1
    for n, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        segs = segments(line)
        if len(segs) != 1:
            raise ScanError(f"plain list line {n}: hard punctuation inside a token (split it into separate lines)")
        words = segs[0]
        forms = [words] + ([["".join(words)]] if len(words) > 1 else [])
        glued = [w for raw in _norm.WORD.findall(_norm.prepare(line)) for part in _norm.glued_parts(raw)
                 for w in _norm.WORD.findall(part)]
        if glued and glued not in forms:            # `NameScene` and `myName` then match a CamelCase token
            forms.append(glued)
        for w in forms:
            tokens.add(_h(key, w))
            first.add(_h(key, w[:1]))
            if len(w) > 1:
                first2.add(_h(key, w[:2]))          # second-level prefilter: a phrase grows only past a listed pair
            longest = max(longest, len(w))
    if not tokens:
        raise ScanError("the plain list has no tokens")
    doc = {"format": FORMAT, "mode": "keyed", "algo": "hmac-sha256", "key_id": key_id(key),
           "norm_version": _norm.NORM_VERSION, "max_words": longest, "tokens": sorted(tokens), "first": sorted(first),
           "first2": sorted(first2)}
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".partial")
        tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, out)
    except OSError as e:
        raise ScanError(f"cannot write the hash file {out}: {type(e).__name__}") from None
    return {"tokens": len(tokens), "max_words": longest, "key_id": doc["key_id"]}


def load_db(path: Path = DEFAULT_HASHES) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if doc.get("mode") != "keyed" or doc.get("format") != FORMAT:
            raise ValueError("format")
        return {"key_id": str(doc["key_id"]), "norm_version": int(doc["norm_version"]),
                "max_words": int(doc["max_words"]), "tokens": set(doc["tokens"]), "first": set(doc["first"]),
                "first2": set(doc["first2"])}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise ScanError(f"{path}: not a readable format-{FORMAT} keyed hash file ({type(e).__name__})") from None


# ---------------------------------------------------------------------------------------------------------- files
def _is_link(p: str) -> bool:
    if os.path.islink(p) or (hasattr(os.path, "isjunction") and os.path.isjunction(p)):
        return True
    try:                                        # older Pythons: any reparse point counts as a link
        return bool(getattr(os.lstat(p), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def walk(root: Path, errors: list | None = None) -> list[str]:
    """Relative POSIX paths of every file and folder under `root`; links and junctions are listed, never entered.
    A folder that cannot be listed goes to `errors` (never silently skipped)."""
    out, stack = [], [""]
    while stack:
        rel = stack.pop()
        base = os.path.join(root, rel) if rel else str(root)
        try:
            entries = sorted(os.scandir(base), key=lambda e: e.name)
        except OSError:
            if errors is not None:
                errors.append(rel or ".")
            continue
        for e in entries:
            if e.name == ".git":
                continue
            r = f"{rel}/{e.name}" if rel else e.name
            out.append(r)
            if _is_link(e.path):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    stack.append(r)
            except OSError:
                pass
    return out


def repo_files(root: Path, errors: list | None = None) -> list[str]:
    """Git-tracked + untracked-not-ignored files (and their folders) when `root` is a git work tree's top, else a
    link-safe walk. Raises ScanError when `root` is not a folder."""
    root = Path(root)
    if not root.is_dir():
        raise ScanError(f"--root {root} is not a folder (extract an archive before scanning it)")
    if (root / ".git").exists():
        try:
            p = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "-co", "--exclude-standard"],
                               capture_output=True, timeout=60)
            if p.returncode == 0:
                files = [f for f in p.stdout.decode("utf-8", "replace").split("\0") if f]
                more = set()
                for f in files:                   # folder names are scanned too
                    parts = f.split("/")[:-1]
                    for i in range(1, len(parts) + 1):
                        more.add("/".join(parts[:i]))
                return sorted(set(files) | more)
            print("identity scan: git ls-files failed; walking the folder instead", file=sys.stderr)
        except (OSError, subprocess.SubprocessError):
            print("identity scan: git not usable; walking the folder instead", file=sys.stderr)
    return walk(root, errors)


def _long(path: str) -> str:
    if os.name == "nt" and len(path) >= 240 and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(path)
    return path


def _read_bytes(path: str) -> bytes | None:
    """File bytes; None for a folder, a link or an oversized file. Raises OSError when a file cannot be read."""
    st = os.lstat(_long(path))
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
        return None
    with open(_long(path), "rb") as f:
        return f.read()


def _decode(data: bytes | None) -> str | None:
    if data is None:
        return None
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", "replace")


def _lines(text: str) -> list[str]:
    return [ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n")]


# ------------------------------------------------------------------------------------------------------------ scan
@dataclass(frozen=True)
class Hit:
    path: str          # as shown: name parts that match are replaced by <name:hash>
    line: int
    hash: str


_ESC = re.compile(r"\\u[0-9a-fA-F]{4}|&#?\w+;|%[0-9a-fA-F]{2}")
_U = re.compile(r"\\u([0-9a-fA-F]{4})")


def _unescaped(text: str) -> str | None:
    if not _ESC.search(text):
        return None
    t = _U.sub(lambda m: chr(int(m.group(1), 16)), text)
    t = unquote(html.unescape(t))
    return t if t != text else None


class _Matcher:
    def __init__(self, db: dict, key: bytes):
        self.db, self.key = db, key
        self.first, self.tokens, self.n_max = db["first"], db["tokens"], db["max_words"]
        self.first2 = db["first2"]
        self.cache: dict[str, str] = {}
        self.ngrams: dict[tuple, str] = {}
        self.forms: dict[str, list[list[str]]] = {}
        self.hot: dict[str, bool] = {}
        self.texts: dict[str, str | None] = {}

    def wh(self, w: str) -> str:
        h = self.cache.get(w)
        if h is None:
            h = self.cache[w] = _h(self.key, [w])
        return h

    def hn(self, words: tuple) -> str:
        h = self.ngrams.get(words)
        if h is None:
            h = self.ngrams[words] = _h(self.key, words)
        return h

    def word_forms(self, raw: str) -> list[list[str]]:
        """The spellings one raw word may stand for, each a word list: itself (case-folded and re-split, so a fold that
        adds a mark splits the same way as in the generator), its glued parts, and each form without an Arabic
        proclitic."""
        f = self.forms.get(raw)
        if f is None and raw.isascii():                # fast path (most words): no fold marks, no Arabic proclitic
            low = raw.lower()
            f = [[low]]
            if not raw.islower() or not raw.isalpha():   # only then can it hold a CamelCase or letter/digit join
                glued = _norm.glued_parts(raw)
                if glued != [low]:
                    f.append(glued)
            self.forms[raw] = f
            return f
        if f is None:
            base = _norm.WORD.findall(raw.casefold())
            f = [base] if base else []
            glued = [w for part in _norm.glued_parts(raw) for w in _norm.WORD.findall(part)]
            if glued and glued != base:
                f.append(glued)
            if len(base) == 1:      # 3-letter remainders allowed here; match() never accepts one as a whole token
                f += [[bare] for bare in _norm.prefix_forms(base[0], min_rest=3)]
            self.forms[raw] = f
        return f

    def is_first(self, raw: str) -> bool:
        """Can a listed token start at (or inside) this raw word, in any of its spellings?"""
        f = self.hot.get(raw)
        if f is None:
            f = self.hot[raw] = any(self.wh(w) in self.first for form in self.word_forms(raw) for w in form)
        return f

    def any_first(self, raw_words) -> bool:
        return any(self.is_first(w) for w in raw_words)

    def match(self, raw_words, min_index: int = 0) -> str | None:
        """A listed token among these raw words (one segment), ending at a raw word index >= min_index. Each raw word
        may take any of its spellings independently; a token may start inside a glued word (`myName`)."""
        n_raw, tokens, first2 = len(raw_words), self.tokens, self.first2

        def grow(seq, j, short):
            # seq: [(word, raw index)]; `short`: seq[0] is a 3-letter remainder (never a whole token by itself)
            words = tuple(w for w, _ in seq)
            top = min(len(seq), self.n_max)
            for length in range(1, top + 1):
                h = self.wh(words[0]) if length == 1 else self.hn(words[:length])
                if length == 2 and h not in first2 and h not in tokens:
                    return None                       # no listed token starts with this pair
                if h in tokens and seq[length - 1][1] >= min_index and not (length == 1 and short):
                    return h
            if len(seq) >= self.n_max or j >= n_raw:
                return None
            if len(seq) >= 2 and self.hn(words[:2]) not in first2:
                return None
            for form in self.word_forms(raw_words[j]):
                r = grow(seq + [(w, j) for w in form], j + 1, short)
                if r:
                    return r
            return None

        for i in range(n_raw):
            if not self.is_first(raw_words[i]):
                continue
            base = self.word_forms(raw_words[i])[0] if self.word_forms(raw_words[i]) else []
            for form in self.word_forms(raw_words[i]):
                short = len(form) == 1 and form != base and len(form[0]) < 4
                for k in range(len(form)):
                    if self.wh(form[k]) not in self.first:
                        continue
                    r = grow([(w, i) for w in form[k:]], i + 1, short and k == 0)
                    if r:
                        return r
        return None

    def pieces(self, line: str, prepared: bool = False) -> list[list[str]]:
        """Raw (case-kept) words of each hard-punctuation piece of a line; empty pieces kept (they mark breaks)."""
        return [_norm.WORD.findall(p) for p in _norm.HARD.split(line if prepared else _norm.prepare(line))]

    def text_hit(self, text: str) -> str | None:
        if text in self.texts:
            return self.texts[text]
        h = None
        for words in self.pieces(text):
            if words and self.any_first(words):
                h = self.match(words)
                if h:
                    break
        self.texts[text] = h
        return h

    def name_hit(self, name: str) -> str | None:
        """A file or folder name (or path), also with %XX decoded."""
        return self.text_hit(name) or (self.text_hit(unquote(name)) if "%" in name else None)


_QUOTE = re.compile(r"^\s*(?:(?:>|&gt;)\s*)+")      # a quote marker at the start of a line does not break a phrase


def _display(rel: str, m: _Matcher, memo: dict) -> str:
    """`rel` with every matching name part replaced by <name:hash>; a token spread over parts → <path:hash>."""
    if rel in memo:
        return memo[rel]
    shown = []
    for p in rel.split("/"):
        h = m.name_hit(p)
        shown.append(f"<name:{h[:12]}>" if h else p)
    joined = "/".join(shown)
    h = m.name_hit(joined)
    memo[rel] = f"<path:{h[:12]}>" if h else joined
    return memo[rel]


def _check_db(db: dict, key: bytes) -> None:
    if key_id(key) != db["key_id"]:
        raise ScanError("the key does not match the hash file (key_id differs)")
    if db["norm_version"] != _norm.NORM_VERSION:
        raise ScanError(f"the hash file was made with normaliser v{db['norm_version']}, this is "
                        f"v{_norm.NORM_VERSION}: regenerate the hash file (make-hashes)")


def _chunk_worker(args):
    root, db, key, files = args
    return _scan_files(Path(root), db, key, files)


def _jobs_default() -> int:
    return max(1, min(4, (os.cpu_count() or 1) // 4))


def scan(root: Path, db: dict, key: bytes, files: list[str] | None = None, report: dict | None = None,
         jobs: int | None = None, min_files_per_job: int = 400) -> list[Hit]:
    """Every (path, line) where a listed token appears in a file's text or in a file or folder name. `report`, when
    given, receives "files" (paths listed) and "unreadable" (shown paths of files and folders that could not be read;
    files git lists but that no longer exist are skipped, not unreadable). Big trees are split over `jobs` worker
    processes (default: a quarter of the CPU threads, at most 4); the result is the same, in the same order, and any
    problem starting the workers falls back to one process. Workers start by spawning (Windows, macOS), which re-imports
    the caller's main module: an in-process caller needs an `if __name__ == "__main__":` guard, or should use the CLI."""
    _check_db(db, key)
    root = Path(root)
    unlisted: list[str] = []
    files = files if files is not None else repo_files(root, errors=unlisted)
    if not files:
        raise ScanError(f"nothing to scan under {root}")
    m = _Matcher(db, key)
    memo: dict[str, str] = {}
    unreadable = [_display(r, m, memo) for r in unlisted]
    jobs = _jobs_default() if jobs is None else max(1, jobs)
    jobs = min(jobs, len(files) // max(1, min_files_per_job)) or 1
    results = None
    if jobs > 1:
        size = -(-len(files) // jobs)
        chunks = [files[i:i + size] for i in range(0, len(files), size)]
        try:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=len(chunks)) as ex:
                results = list(ex.map(_chunk_worker, [(str(root), db, key, c) for c in chunks]))
        except Exception:  # noqa: BLE001  G10: workers unavailable here → the same scan in one process
            results = None
    if results is None:
        results = [_scan_files(root, db, key, files, m, memo)]
    hits = [h for r in results for h in r[0]]
    unreadable += [u for r in results for u in r[1]]
    if report is not None:
        report["files"] = len(files)
        report["unreadable"] = unreadable
    return hits


def _scan_files(root: Path, db: dict, key: bytes, files: list[str], m: "_Matcher | None" = None,
                memo: dict | None = None) -> tuple[list[Hit], list[str]]:
    m = m or _Matcher(db, key)
    memo = {} if memo is None else memo
    hits, unreadable = [], []
    for rel in files:
        parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
        h = m.name_hit(rel)
        if h and not (parent and m.name_hit(parent)):        # each name reported once, where it first matches
            hits.append(Hit(_display(rel, m, memo), 0, h[:12]))
        try:
            text = _decode(_read_bytes(os.path.join(root, rel)))
        except FileNotFoundError:
            continue                        # listed by git but deleted in the working folder
        except OSError:
            unreadable.append(_display(rel, m, memo))
            continue
        if not text:
            continue
        alt = _unescaped(text)
        prep = _norm.prepare(text)          # once per file; it keeps every line break, so line numbers stay true
        raw_all = set(_norm.WORD.findall(prep)) | (set(_norm.WORD.findall(_norm.prepare(alt))) if alt else set())
        hot = {w for w in raw_all if m.is_first(w)}
        if not hot:
            continue                        # no listed first word in any spelling anywhere in the file
        hot_rx = re.compile("|".join(map(re.escape, sorted(hot, key=len, reverse=True))))   # a superset line test
        carry: list[str] = []
        raw_lines = _lines(text)
        for n, pline in enumerate(_lines(prep), 1):
            if not pline.strip():
                carry = []
                continue
            line = raw_lines[n - 1] if n <= len(raw_lines) else pline
            if not carry and not hot_rx.search(pline) and not (alt and _ESC.search(line)):
                continue                    # no word a token could start with, nothing wrapped from above
            pcs = m.pieces(_QUOTE.sub("", pline), prepared=True)
            found = None
            for j, words in enumerate(pcs):
                if not words:
                    continue
                if j == 0 and carry:                  # a phrase wrapped from the previous line
                    found = m.match(carry + words, min_index=len(carry))
                if not found and not hot.isdisjoint(words):
                    found = m.match(words)
                if found:
                    break
            if not found and alt and (u := _unescaped(line)):
                found = m.text_hit(u)
            if found:
                hits.append(Hit(_display(rel, m, memo), n, found[:12]))
            tail = pcs[-1][-(m.n_max - 1):] if pcs and pcs[-1] and m.n_max > 1 else []
            # only words a token can start with are worth carrying (a wrapped token starts on this line)
            carry = tail[next((i for i, w in enumerate(tail) if w in hot or m.is_first(w)), len(tail)):]
    return hits, unreadable


# --------------------------------------------------------------------------------------------------------- secrets
SECRET_PATTERNS = {
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})"),
    "aws_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"),
    "ai_api_key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{32,}"),
    "stripe_key": re.compile(r"\b[sr]k_live_[0-9A-Za-z]{24,}"),
    "slack_token": re.compile(r"\b(?:xox[abprs]|xapp)-[0-9A-Za-z-]{10,}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?-----"),
    "hf_token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "npm_token": re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    "gitlab_token": re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"),
}
# A Windows home (any case: c:\users\…), a macOS home (/Users/, capitalised; lowercase /users/ is a URL path) or a
# Linux home (/home/), also inside file:// URLs. The name starts with a letter or digit, so a placeholder, a regex
# character or prose punctuation after the folder is not a name.
_HOME = re.compile(r"(?:\b[A-Za-z]:[\\/]{1,2}(?i:users)[\\/]{1,2}|(?:(?<=file://)|(?<![\w.:/]))/(?:Users|home)/)"
                   r"(?!(?i:all users)[\\/])(?=[^\W_])([^\\/\s\"'`<>|*?:()\[\]{}]+)")
PLACEHOLDER_USERS = {"you", "user", "username", "name", "runner", "public", "default", "shared", "...", "…", "x", "me"}
BOM_FREE_EXT = {".ps1", ".psm1", ".psd1"}     # Windows PowerShell 5.1 needs a BOM for non-ASCII scripts


@dataclass(frozen=True)
class SecretHit:
    path: str
    line: int
    pattern: str


def _glob_rx(g: str) -> re.Pattern:
    out, i = "", 0
    while i < len(g):
        if g.startswith("**", i):
            out, i = out + ".*", i + 2
        elif g[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif g[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(g[i]), i + 1
    return re.compile(out + r"\Z")


def _load_allowlist(path: Path | None) -> list:
    if path is None:
        return []
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("not a list")
        out = []
        for e in entries:
            if not (isinstance(e, dict) and e.get("path") and e.get("pattern") and str(e.get("reason", "")).strip()):
                raise ValueError("an entry needs path, pattern and reason")
            out.append((_glob_rx(str(e["path"])), str(e["pattern"])))
        return out
    except (OSError, ValueError) as e:
        raise ScanError(f"cannot use the allowlist {path}: {e if isinstance(e, ValueError) else type(e).__name__}") \
            from None


def scan_secrets(root: Path, files: list[str] | None = None, allowlist: Path | None = None,
                 report: dict | None = None, shown=None) -> list[SecretHit]:
    """Credential patterns, personal home paths and UTF-8 BOMs. Never returns the matched value. `shown` (a function
    of a path) redacts identity names in the reported paths (the CLI passes it when the identity key is available; with
    a key set, a missing or out-of-date hash file is then an error, exit 2, never an unredacted report)."""
    allow = _load_allowlist(allowlist)
    root = Path(root)
    unlisted: list[str] = []
    files = files if files is not None else repo_files(root, errors=unlisted)
    if not files:
        raise ScanError(f"nothing to scan under {root}")
    shown = shown or (lambda r: r)
    out, unreadable = [], [shown(r) for r in unlisted]
    for rel in files:
        try:
            data = _read_bytes(os.path.join(root, rel))
        except FileNotFoundError:
            continue
        except OSError:
            unreadable.append(shown(rel))
            continue
        text = _decode(data)
        if text is None:
            continue
        found = []
        if data[:3] == b"\xef\xbb\xbf" and Path(rel).suffix.lower() not in BOM_FREE_EXT:
            found.append((1, "bom"))
        for n, line in enumerate(_lines(text), 1):
            for name, rx in SECRET_PATTERNS.items():
                if rx.search(line):
                    found.append((n, name))
            for mt in _HOME.finditer(line):
                if mt.group(1).strip().casefold() not in PLACEHOLDER_USERS:
                    found.append((n, "home_path"))
                    break
        out += [SecretHit(shown(rel), n, p) for n, p in found
                if not any(rx.match(rel) and pat in (p, "*") for rx, pat in allow)]
    if report is not None:
        report["files"] = len(files)
        report["unreadable"] = unreadable
    return out


# ------------------------------------------------------------------------------------------------------------- CLI
def _emit(as_json: bool, doc: dict, lines: list[str]) -> None:
    if as_json:
        print(json.dumps(doc, ensure_ascii=False))
    else:
        for line in lines:
            print(line)


def _cmd_scan(a) -> int:
    key = read_key(Path(a.key_file)) if a.key_file else key_from_env()
    if key is None:
        if a.require_key:
            print("identity scan: no key (set --key-file, WNC_IDENTITY_KEY_FILE or WNC_IDENTITY_KEY); the release gate "
                  "needs it", file=sys.stderr)
            return 2
        _emit(a.json, {"skipped": "no key", "hits": [], "files": 0}, ["identity scan skipped: no key"])
        return 0
    db = load_db(Path(a.hashes))
    rep: dict = {}
    hits = scan(Path(a.root), db, key, report=rep)
    bad = rep["unreadable"]
    _emit(a.json, {"hits": [{"path": h.path, "line": h.line, "hash": h.hash} for h in hits], "files": rep["files"],
                   "unreadable": bad},
          [f"{h.path}:{h.line}: identity token {h.hash}" for h in hits]
          + [f"unreadable (not scanned): {p}" for p in bad]
          + [f"identity scan: {len(hits)} finding(s) in {rep['files']} paths"
             + (f", {len(bad)} unreadable" if bad else "")])
    if hits:
        return 1
    return 2 if (bad and a.require_key) else 0


def _cmd_secrets(a) -> int:
    allow = Path(a.allowlist) if a.allowlist else (DEFAULT_ALLOWLIST if DEFAULT_ALLOWLIST.is_file() else None)
    shown = None
    key = read_key(Path(a.key_file)) if a.key_file else key_from_env()
    if key is not None:                     # redact identity names in the paths this report prints
        db = load_db(Path(a.hashes))
        _check_db(db, key)
        m, memo = _Matcher(db, key), {}
        shown = lambda r: _display(r, m, memo)  # noqa: E731
    rep: dict = {}
    found = scan_secrets(Path(a.root), None, allow, report=rep, shown=shown)
    bad = rep["unreadable"]
    _emit(a.json, {"hits": [{"path": s.path, "line": s.line, "pattern": s.pattern} for s in found],
                   "files": rep["files"], "unreadable": bad},
          [f"{s.path}:{s.line}: {s.pattern}" for s in found]
          + [f"unreadable (not scanned): {p}" for p in bad]
          + [f"secret scan: {len(found)} finding(s) in {rep['files']} paths" + (f", {len(bad)} unreadable" if bad else "")])
    if found:
        return 1
    return 2 if (bad and a.require_readable) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="identity_scan.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--root", default=str(REPO))
    s.add_argument("--hashes", default=str(DEFAULT_HASHES))
    s.add_argument("--key-file")
    s.add_argument("--require-key", action="store_true")
    s.add_argument("--json", action="store_true")
    s2 = sub.add_parser("secrets")
    s2.add_argument("--root", default=str(REPO))
    s2.add_argument("--allowlist")
    s2.add_argument("--hashes", default=str(DEFAULT_HASHES))
    s2.add_argument("--key-file", help="the identity key: name parts that match are redacted in the report")
    s2.add_argument("--require-readable", action="store_true")
    s2.add_argument("--json", action="store_true")
    k = sub.add_parser("make-key")
    k.add_argument("--out", required=True)
    m = sub.add_parser("make-hashes")
    m.add_argument("--plain", required=True)
    m.add_argument("--key-file", required=True)
    m.add_argument("--out", default=str(DEFAULT_HASHES))
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        if a.cmd == "scan":
            return _cmd_scan(a)
        if a.cmd == "secrets":
            return _cmd_secrets(a)
        if a.cmd == "make-key":
            print(f"key written (key_id {make_key(Path(a.out))})")
            return 0
        r = make_hashes(Path(a.plain), Path(a.key_file), Path(a.out))
        print(f"hash file written: {r['tokens']} hashes, max {r['max_words']} words, key_id {r['key_id']}")
        return 0
    except ScanError as e:
        print(f"identity scan: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001  an unexpected error is a tool problem (2), never "findings" (1)
        print(f"identity scan: internal error ({type(e).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
