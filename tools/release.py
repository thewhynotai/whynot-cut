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
import hashlib
import json
import os
import re
import sys
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="release.py", description="WhyNot Cut release tool (stub: installer parts)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("components", help="setup/components.json placeholders and Adobe artefacts")
    mode = c.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="list placeholder paths (exit 0)")
    mode.add_argument("--fill-artefacts", action="store_true", help="pin adobe/*.zxp|*.ccx (file + sha256)")
    c.add_argument("--plugin", help="plugin folder (default: whynot-cut/ next to tools/)")
    c.add_argument("--components", help="components.json to read / write (default: <plugin>/setup/components.json)")
    args = ap.parse_args(argv)
    return cmd_check(args) if args.check else cmd_fill(args)


if __name__ == "__main__":
    sys.exit(main())
