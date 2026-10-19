# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 The Why Not AI (thewhynot.ai)
"""3.0 Phase 4 T4.5 — the net for future readers of the client database (a source scan, no client needed).

(a) A client-database file that carries paths (lib/client_db.PATH_FIELDS: asset-manifest, typography,
    reference_analysis) is read only through `client_db.load`, which resolves the stored relative (or old absolute)
    paths. A direct read_json of one anywhere else in engine/reel fails here.
(b) A ratchet for every other direct client-database read: today's are listed (file, database file); a NEW one fails,
    and an entry its owner already swapped fails too, so the list only shrinks.
Run:  bash tools/test.sh -p test_t45_guard.py
"""
import sys as _sys
_sys.dont_write_bytecode = True  # keep the plugin folder free of __pycache__
import _isolation  # noqa: F401,E402  G79: sandbox the engine home first (tests/_isolation.py)
import re
import unittest
from pathlib import Path

sys = _sys
SK = Path(__file__).resolve().parents[1]
ENGINE = SK / "engine" / "reel"
sys.path.insert(0, str(ENGINE))

from lib import client_db  # noqa: E402

# a read_json(...) whose argument names the client database: through paths.client_db / output/client_database, or a
# `db / "..."` join of one of its folders
READ = re.compile(r"read_json\((?P<arg>[^#\n]*?(?:client_db|client_database|\bdb\)?\s*/\s*\"(?:branding|asset-manifest|"
                  r"assets/|client-database-status|profile/|reference_analysis)))")
NAME = re.compile(r"\"(?:(?:output/)?client_database/)?(?P<name>[\w./-]+\.json)\"")
# (b) today's direct reads of files WITHOUT paths, by (engine file, database file). Remove an entry when its owner
# swaps it to client_db.load.
ALLOW = {
    ("lib/ae_builder.py", "branding/brand-tokens.json"),
    ("lib/board.py", "reel-profile/profile.json"),
    ("lib/looks.py", "branding/brand-tokens.json"),
    ("lib/onboard.py", "reel-profile/profile.json"),
    ("lib/previews.py", "branding/brand-tokens.json"),
    ("lib/ps_builder.py", "branding/brand-tokens.json"),
}


# (c) the net for a read the pattern above can't see (a path built first, read later: `f = root / ".../asset-manifest
# .json"; read_json(f)`): every line that names a path-carrying file as a PATH (a join, or a string with a folder in it)
# goes through client_db, or is listed here with why it may read the stored value as it is. A new one fails, and so
# does a stale entry. lib/client_db.py and lib/ref_analysis.py write these files: they are the owners, not readers.
NAMED = re.compile(r"(?:/\s*\"|\"[^\"\n]*/)(?P<name>asset-manifest\.json|typography\.json|reference-measurements\.json|"
                   r"measurements\.json|reference_analysis)\b")
THROUGH_DB = re.compile(r"client_db\.(?:load|stored|resolved|migrate|path_fields)\(")
OWNERS = {"lib/client_db.py", "lib/ref_analysis.py", "lib/client_move.py"}
# (d) PENDING 2026-10-19 (executor ruling: the guard is never committed red): the ONE file whose swap to client_db.load
# is not in yet, and only its two reads (typography.json, asset-manifest.json). They land with
# hooks/BL-14/ae_builder.patch (ADOBE-G4), which also deletes this line. No other entry; any other direct read in that
# file still fails, and so does this entry once the file reads through client_db.load (stale).
PENDING_SWAP = ("lib/ae_builder.py", {"typography.json", "asset-manifest.json"})


def pending(f: str, name: str) -> bool:
    return f == PENDING_SWAP[0] and name.rsplit("/", 1)[-1] in PENDING_SWAP[1]
ALLOW_NAMED = {
    ("cli.py", "reference-measurements.json"),        # a video's own 01_analysis copy: only whether it exists
    ("lib/looks_recommend.py", "reference-measurements.json"),   # reads cuts_per_minute only, no path
    ("lib/looks_recommend.py", "reference_analysis"),             # (the same line's folder)
    ("lib/needs_you.py", "typography.json"),          # reads the file names of missing fonts (any form) for the editor
    ("lib/needs_you.py", "asset-manifest.json"),      # reads each asset's category only
    ("lib/plan.py", "typography.json"),               # a list of the plan's input files (fingerprint), not a read
}


