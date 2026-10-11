"""Dev-only: vendor the Lucide icon set (ISC) into whynot-cut/templates/motion/icons/lucide/ at a pinned version.

    python tools/vendor_lucide.py 1.47.0 [--tarball path/to/lucide-static-1.47.0.tgz]

Downloads (or reads) the `lucide-static` npm tarball, checks it against the registry's published sha512 integrity, and
copies ONLY icons/*.svg, LICENSE and an icons.json index (name -> tags, from the package's tags.json). The tarball is
untrusted data: members are read one by one by name; nothing is extracted wholesale and nothing in it is executed.
Not shipped in the plugin zip (package.py skips tools/).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "whynot-cut" / "templates" / "motion" / "icons" / "lucide"
REGISTRY = "https://registry.npmjs.org/lucide-static"
NAME = re.compile(r"^package/icons/([a-z0-9-]+)\.svg$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--tarball", help="a local copy of the tarball (still checked against the registry integrity)")
    a = ap.parse_args()
    meta = json.load(urllib.request.urlopen(f"{REGISTRY}/{a.version}", timeout=60))
    integrity, url = meta["dist"]["integrity"], meta["dist"]["tarball"]
    if meta.get("license") != "ISC":
        raise SystemExit(f"license changed upstream: {meta.get('license')!r} — review before vendoring")
    data = Path(a.tarball).read_bytes() if a.tarball else urllib.request.urlopen(url, timeout=300).read()
    got = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != integrity:
        raise SystemExit(f"integrity mismatch: {got} != {integrity}")
    import io
    tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    DEST.mkdir(parents=True, exist_ok=True)
    for old in DEST.glob("*.svg"):
        old.unlink()
    tags, names = {}, []
    for m in tf.getmembers():
        if not m.isfile():
            continue
        hit = NAME.match(m.name)
        if hit:
            (DEST / f"{hit.group(1)}.svg").write_bytes(tf.extractfile(m).read())
            names.append(hit.group(1))
        elif m.name == "package/LICENSE":
            (DEST / "LICENSE").write_bytes(tf.extractfile(m).read())
        elif m.name == "package/tags.json":
            tags = json.loads(tf.extractfile(m).read().decode("utf-8"))
    index = {n: {"tags": [str(t) for t in tags.get(n, [])] or n.split("-"), "categories": []} for n in sorted(names)}
    (DEST / "icons.json").write_text(json.dumps({"set": "lucide", "version": a.version, "license": "ISC",
                                                 "source": url, "integrity": integrity, "icons": index},
                                                ensure_ascii=False, indent=0), encoding="utf-8", newline="\n")
    print(json.dumps({"icons": len(names), "dest": str(DEST), "version": a.version}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
