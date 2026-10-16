#!/usr/bin/env python3
"""WhyNot Cut release tool - STUB (3.0 T7.1 task 7): only the installer's parts of components.json.
Python stdlib only (no third-party package), so it runs on any Python 3.9+.

    python tools/release.py components --check [--plugin <dir> | --components <file>]
        Print the dotted path of every placeholder ("<release>" or null) in setup/components.json, one per line;
        a count goes to stderr. Exit 0 (it reports, it does not judge).
    python tools/release.py components --fill-artefacts [--plugin <dir> | --components <file>]
        For the Adobe panel files present in <plugin>/adobe/ (default plugin: whynot-cut/ next to tools/), write the
        file (as the plugin-root-relative path `adobe/<name>`, which is how the installer's adobe step resolves it)
        and its sha256 into components.json:
            adobe/*.zxp  ->  bridge.cep.zxp + bridge.cep.sha256
            adobe/*.ccx  ->  bridge.uxp.ccx + bridge.uxp.sha256
        Every other value, placeholders included (bridge.cep.bundle, bridge.uxp.version / id, marketplace.url, ...),
        stays as it is. Only those value tokens are rewritten in the text, so the file keeps its formatting (indent 2,
        inline objects, key order, line endings, trailing newline); the result is parsed back and compared before it
        is written (atomically). No artefact found = nothing written. Two .zxp (or two .ccx) = exit 2, nothing
        written: the tool never guesses which one ships.

    python tools/release.py handoff --out <dir> [--label PREVIEW-3.0.0-p3] [--preview] [--dry-run] [--repo <dir>]
        Addendum G12 (pulled forward as a PREVIEW): build <out>/Windows/ and <out>/Mac/ from the commit at HEAD.
        Generated, never hand-edited. It is built into <out>.new and then swapped in; <out>.prev is kept until the new
        folder is in place, and any failure leaves the previous output as it was. Exit 2 = refused.
          Windows/  the plugin zip (package.py's file list, from a `git archive` of HEAD plus the shipped Adobe
                    artefacts, with their pins filled in the zip's components.json), install.ps1, install.sh,
                    README-installer.md, the .ccx, the .zxp ONLY when signed (META-INF/signatures.xml), the guide PDF,
                    README-AR.md (with the exact local -Source/-SourceSha256 command) and checksums.txt.
          Mac/      repo/ (git clone --no-local of the branch: full history; origin = this repo's origin without
                    credentials; no stale remote-tracking refs; refused if secrets/caches/renders/venvs are tracked),
                    sample-client/ (the FICTIONAL evals/_fixtures/example-clinic.sh client, synthetic ffmpeg clips),
                    START-HERE.md (it includes LOCKED-AREAS.md) and the Arabic guide for Yunus.
          root      WHAT-WORKS-NOW-AR.md (from tools/handoff/what-works.json + PROGRESS.md's passed phases) and
                    LABEL.txt.
        The templates live in tools/handoff/. Every generated text file is scanned for the real-client words of
        tests/test_plugin.py; a hit refuses the hand-off.

Scope. The full release pipeline is T7.6 (master plan) and its steps 1-10 belong to the executor; this stub covers
the installer's parts only. NOT done here: (1) tests; (2) validate --strict; (3) locks compile
(setup/locks/runtime-<platform>.lock, `uv pip compile --generate-hashes`, and `runtime.locks.<platform>.id`);
(4) build panel-ui + UXP -> .ccx; (5) CEP -> signed .zxp (Phase 6); (6) guide PDF (Phase 10); (7) package.py ->
plugin zip; (8) render components.json (every "<release>" pin: marketplace.url, release.index_url,
runtime.index_url, bridge.*, models.*.revision) + marketplace.json (URL + sha256 when H3); (9) checksums;
(10) dist/. marketplace.json is uploaded last. `components --fill-artefacts` is the part of step 8 that the
installer's adobe step needs today.

Release index - what the release tool must publish later at `release.index_url` (the installer's one-line mode reads
it: installer/install.ps1 `$index.$ch.url` / `.sha256`, installer/install.sh `<channel>.url` / `<channel>.sha256`):

    {
      "stable": {"url": "https://.../WhyNotCut-<version>.zip", "sha256": "<64 lowercase hex of that zip>"},
      "beta":   {"url": "https://.../WhyNotCut-<version>-beta.N.zip", "sha256": "<64 hex>"}
    }

Keys are the channel names (`stable`, `beta`; the front ends default to `stable`), each holding exactly `url`
(https) and `sha256` of the release zip (whose root holds whynot-cut-marketplace/whynot-cut). Until it is hosted,
`release.index_url` stays "<release>" and the one-liners stop with the H3 message (exit 2).
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

PLACEHOLDER = "<release>"
PLUGIN = Path(__file__).resolve().parents[1] / "whynot-cut"
ARTEFACTS = (("zxp", ("bridge", "cep"), "zxp"), ("ccx", ("bridge", "uxp"), "ccx"))  # suffix, object path, file key


def is_placeholder(v) -> bool:
    """Same rule as installer/core/wnc_installer/base.is_placeholder."""
    return v is None or (isinstance(v, str) and v.startswith("<release"))


def leaves(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{prefix}.{i}")
    else:
        yield prefix, obj


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------------------------- text surgery
_WS = re.compile(r"\s*")
_STR = re.compile(r'"(?:[^"\\]|\\.)*"')


def _value_end(text: str, i: int) -> int:
    """End index of the JSON value starting at text[i] (string-aware bracket matching)."""
    if text[i] == '"':
        return _STR.match(text, i).end()
    if text[i] in "{[":
        depth, j = 0, i
        while j < len(text):
            c = text[j]
            if c == '"':
                j = _STR.match(text, j).end()
                continue
            if c in "{[":
                depth += 1
            elif c in "}]":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        raise ValueError("unbalanced JSON")
    m = re.compile(r"[^\s,}\]]+").match(text, i)
    return m.end()


def _member(text: str, start: int, end: int, key: str) -> tuple:
    """(value start, value end) of `key` among the DIRECT members of the object text[start:end] (start at '{')."""
    i = start + 1
    while i < end:
        i = _WS.match(text, i).end()
        if text[i] == "}":
            break
        if text[i] == ",":
            i += 1
            continue
        k_end = _STR.match(text, i).end()
        name = json.loads(text[i:k_end])
        i = _WS.match(text, k_end).end()
        if text[i] != ":":
            raise ValueError(f"not JSON at offset {i}")
        v_start = _WS.match(text, i + 1).end()
        v_end = _value_end(text, v_start)
        if name == key:
            return v_start, v_end
        i = v_end
    raise KeyError(key)


def set_values(text: str, edits: dict) -> str:
    """Replace the value tokens at the dotted paths in `edits` (each must already exist) and nothing else."""
    spans = []
    for dotted, value in edits.items():
        start = _WS.match(text, 0).end()
        end = _value_end(text, start)
        for key in dotted.split("."):
            start, end = _member(text, start, end, key)
        spans.append((start, end, json.dumps(value, ensure_ascii=False)))
    for start, end, new in sorted(spans, reverse=True):
        text = text[:start] + new + text[end:]
    return text


# --------------------------------------------------------------------------------------------- commands
def components_path(args) -> Path:
    if args.components:
        return Path(args.components)
    return Path(args.plugin or PLUGIN) / "setup" / "components.json"


def cmd_check(args) -> int:
    path = components_path(args)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    found = [p for p, v in leaves(data) if is_placeholder(v)]
    for p in found:
        print(p)
    print(f"{len(found)} placeholder(s) in {path}", file=sys.stderr)
    return 0


def cmd_fill(args) -> int:
    path = components_path(args)
    plugin = Path(args.plugin) if args.plugin else (path.parent.parent if args.components else PLUGIN)
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw[3:].decode("utf-8") if bom else raw.decode("utf-8")
    data = json.loads(text)
    adobe = plugin / "adobe"
    edits = {}
    for suffix, obj, file_key in ARTEFACTS:
        found = sorted(p for p in adobe.glob(f"*.{suffix}") if p.is_file()) if adobe.is_dir() else []
        if len(found) > 1:
            print(f"ERROR: more than one .{suffix} in {adobe}: {', '.join(p.name for p in found)}; keep the one that "
                  "ships", file=sys.stderr)
            return 2
        if not found:
            print(f"no adobe/*.{suffix}: {'.'.join(obj)} left as it is", file=sys.stderr)
            continue
        node = data
        for k in obj:
            node = node.get(k) if isinstance(node, dict) else None
        if not isinstance(node, dict) or file_key not in node or "sha256" not in node:
            print(f"ERROR: {path} has no {'.'.join(obj)}.{file_key} / .sha256", file=sys.stderr)
            return 2
        dotted = ".".join(obj)
        edits[f"{dotted}.{file_key}"] = f"adobe/{found[0].name}"
        edits[f"{dotted}.sha256"] = sha256_file(found[0])
    if not edits:
        print("nothing to fill", file=sys.stderr)
        return 0
    new_text = set_values(text, edits)
    expected = json.loads(text)
    for dotted, value in edits.items():
        *parents, last = dotted.split(".")
        node = expected
        for k in parents:
            node = node[k]
        node[last] = value
    if json.loads(new_text) != expected:  # the text surgery must change exactly these values
        print("ERROR: internal: the rewritten components.json does not match; nothing written", file=sys.stderr)
        return 2
    out = (b"\xef\xbb\xbf" if bom else b"") + new_text.encode("utf-8")
    if out != raw:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(out)
        os.replace(tmp, path)
    for dotted, value in edits.items():
        print(f"{dotted} = {value}")
    return 0


# --------------------------------------------------------------------------------------------- handoff (Addendum G12)
ROOT = Path(__file__).resolve().parents[1]
HANDOFF_DIR = ROOT / "tools" / "handoff"
SIGNATURES = "META-INF/signatures.xml"
INBOX_FIELDS = ("Added", "Commits", "Tests", "Needs Windows verification", "Status")
MAC_GUIDE = "دليل-الماك.md"
GUIDE_PDF = "WhyNot-Cut-Guide-AR.pdf"
BINARY_SUFFIXES = {".zip", ".ccx", ".zxp", ".pdf", ".mp4", ".mov", ".png", ".jpg", ".jpeg", ".aiff", ".wav", ".m4a",
                   ".otf", ".ttf", ".woff", ".woff2"}
SECRET_DIRS = {".venv", "venv", "node_modules", "renders"}
SECRET_SUFFIXES = {".env", ".pem", ".key", ".p12", ".pfx"}
SECRET_NAMES = {".env", "id_rsa", "id_ed25519"}
CLIENT_PATH_WORDS = ("whynot-test", "whynot clients")


class HandoffError(Exception):
    """The handoff stops; nothing was swapped in (exit 2)."""


def _git(cwd, *args, check=True, binary=False):
    cmd = ["git", "-c", "core.autocrlf=false", *args]
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                       **({} if binary else {"text": True, "encoding": "utf-8", "errors": "replace"}))
    if check and r.returncode != 0:
        err = r.stderr if not binary else r.stderr.decode("utf-8", "replace")
        raise HandoffError(f"git {' '.join(args[:3])} failed: {err.strip()}")
    return r.stdout if binary else r.stdout.strip()


def _show_many(repo, rev: str, paths) -> dict:
    """{path: text or None} of files at `rev`, in one `git cat-file --batch` (git is slow to start on Windows)."""
    data = subprocess.run(["git", "cat-file", "--batch"], cwd=str(repo), capture_output=True,
                          input="".join(f"{rev}:{p}\n" for p in paths).encode("utf-8")).stdout
    out, i = {}, 0
    for p in paths:
        nl = data.index(b"\n", i)
        header = data[i:nl].split()
        i = nl + 1
        if len(header) == 3 and header[1] == b"blob":
            size = int(header[2])
            out[p] = data[i:i + size].decode("utf-8")
            i += size + 1
        else:
            out[p] = None
    return out


def clean_url(url: str) -> str:
    """The remote URL without any user:token@ part (https), so no credential is ever copied into the hand-off."""
    from urllib.parse import urlsplit, urlunsplit
    u = urlsplit(url)
    if u.scheme in ("http", "https") and "@" in u.netloc:
        return urlunsplit((u.scheme, u.netloc.rsplit("@", 1)[1], u.path, u.query, u.fragment))
    return url


def zxp_signed(path: Path) -> bool:
    """True when the .zxp is a zip holding META-INF/signatures.xml (the installer's own rule: unsigned never ships)."""
    try:
        with zipfile.ZipFile(path) as z:
            return SIGNATURES in z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def scan_secrets(root: Path) -> list:
    """Posix paths (relative to root) of secrets, caches, renders and venvs in a working tree; .git is skipped.
    A matching folder is reported once and not walked."""
    root = Path(root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        keep = []
        for d in sorted(dirnames):
            rel = (rel_dir / d).as_posix()
            if d == ".git" or is_link(Path(dirpath) / d):
                continue
            if d in SECRET_DIRS or rel.endswith("evals/results") or rel == "evals/results":
                found.append(rel)
            else:
                keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            low = f.lower()
            if (low in SECRET_NAMES or low.startswith(".env.") or Path(low).suffix in SECRET_SUFFIXES
                    or "credentials" in low):
                found.append((rel_dir / f).as_posix())
    return found


def real_client_tokens() -> list:
    """The real-client words, from the one list the product tests use (tests/test_plugin.py REAL_CLIENT_TOKENS)."""
    import ast
    src = ROOT / "whynot-cut" / "tests" / "test_plugin.py"
    try:
        tree = ast.parse(src.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as e:
        raise HandoffError(f"cannot read the real-client word list in {src}: {e}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "REAL_CLIENT_TOKENS" for t in node.targets):
            return [str(t).lower() for t in ast.literal_eval(node.value)]
    raise HandoffError(f"REAL_CLIENT_TOKENS not found in {src}: refusing to build without the real-name check")


def find_real_names(root: Path, skip: tuple = ()) -> list:
    """(relative path, word) for every real-client word in a text file (or a file name) under root."""
    toks = real_client_tokens()
    hits = []
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file() or any(s == p or s in p.parents for s in skip):
            continue
        rel = p.relative_to(root).as_posix()
        hits += [(rel, t) for t in toks if t in rel.lower()]
        if p.suffix.lower() not in BINARY_SUFFIXES:
            low = p.read_text(encoding="utf-8", errors="ignore").lower()
            hits += [(rel, t) for t in toks if t in low]
    return hits


def parse_locked_areas(text: str) -> list:
    """[(glob, owner)] from the '## Locked now' list of LOCKED-AREAS.md. A top-level bullet is either
    "- `g1`[, `g2`…]: owner" or an owner heading ("- tools track (…):"); an indented bullet's paths take the owner of
    the top-level bullet above it unless they carry their own ": owner". Lines continue on indented non-bullet lines.
    An empty list, or a path with no owner, is an error (never dropped silently)."""
    m = re.search(r"^## Locked now\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise ValueError("LOCKED-AREAS.md has no '## Locked now' section")
    bullets = []
    for ln in m.group(1).splitlines():
        if re.match(r"^\s*- ", ln):
            bullets.append(ln)
        elif bullets and ln.startswith((" ", "\t")) and ln.strip():
            bullets[-1] += " " + ln.strip()
    paths_why = re.compile(r"^((?:`[^`]+`\s*,\s*)*`[^`]+`)\s*[:—-]\s*(.+?)\s*$")
    areas, owner = [], ""
    for b in bullets:
        top = not b.startswith((" ", "\t"))
        body = b.strip()[2:].strip()
        own = paths_why.match(body)
        if own:
            why = own.group(2).strip()
            areas += [(g.strip(), why) for g in re.findall(r"`([^`]+)`", own.group(1))]
            if top:
                owner = why
        elif top:
            owner = body.rstrip(":").strip()
            if not owner:
                raise ValueError("LOCKED-AREAS.md has an empty bullet")
        else:
            globs = re.findall(r"`([^`]+)`", body)
            if globs and not owner:
                raise ValueError(f"LOCKED-AREAS.md: {', '.join(globs)} has no owner (no top-level bullet above it)")
            areas += [(g.strip(), owner) for g in globs]
    if not areas:
        raise ValueError("LOCKED-AREAS.md lists no locked path")
    return areas


def parse_mac_inbox(text: str) -> list:
    """The entries under '## Entries' of MAC-INBOX.md: [{title, <field>: value}]; every field of INBOX_FIELDS is
    required. Fenced blocks (the format example) are ignored."""
    lines, out, fence = text.splitlines(), [], False
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("```"):
            fence = not fence
        elif not fence and ln.strip() == "## Entries":
            start = i + 1
            break
    if start is None:
        raise ValueError("MAC-INBOX.md has no '## Entries' section")
    cur = None
    for ln in lines[start:]:
        if ln.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        if ln.startswith("## "):
            break
        if ln.startswith("### "):
            cur = {"title": ln[4:].strip()}
            out.append(cur)
            continue
        m = re.match(r"^- ([^:]+):\s*(.*)$", ln)
        if cur is not None and m:
            cur[m.group(1).strip()] = m.group(2).strip()
    for e in out:
        missing = [f for f in INBOX_FIELDS if not e.get(f)]
        if missing:
            raise ValueError(f"MAC-INBOX.md entry '{e['title']}' lacks {', '.join(missing)}")
    return out


def _cells(line: str) -> list:
    """The cells of one markdown table row; `\\|` is a pipe inside a cell, not a column break."""
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", inner)]


def _tag_key(tag: str) -> tuple:
    m = re.search(r"-p(\d+)(?:\.(\d+))?$", tag)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (-1, -1)


def passed_phases(progress: str, tags=(), version: str = "") -> tuple:
    """([(number, name, tag)] passed, [(number, name)] in progress) from PROGRESS.md's phase table. A phase passed when
    its state's FIRST bold run says "passed" (and not "not passed" / "failed"), or a gate tag `v<version>-p<N>` exists
    (the committed PROGRESS.md can lag behind the tag of a passed gate). Its tag is the newest gate-record tag of that
    phase, else the first vX-pN(.M) token of the tag cell."""
    gate = {m.group(1): t for t in tags if version and (m := re.fullmatch(rf"v{re.escape(version)}-p(\d+)", t))}
    newest = {}
    for r in gate_record(progress):
        newest[r["gate"]] = r["tag"]                    # gate_record is sorted oldest first: the last one wins
    passed, active = [], []
    for ln in progress.splitlines():
        cells = _cells(ln)
        if len(cells) < 3 or not re.match(r"^\d+\s", cells[0]):
            continue
        num, name = cells[0].split(None, 1)
        state = cells[1]
        bold = re.match(r"^\*\*([^*]+)\*\*", state)
        said = bold.group(1).lower() if bold else ""
        if re.search(r"\bpassed\b", said) and not re.search(r"\bnot passed\b|\bfail", said):
            tag = re.match(r"v[\w.]+-p\d+(?:\.\d+)?", cells[2])
            passed.append((num, name, newest.get(num) or (tag.group(0) if tag else (cells[2] or gate.get(num, "")))))
        elif num in gate:
            passed.append((num, name, newest.get(num) or gate[num]))
        elif "in progress" in state.lower():
            active.append((num, name))
    return passed, active


def gate_record(progress: str) -> list:
    """Rows of PROGRESS.md's '## Gate record' table (one per gate tag): [{gate, tag, windows, mac_ci, live_mac}],
    sorted oldest first by gate number then tag (whatever order they were written in). No table = []."""
    m = re.search(r"^## Gate record\s*$(.*?)(?=^## |\Z)", progress, re.M | re.S)
    rows = []
    for ln in (m.group(1) if m else "").splitlines():
        cells = _cells(ln)
        if len(cells) >= 5 and re.fullmatch(r"\d+", cells[0]):
            rows.append({"gate": cells[0], "tag": cells[1].strip("`"), "windows": cells[2], "mac_ci": cells[3],
                         "live_mac": cells[4]})
    return sorted(rows, key=lambda r: (int(r["gate"]), _tag_key(r["tag"])))


def _mac_ci_kind(cell: str) -> str:
    """'' not run, 'red' any red/failed run named in the cell (red wins), 'full' / 'smoke' green, 'other'."""
    c = re.sub(r"\b0 (?:failures?|failed|fails?)\b", "", cell.lower())
    if not c.strip() or c.strip() in ("-", "—", "none", "not run"):
        return ""
    if re.search(r"\bred\b|\bfail", c):
        return "red"
    if re.search(r"\bgreen\b|\bpass(?:ed)?\b", c):
        return "smoke" if "smoke" in c and "full" not in c else "full"
    return "other"


def gate_state(progress: str, tags=(), version: str = "") -> dict:
    """What PROGRESS.md records about the gates: passed phase numbers, phases in progress, the latest gate tag and the
    latest gate row that has a macOS CI result (the Mac line of the PREVIEW banner and WHAT-WORKS page)."""
    passed, active = passed_phases(progress, tags, version)
    rows = gate_record(progress)
    mac = None
    for r in reversed(rows):
        kind = _mac_ci_kind(r["mac_ci"])
        if kind:
            mac = {"tag": r["tag"], "ci": kind, "detail": r["mac_ci"], "live": r["live_mac"] or "Not verified"}
            break
    latest = rows[-1]["tag"] if rows else (passed[-1][2] if passed else "")
    return {"passed": [n for n, _name, _tag in passed], "active": active, "latest_tag": latest, "mac": mac}


def _live_verified(live: str) -> bool:
    low = live.lower()
    return low.startswith("verified") and not re.search(r"\bnot\b|\bpart", low)


def gate_lines_en(st: dict) -> list:
    if st["passed"]:
        L = [f"Phases passed: {', '.join(st['passed'])}"
             + (f" (latest gate tag `{st['latest_tag']}`)." if st["latest_tag"] else ".")]
    else:
        L = ["Phases passed: none yet."]
    L += [f"In progress: phase {n} ({name})." for n, name in st["active"]]
    mac = st["mac"]
    if not mac:
        L.append("macOS: never run yet (no gate in PROGRESS.md has a macOS CI result).")
        return L
    line = {"full": f"macOS: CI full suite green at `{mac['tag']}`.",
            "smoke": f"macOS: CI smoke job green at `{mac['tag']}` (not the full suite).",
            "red": f"macOS: CI red at `{mac['tag']}`: {mac['detail']}."}.get(
                mac["ci"], f"macOS: CI at `{mac['tag']}`: {mac['detail']}.")
    if st["latest_tag"] and mac["tag"] != st["latest_tag"]:
        line += f" The Mac CI was not run at `{st['latest_tag']}` (the latest gate) yet."
    L += [line, f"Live Mac checks: {mac['live']}."]
    return L


def gate_lines_ar(st: dict) -> list:
    mac = st["mac"]
    if not mac:
        return ["الماك: لسه ما اتجرّبش على ماك خالص (مفيش مرحلة في PROGRESS.md ليها نتيجة ماك)."]
    line = {"full": f"الماك: كل الاختبارات الآلية (full suite) عدّت على ماك في CI عند `{mac['tag']}`.",
            "smoke": f"الماك: الاختبار السريع (smoke) بس هو اللي عدّى على ماك عند `{mac['tag']}`، مش كل الاختبارات.",
            "red": f"الماك: فيه اختبارات فشلت على ماك عند `{mac['tag']}`."}.get(
                mac["ci"], f"الماك: فيه نتيجة CI على ماك عند `{mac['tag']}`، مش واضح إنها عدّت.")
    if st["latest_tag"] and mac["tag"] != st["latest_tag"]:
        line += f" ولسه ما اتعملش CI على ماك عند آخر مرحلة `{st['latest_tag']}`."
    if _live_verified(mac["live"]):
        live = "التجربة الحية على ماك حقيقي: اتأكّدت."
    else:
        ph = re.search(r"\bPhase (\d+)", mac["live"])
        live = "التجربة الحية على ماك حقيقي: لسه" + (f" (المرحلة {ph.group(1)})." if ph else ".")
    return [line, live]


def render(template: str, values: dict) -> str:
    out = template
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", str(v))
    left = re.findall(r"\{\{\w+\}\}", out)
    if left:
        raise HandoffError(f"template placeholders without a value: {', '.join(sorted(set(left)))}")
    return out


def _template(name: str) -> str:
    return (HANDOFF_DIR / name).read_text(encoding="utf-8")


def is_link(p) -> bool:
    """A symlink, a Windows junction or any other reparse point: never followed, never deleted through."""
    p = Path(p)
    try:
        if p.is_symlink():
            return True
        isj = getattr(os.path, "isjunction", None)
        if isj is not None and isj(p):
            return True
        return bool(getattr(os.lstat(p), "st_reparse_tag", 0))
    except OSError:
        return False


def scan_links(root: Path) -> list:
    """Posix paths (relative to root) of every link / junction under root; a linked folder is never walked."""
    root = Path(root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root)
        keep = []
        for d in sorted(dirnames):
            if is_link(Path(dirpath) / d):
                found.append((rel_dir / d).as_posix())
            else:
                keep.append(d)
        dirnames[:] = keep
        found += [(rel_dir / f).as_posix() for f in sorted(filenames) if is_link(Path(dirpath) / f)]
    return found


def _rmtree(path: Path):
    """Delete a folder this tool made, never through a link (COORDINATION rule 15): a link given as `path` is refused;
    a link inside is removed as an entry (its target is untouched) before the rest is deleted."""
    path = Path(path)
    if is_link(path):
        raise HandoffError(f"refusing to delete {path}: it is a link/junction (its target would be at risk)")
    if not path.exists():
        return
    for rel in sorted(scan_links(path), key=len, reverse=True):
        entry = path / rel
        try:
            os.rmdir(entry) if entry.is_dir() else os.unlink(entry)
        except OSError:
            os.unlink(entry)

    def fix(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
            func(p)
        except OSError:
            pass
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=fix)
    else:
        shutil.rmtree(path, onerror=fix)
    if path.exists():
        raise HandoffError(f"could not remove {path} (a file in it is open?)")


def find_bash() -> str:
    if os.name == "nt":
        cands = []
        g = shutil.which("git")
        if g:
            gp = Path(g).resolve()
            cands += [p / "bin" / "bash.exe" for p in gp.parents][:4]
        cands.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "bash.exe")
        for c in cands:
            if c.is_file():
                return str(c)
        raise HandoffError("Git Bash not found (bash.exe next to git); the sample client needs it")
    return shutil.which("bash") or "/bin/bash"


def find_ffmpeg():
    """The ffmpeg the engine and the tests use: WHYNOT_FFMPEG / NH_FFMPEG > the pinned one in the engine home > the
    engine runtime's imageio-ffmpeg binary > PATH."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for k in ("WHYNOT_FFMPEG", "NH_FFMPEG"):
        v = os.environ.get(k)
        if v:
            p = Path(v)
            p = p / exe if p.is_dir() else p
            if p.is_file():
                return p
    eng = str(ROOT / "whynot-cut" / "engine" / "reel")
    if eng not in sys.path:
        sys.path.insert(0, eng)
    try:
        from lib import plat  # stdlib only
        p = plat.engine_ffmpeg()
        if p:
            return Path(p)
        py = plat.venv_python()
        if py and Path(py).is_file():
            r = subprocess.run([str(py), "-s", "-c", "import imageio_ffmpeg as m; print(m.get_ffmpeg_exe())"],
                               capture_output=True, text=True, timeout=120)
            cand = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
            if cand and cand.is_file():
                return cand
    except Exception:  # noqa: BLE001  (fall back to PATH)
        pass
    w = shutil.which("ffmpeg")
    return Path(w) if w else None


def make_sample_client(repo_dir: Path, dest: Path):
    """The FICTIONAL Example Clinic client, made by the eval fixture (synthetic testsrc + sine clips) from the clone."""
    fixture = Path(repo_dir) / "whynot-cut" / "evals" / "_fixtures" / "example-clinic.sh"
    if not fixture.is_file():
        raise HandoffError(f"the sample client fixture is missing: {fixture}")
    ff = find_ffmpeg()
    if not ff:
        raise HandoffError("ffmpeg not found (engine home, engine runtime or PATH): the sample client needs it")
    script = ('set -eu; WNC_FF="$3"; . "$1"; find_ffmpeg() { printf "%s\\n" "$WNC_FF"; }; '
              'make_clinic "$2" profile; add_references "$2"; add_project "$2" C0239; add_episode_plan "$2"')
    r = subprocess.run([find_bash(), "-c", script, "handoff", fixture.as_posix(), Path(dest).as_posix(),
                        Path(ff).as_posix()], cwd=str(Path(dest).parent), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600)
    if r.returncode != 0:
        raise HandoffError(f"the sample client fixture failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-800:]}")


def _load_package():
    spec = importlib.util.spec_from_file_location("whynot_package_handoff", ROOT / "package.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build_plugin_zip(stage: Path, out_zip: Path) -> int:
    """package.py's release zip, built from `stage` (a HEAD snapshot + the shipped Adobe artefacts)."""
    pkg = _load_package()
    bad = pkg.disallowed_profiles(stage / "whynot-cut" / "profiles")
    if bad:
        raise HandoffError(f"refusing to package: whynot-cut/profiles/ holds {', '.join(bad)} (only _template and "
                           "example-* may ship)")
    files = pkg.package_files(stage)
    plugin = stage / "whynot-cut"
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            info = zipfile.ZipInfo((Path("whynot-cut-marketplace") / p.relative_to(stage)).as_posix(),
                                   date_time=(2026, 10, 11, 0, 0, 0))
            in_plugin = p.relative_to(plugin).as_posix() if plugin in p.parents else ""
            info.external_attr = (stat.S_IFREG | (0o755 if in_plugin in pkg.EXEC else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    with zipfile.ZipFile(out_zip) as z:
        if z.testzip() is not None or "whynot-cut-marketplace/whynot-cut/.claude-plugin/plugin.json" not in z.namelist():
            raise HandoffError(f"the plugin zip {out_zip.name} is corrupt or has no plugin.json")
        return len(z.namelist())


def _ccx_build(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            b = json.loads(z.read("build.json"))
        return f"build {b.get('build')}, from commit {b.get('sha')}"
    except (KeyError, ValueError, zipfile.BadZipFile, OSError):
        return "no build.json"


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _items(data: dict, key: str, lang: str, passed=()) -> list:
    """An item with "until_passed": "<N>" is dropped once phase N has passed (gate state, not fixed text)."""
    done = {str(n) for n in passed}
    return [i[lang] for i in data.get(key, []) if "until_passed" not in i or str(i["until_passed"]) not in done]


def what_works_ar(data: dict, ctx: dict) -> str:
    passed, active = passed_phases(ctx["progress"], ctx.get("tags", ()), ctx["version"])
    st = gate_state(ctx["progress"], ctx.get("tags", ()), ctx["version"])
    done = st["passed"]
    L = ["# WhyNot Cut: إيه اللي شغّال دلوقتي؟", ""]
    if ctx["preview"]:
        L += [f"> **نسخة تجريبية (PREVIEW) من المرحلة {ctx['phase'] or 'الحالية'}**: مش النسخة النهائية.", ""]
    L += [f"النسخة `{ctx['label']}`، الكود `{ctx['sha_short']}`، اتعملت {ctx['date']}. البيانات محدّثة لحد "
          f"{data.get('as_of', '?')}.", "",
          "الصفحة دي بتقول الحقيقة بس: المكتوب تحت \"شغّال\" اتجرّب واتأكّد، والباقي مكتوب إنه لسه.", ""]
    L += ["## المراحل اللي عدّت الاختبار", ""]
    L += [f"- المرحلة {n} ({name}): `{tag}`" for n, name, tag in passed] or ["- لسه مفيش."]
    L += [f"- المرحلة {n} ({name}): لسه شغّالة." for n, name in active]
    L += [""] + [f"- {t}" for t in gate_lines_ar(st)]
    L += ["", "## شغّال دلوقتي", ""] + [f"- {t}" for t in _items(data, "works", "ar", done)]
    L += ["", "## شغّال جزئيًا (بيتجرّب)", ""] + [f"- {t}" for t in _items(data, "partial", "ar", done)]
    L += ["", "## لسه جاي", ""] + [f"- {t}" for t in _items(data, "coming", "ar", done)]
    if ctx["excluded"]:
        L += ["", "## ملفات مش في الحزمة دي", ""] + [f"- `{e['file']}`: {e['why_ar']}" for e in ctx["excluded"]]
    L += ["", "---", "الصفحة دي متولّدة أوتوماتيك بـ `tools/release.py handoff` من `tools/handoff/what-works.json` "
          "و`PROGRESS.md`. متعدّلهاش بإيدك.", ""]
    return "\n".join(L)


def _swap(new: Path, out: Path, prev: Path, rename):
    had_old = out.exists()
    if had_old:
        if prev.exists():
            _rmtree(prev)
        rename(str(out), str(prev))
    try:
        rename(str(new), str(out))
    except OSError as e:
        if had_old:
            rename(str(prev), str(out))
        _rmtree(new)
        raise HandoffError(f"could not move the new hand-off into place ({e}); the previous one is back at {out}")
    if had_old:
        _rmtree(prev)


def handoff(repo, out, label=None, preview=False, dry_run=False, sample_maker=None, log=print, rename=os.replace,
            now=None) -> dict:
    """Build <out>/Windows and <out>/Mac (Addendum G12) from the commit at HEAD of `repo`: into <out>.new, then swap,
    keeping <out>.prev until the new one is in place. Raises HandoffError; nothing is swapped in on any failure."""
    repo = Path(repo).resolve()
    out = Path(os.path.abspath(out))           # never resolve() the output itself: that would follow a link/junction
    sample_maker = sample_maker or make_sample_client
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if not (repo / ".git").exists():
        raise HandoffError(f"not a git repo: {repo}")
    real_out = out.parent.resolve() / out.name
    if real_out == repo or repo in real_out.parents:
        raise HandoffError(f"--out must be outside the repo: {out}")
    if any(part.lower() in CLIENT_PATH_WORDS for part in out.parts):
        raise HandoffError(f"--out must not be in a client or whynot-test folder: {out}")
    for p in (out, out.with_name(out.name + ".new"), out.with_name(out.name + ".prev")):
        if is_link(p):
            raise HandoffError(f"{p} is a link/junction: the hand-off never writes, swaps or deletes through a link")
    head, branch = (_git(repo, "rev-parse", "HEAD", "--abbrev-ref", "HEAD").splitlines() + ["", ""])[:2]
    if not branch or branch == "HEAD":
        raise HandoffError("HEAD is detached: check out the release branch first")
    origin = clean_url(_git(repo, "config", "--get", "remote.origin.url", check=False))
    if not origin:
        raise HandoffError("the repo has no `origin` remote: the Mac clone must push to the same private repo")
    blobs = _show_many(repo, head, ("whynot-cut/.claude-plugin/plugin.json", "LOCKED-AREAS.md", "MAC-INBOX.md",
                                    "PROGRESS.md"))
    try:
        version = json.loads(blobs["whynot-cut/.claude-plugin/plugin.json"] or "{}")["version"]
        locked = parse_locked_areas(blobs["LOCKED-AREAS.md"] or "")
        parse_mac_inbox(blobs["MAC-INBOX.md"] or "")
    except (ValueError, KeyError) as e:
        raise HandoffError(f"at {head[:8]}: {e} (plugin.json, LOCKED-AREAS.md and MAC-INBOX.md must be committed)")
    progress = blobs["PROGRESS.md"] or ""
    dirty = len(_git(repo, "status", "--porcelain", "--untracked-files=no").splitlines())
    label = label or (f"PREVIEW-{version}" if preview else version)
    preview = bool(preview or label.upper().startswith("PREVIEW"))
    m = re.search(r"-(p\d+)$", label)
    phase = m.group(1) if m else ""

    adobe = repo / "whynot-cut" / "adobe"
    excluded, ship = [], {}
    for suffix in ("ccx", "zxp"):
        found = sorted(p for p in adobe.glob(f"*.{suffix}") if p.is_file()) if adobe.is_dir() else []
        if len(found) > 1:
            raise HandoffError(f"more than one .{suffix} in {adobe}: {', '.join(p.name for p in found)}")
        if not found:
            excluded.append({"file": f"*.{suffix}", "why": f"no built .{suffix} in whynot-cut/adobe/",
                             "why_ar": f"مفيش ملف .{suffix} متبني لسه."})
        elif suffix == "zxp" and not zxp_signed(found[0]):
            excluded.append({"file": found[0].name, "why": f"unsigned: no {SIGNATURES} inside; an unsigned panel never "
                             "ships", "why_ar": "مش متوقّع (مفيهوش توقيع)، والبرنامج مبيوزّعش لوحة من غير توقيع."})
        else:
            ship[suffix] = found[0]
    zip_name = f"whynot-cut-{version}.zip"
    ctx = {"label": label, "preview": preview, "phase": phase, "sha": head, "sha_short": head[:8], "branch": branch,
           "origin": origin, "date": now.strftime("%Y-%m-%d %H:%M UTC"), "excluded": excluded, "progress": progress,
           "version": version}
    plan = [f"handoff {label} from {head[:8]} ({branch}) -> {out}",
            f"  Windows/: {zip_name}, install.ps1, install.sh, README-installer.md"
            + "".join(f", {p.name}" for p in ship.values()) + f", {GUIDE_PDF}, README-AR.md, checksums.txt",
            f"  Mac/: repo/ (git clone --no-local, origin {origin}), sample-client/, START-HERE.md, {MAC_GUIDE}",
            "  root: WHAT-WORKS-NOW-AR.md, LABEL.txt"]
    plan += [f"  excluded: {e['file']}: {e['why']}" for e in excluded]
    if dirty:
        plan.append(f"  note: {dirty} uncommitted tracked change(s) in the source tree are NOT included (HEAD only)")
    summary = {"out": str(out), "label": label, "sha": head, "branch": branch, "origin": origin, "preview": preview,
               "dry_run": dry_run, "excluded": excluded, "files": [], "zip": zip_name}
    if dry_run:
        for ln in ["DRY RUN: nothing written"] + plan:
            log(ln)
        return summary
    for ln in plan:
        log(ln)

    new, prev = out.with_name(out.name + ".new"), out.with_name(out.name + ".prev")
    if prev.exists() and not out.exists():          # an earlier run died between the two renames: that is the last good
        rename(str(prev), str(out))
    if new.exists():
        _rmtree(new)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        _build(repo, new, ctx, ship, locked, zip_name, sample_maker, summary, log)
    except BaseException:
        _rmtree(new)
        raise
    _swap(new, out, prev, rename)
    summary["files"] = [(p.relative_to(out).as_posix(), p.stat().st_size) for p in sorted(out.rglob("*"))
                        if p.is_file() and (out / "Mac" / "repo") not in p.parents]
    return summary


def _build(repo, new, ctx, ship, locked, zip_name, sample_maker, summary, log):
    import contextlib
    import io
    import tarfile
    win, mac = new / "Windows", new / "Mac"
    win.mkdir(parents=True)
    mac.mkdir()
    clone = mac / "repo"
    # ---- Mac/repo: the full history of the branch, origin = the private GitHub repo, no stale remote-tracking refs
    _git(new, "clone", "-q", "--no-local", "--single-branch", "--branch", ctx["branch"], "--config",
         "core.autocrlf=false", str(repo), str(clone))
    got = _git(clone, "rev-parse", "HEAD")
    if got != ctx["sha"]:
        raise HandoffError(f"HEAD moved during the hand-off ({ctx['sha'][:8]} -> {got[:8]}): run it again")
    _git(clone, "remote", "set-url", "origin", ctx["origin"])
    refs = _git(clone, "for-each-ref", "--format=%(refname)", "refs/remotes/origin").splitlines()
    if refs:
        r = subprocess.run(["git", "update-ref", "--no-deref", "--stdin"], cwd=str(clone), capture_output=True,
                           input="".join(f"delete {ref}\n" for ref in refs).encode("utf-8"))   # bytes: no CRLF
        if r.returncode != 0:
            raise HandoffError("could not drop the clone's remote-tracking refs: "
                               + r.stderr.decode("utf-8", "replace").strip())
    links = scan_links(clone)
    if links:
        raise HandoffError("the clone holds links/junctions (rule 15: never a link into the live repo): "
                           + ", ".join(links))
    bad = scan_secrets(clone)
    if bad:
        raise HandoffError("the clone's working tree holds secrets, caches, renders or venvs (remove them from git "
                           "first): " + ", ".join(bad))
    ctx["tags"] = _git(clone, "tag", "--merged", "HEAD").split()      # gate tags v<version>-p<N> (WHAT-WORKS page)
    log(f"  cloned {ctx['branch']} @ {ctx['sha_short']}")

    # ---- the plugin zip: a HEAD snapshot + the shipped Adobe artefacts, their pins filled in components.json
    stage = new / ".stage"
    stage.mkdir()
    tar = new / ".stage.tar"
    _git(clone, "archive", "--format=tar", "-o", str(tar), "HEAD")
    with tarfile.open(tar) as t:
        if hasattr(tarfile, "data_filter"):
            t.extractall(stage, filter="data")
        else:
            t.extractall(stage)
    tar.unlink()
    (stage / "whynot-cut" / "adobe").mkdir(parents=True, exist_ok=True)
    for p in ship.values():
        shutil.copy2(p, stage / "whynot-cut" / "adobe" / p.name)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = cmd_fill(argparse.Namespace(plugin=str(stage / "whynot-cut"), components=None))
    if rc != 0:
        raise HandoffError("pinning the Adobe artefacts in components.json failed: " + buf.getvalue().strip())
    n = build_plugin_zip(stage, win / zip_name)
    log(f"  {zip_name}: {n} files")
    inst = stage / "whynot-cut" / "installer"
    for src, name in ((inst / "install.ps1", "install.ps1"), (inst / "install.sh", "install.sh"),
                      (inst / "README.md", "README-installer.md")):
        if not src.is_file():
            raise HandoffError(f"missing at HEAD: whynot-cut/installer/{src.name}")
        shutil.copy2(src, win / name)
    pdf = stage / "whynot-cut" / "docs" / GUIDE_PDF
    if pdf.is_file():
        shutil.copy2(pdf, win / GUIDE_PDF)
    else:
        ctx["excluded"].append({"file": GUIDE_PDF, "why": "not in the commit", "why_ar": "الدليل مش موجود في الكود."})
    for p in ship.values():
        shutil.copy2(p, win / p.name)
    _rmtree(stage)

    zip_sha = sha256_file(win / zip_name)
    what = {"zip": "الإضافة كاملة (اللي بيثبّتها الأمر تحت)", "install.ps1": "المُثبّت لويندوز",
            "install.sh": "المُثبّت للماك", "README-installer.md": "شرح المُثبّت بالتفصيل (إنجليزي)",
            "ccx": "لوحة Premiere (المُثبّت بيركّبها لوحده)", "zxp": "لوحة الجسر لـ Premiere/AE، متوقّعة (المُثبّت بيركّبها لوحده)",
            GUIDE_PDF: "دليل الاستخدام بالعربي (مسودة)", "README-AR.md": "الملف ده",
            "checksums.txt": "بصمة (sha256) كل ملف"}
    names = sorted(p.name for p in win.iterdir()) + ["README-AR.md", "checksums.txt"]
    rows = ["| الملف | إيه ده |", "|---|---|"]
    for nm in names:
        key = "zip" if nm == zip_name else (Path(nm).suffix[1:] if Path(nm).suffix in (".ccx", ".zxp") else nm)
        rows.append(f"| `{nm}` | {what.get(key, '')} |")
    excl = ""
    if ctx["excluded"]:
        excl = "## ملفات مش موجودة هنا\n\n" + "\n".join(f"- `{e['file']}`: {e['why_ar']}" for e in ctx["excluded"])
    preview_ar = (f"> **نسخة تجريبية (PREVIEW) من المرحلة {ctx['phase'] or 'الحالية'}**: مش النسخة النهائية. "
                  "شوف `WHAT-WORKS-NOW-AR.md` عشان تعرف إيه اللي شغّال وإيه اللي لسه.") if ctx["preview"] else ""
    common_vals = {"label": ctx["label"], "sha": ctx["sha"], "sha_short": ctx["sha_short"], "date": ctx["date"],
                   "preview_line_ar": preview_ar}
    (win / "README-AR.md").write_text(render(_template("README-AR.windows.md.tmpl"), {
        **common_vals, "zip_name": zip_name, "zip_sha": zip_sha, "file_table": "\n".join(rows),
        "excluded_ar": excl}), encoding="utf-8")
    sums = [f"# sha256 of every file in this folder: {ctx['label']} @ {ctx['sha_short']} ({ctx['date']})"]
    sums += [f"{sha256_file(p)}  {p.name}" for p in sorted(win.iterdir()) if p.is_file()]
    (win / "checksums.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")

    # ---- Mac: the fictional sample client, START-HERE.md, the Arabic guide
    try:
        sample_maker(clone, mac / "sample-client")
    except HandoffError:
        raise
    except Exception as e:  # noqa: BLE001
        raise HandoffError(f"the sample client could not be made: {e}")
    data = json.loads(_template("what-works.json"))
    if ctx["preview"]:
        st = gate_state(ctx["progress"], ctx.get("tags", ()), ctx["version"])
        not_yet = _items(data, "coming", "en", st["passed"]) + _items(data, "partial", "en", st["passed"])
        banner = (f"> **PREVIEW of phase {ctx['phase'] or '(current)'}: not a release.** This hand-off was cut "
                  "early so the Mac work can start; later gates regenerate it.\n>\n"
                  "> Gate state, as recorded in `PROGRESS.md`:\n" + "\n".join(f"> - {t}" for t in gate_lines_en(st))
                  + "\n>\n> What is not built or not finished yet:\n" + "\n".join(f"> - {t}" for t in not_yet))
        footer = (f"_This is a PREVIEW hand-off (phase {ctx['phase'] or 'current'}). A later `release.py handoff` "
                  "replaces this file. Between hand-offs, the repo is synced through GitHub (`mac/dev`), not by copying "
                  "folders._")
    else:
        banner, footer = f"> Release hand-off `{ctx['label']}`.", ""
    (mac / "START-HERE.md").write_text(render(_template("START-HERE.md.tmpl"), {
        **common_vals, "branch": ctx["branch"], "origin": ctx["origin"], "preview_banner": banner,
        "preview_footer": footer, "locked_areas": "\n".join(f"- `{g}`: {why}" for g, why in locked)}),
        encoding="utf-8")
    (mac / MAC_GUIDE).write_text(render(_template("mac-guide-ar.md.tmpl"), common_vals), encoding="utf-8")

    # ---- root: WHAT-WORKS-NOW-AR.md, LABEL.txt
    (new / "WHAT-WORKS-NOW-AR.md").write_text(what_works_ar(data, ctx), encoding="utf-8")
    lab = [f"label: {ctx['label']}",
           f"preview: {'yes, phase ' + (ctx['phase'] or 'current') if ctx['preview'] else 'no'}",
           f"commit: {ctx['sha']}", f"branch: {ctx['branch']}", f"origin: {ctx['origin']}", f"date: {ctx['date']}",
           f"plugin version: {ctx['version']}", f"plugin zip: {zip_name} sha256 {zip_sha}"]
    for suffix, p in sorted(ship.items()):
        extra = _ccx_build(p) if suffix == "ccx" else "signed (META-INF/signatures.xml)"
        lab.append(f"{suffix}: {p.name} sha256 {sha256_file(p)} ({extra}; a gitignored build output from the source "
                   "tree, not rebuilt by the handoff)")
    lab += [f"excluded: {e['file']}: {e['why']}" for e in ctx["excluded"]]
    lab.append("built by: tools/release.py handoff (generated; never edit by hand)")
    (new / "LABEL.txt").write_text("\n".join(lab) + "\n", encoding="utf-8")

    hits = find_real_names(new, skip=(clone,))
    if hits:
        raise HandoffError("a real client name is in the generated files: "
                           + ", ".join(sorted({f"{p} ({t})" for p, t in hits})))
    summary["zip_sha"] = zip_sha


def _say(*parts, file=None):
    """print() that never fails on a console code page without Arabic (Windows cp1252): unknown characters become ?."""
    stream = file or sys.stdout
    text = " ".join(str(p) for p in parts)
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "ascii"
        print(text.encode(enc, "replace").decode(enc), file=stream)


def cmd_handoff(args) -> int:
    try:
        s = handoff(args.repo or ROOT, args.out, label=args.label, preview=args.preview, dry_run=args.dry_run,
                    log=_say)
    except HandoffError as e:
        _say(f"ERROR: {e}", file=sys.stderr)
        return 2
    if not s["dry_run"]:
        _say(f"done: {s['out']} ({s['label']} @ {s['sha'][:8]})")
        for rel, size in s["files"]:
            _say(f"  {rel}  {_size(size)}")
        _say("  Mac/repo/  (git clone; not listed)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="release.py", description="WhyNot Cut release tool (installer parts + handoff)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("components", help="setup/components.json placeholders and Adobe artefacts")
    mode = c.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="list placeholder paths (exit 0)")
    mode.add_argument("--fill-artefacts", action="store_true", help="pin adobe/*.zxp|*.ccx (file + sha256)")
    c.add_argument("--plugin", help="plugin folder (default: whynot-cut/ next to tools/)")
    c.add_argument("--components", help="components.json to read / write (default: <plugin>/setup/components.json)")
    h = sub.add_parser("handoff", help="build the Windows + Mac hand-off folders (Addendum G12)")
    h.add_argument("--out", required=True, help="output folder (outside the repo); replaced safely via <out>.new")
    h.add_argument("--label", help="label, e.g. PREVIEW-3.0.0-p3 (default: the plugin version)")
    h.add_argument("--preview", action="store_true", help="mark it a PREVIEW (also implied by a PREVIEW-* label)")
    h.add_argument("--dry-run", action="store_true", help="print what would be built; write nothing")
    h.add_argument("--repo", help="source repo (default: the repo this tool lives in)")
    args = ap.parse_args(argv)
    if args.cmd == "handoff":
        return cmd_handoff(args)
    return cmd_check(args) if args.check else cmd_fill(args)


if __name__ == "__main__":
    sys.exit(main())