def named_paths() -> list[tuple[str, int, str]]:
    out = []
    for f in sorted(ENGINE.rglob("*.py")):
        rel = f.relative_to(ENGINE).as_posix()
        if rel in OWNERS or "__pycache__" in rel:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if THROUGH_DB.search(line):
                continue
            out += [(rel, n, m.group("name")) for m in NAMED.finditer(line)]
    return out


def direct_reads() -> list[tuple[str, int, str]]:
    out = []
    for f in sorted(ENGINE.rglob("*.py")):
        rel = f.relative_to(ENGINE).as_posix()
        if rel == "lib/client_db.py" or "__pycache__" in rel:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in READ.finditer(line):
                nm = NAME.search(line, m.start())
                out.append((rel, n, nm.group("name") if nm else "?"))
    return out


class TestGuard(unittest.TestCase):
    def test_the_scan_finds_a_direct_read(self):
        self.assertTrue(READ.search('    man = read_json(paths.client_db / "asset-manifest.json", {"assets": []})'))
        self.assertTrue(READ.search('    typ = read_json(db / "branding/typography.json", {})'))
        self.assertTrue(READ.search('x = read_json(root / "output/client_database/reel-profile/profile.json")'))
        self.assertFalse(READ.search('    man = client_db.load(paths, "asset-manifest.json", {"assets": []})'))

    def test_the_database_file_is_named_the_same_whatever_the_join(self):
        for line in ('x = read_json(root / "output/client_database/reel-profile/profile.json", {})',
                     'x = read_json(p.output / "client_database/reel-profile/profile.json", {})',
                     'x = read_json(paths.client_db / "reel-profile/profile.json", {})'):
            self.assertEqual(NAME.search(line).group("name"), "reel-profile/profile.json", line)

    def test_files_with_paths_are_read_only_through_load(self):
        bad = [f"{f}:{n} reads {name}" for f, n, name in direct_reads()
               if (name == "?" or client_db.path_fields(name)) and not pending(f, name)]
        self.assertEqual(bad, [], "read these through client_db.load(paths, rel, default) (T4.5)")

    def test_the_pending_swap_is_still_pending(self):
        direct = sorted({name.rsplit("/", 1)[-1] for f, _n, name in direct_reads() if pending(f, name)})
        named = sorted({name for f, _n, name in named_paths() if pending(f, name)})
        want = sorted(PENDING_SWAP[1])
        self.assertEqual((direct, named), (want, want), f"{PENDING_SWAP[0]} reads through client_db.load now: delete "
                                                        "PENDING_SWAP")

    def test_the_named_path_scan_finds_a_two_step_read(self):
        self.assertTrue(NAMED.search('    manf = root / "output/client_database/asset-manifest.json"'))
        self.assertTrue(NAMED.search('    doc = _read(paths.client_db / "reference_analysis" / "x.json", None)'))
        self.assertTrue(NAMED.search('    t = db / "branding/typography.json"'))
        self.assertFalse(NAMED.search('    raise SystemExit("run `reel client-db` (typography.json)")'))
        self.assertTrue(THROUGH_DB.search('    man = client_db.load(paths, "asset-manifest.json", {})'))

    def test_every_named_path_goes_through_client_db_or_is_listed(self):
        seen = {(f, name) for f, _n, name in named_paths() if not pending(f, name)}
        self.assertEqual(sorted(seen - ALLOW_NAMED), [], "read it through client_db.load (T4.5), or list it with why")
        self.assertEqual(sorted(ALLOW_NAMED - seen), [], "gone already: remove it from ALLOW_NAMED")

    def test_no_new_direct_read_and_the_list_only_shrinks(self):
        seen = {(f, name) for f, _n, name in direct_reads() if not client_db.path_fields(name)}
        self.assertEqual(sorted(seen - ALLOW), [], "a new direct client-database read: use client_db.load")
        self.assertEqual(sorted(ALLOW - seen), [], "swapped already: remove it from ALLOW")


if __name__ == "__main__":
    unittest.main()
