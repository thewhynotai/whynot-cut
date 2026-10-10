#!/usr/bin/env python3
"""Build the distributable zip of this marketplace (plugin + marketplace.json), clean of caches and OS metadata.

    python package.py            -> ../whynot-cut-<version>.zip
Unix permissions are kept so bin/reel and the setup scripts stay executable after unzipping on macOS.
"""
import json
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache"}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
EXEC = {"bin/reel", "setup/setup_env.sh", "setup/setup_env.py", "hooks/run_python.sh", "hooks/guard.py",
        "hooks/session_context.py", "examples/make_demo.py"}


def wanted(p: Path) -> bool:
    rel = p.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts) or p.name in SKIP_FILES or p.name.startswith("._"):
        return False
    if p.suffix in (".pyc", ".tmp") or rel.as_posix().endswith(".local.md") or p.name == "package.py":
        return False
    return p.is_file()


def main():
    version = json.loads((ROOT / "whynot-cut/.claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    out = ROOT.parent / f"whynot-cut-{version}.zip"
    files = sorted(p for p in ROOT.rglob("*") if wanted(p))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            arc = Path("whynot-cut-marketplace") / p.relative_to(ROOT)
            info = zipfile.ZipInfo(arc.as_posix(), date_time=(2026, 10, 11, 0, 0, 0))
            in_plugin = p.relative_to(ROOT / "whynot-cut").as_posix() if p.is_relative_to(ROOT / "whynot-cut") else ""
            mode = 0o755 if in_plugin in EXEC else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
        names = z.namelist()
    print(json.dumps({"zip": str(out), "files": len(names), "bytes": out.stat().st_size, "corrupt_member": bad,
                      "has_manifest": "whynot-cut-marketplace/whynot-cut/.claude-plugin/plugin.json" in names}, indent=2))
    return 0 if bad is None else 1


if __name__ == "__main__":
    sys.exit(main())
