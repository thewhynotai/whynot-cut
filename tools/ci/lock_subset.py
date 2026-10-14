#!/usr/bin/env python3
"""Write a hash-pinned subset of an engine runtime lock (G-T13, CI only).

    python3 tools/ci/lock_subset.py <lock> <out> <package> [<package> ...]

The lock is uv's `pip compile --generate-hashes` output (whynot-cut/setup/locks/runtime-<platform>.lock). The subset
keeps each named package plus everything it depends on, found from the lock's own `# via` comments (a package whose
`via` names a kept package is kept too, repeated until nothing changes), with every hash line intact, so
`pip install --require-hashes -r <out>` installs exactly the locked, verified wheels and still refuses anything
unpinned. A named package that is not in the lock is an error (a typo must not silently install less).
Stdlib only, Python 3.8+.
"""
import re
import sys

_HEAD = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse(text: str) -> dict:
    """{name: {"lines": [...], "via": set()}} in lock order."""
    pkgs, cur, in_via = {}, None, False
    for line in text.splitlines():
        m = _HEAD.match(line)
        if m:
            cur = norm(m.group(1))
            pkgs[cur] = {"lines": [line], "via": set()}
            in_via = False
            continue
        if cur is None:
            continue
        s = line.strip()
        if line.startswith("    --hash=") or line.startswith("    #") or not s:
            if s:
                pkgs[cur]["lines"].append(line)
            if s.startswith("# via"):
                rest = s[len("# via"):].strip()
                in_via = not rest
                if rest and not rest.startswith("-r"):
                    pkgs[cur]["via"].add(norm(rest))
            elif in_via and s.startswith("#"):
                v = s.lstrip("#").strip()
                if v and not v.startswith("-r"):
                    pkgs[cur]["via"].add(norm(v))
            continue
        cur, in_via = None, False
    return pkgs


def closure(pkgs: dict, roots) -> list:
    keep = set()
    for r in roots:
        n = norm(r)
        if n not in pkgs:
            raise SystemExit(f"lock_subset: {r} is not in the lock")
        keep.add(n)
    changed = True
    while changed:
        changed = False
        for n, p in pkgs.items():
            if n not in keep and p["via"] & keep:
                keep.add(n)
                changed = True
    return [n for n in pkgs if n in keep]


def main(argv) -> int:
    if len(argv) < 4:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    lock, out, roots = argv[1], argv[2], argv[3:]
    with open(lock, encoding="utf-8") as f:
        pkgs = parse(f.read())
    names = closure(pkgs, roots)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# subset of {lock} for: {' '.join(roots)} (tools/ci/lock_subset.py)\n")
        for n in names:
            f.write("\n".join(pkgs[n]["lines"]) + "\n")
    print(" ".join(names))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
