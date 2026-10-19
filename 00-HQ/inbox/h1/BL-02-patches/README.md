# BL-02 patches (outside H1's fence)

Both are `git diff`s against `release/3.0` @ 4c1e59c. `git apply --check` passed on a clean tree for both (patch 2
was checked as written here; this file's blank context lines are empty, which git accepts). They touch different spots
of `test_structure.py`, so they apply in either order.

## 1-executor-licence-plugin-json-package.patch (executor, at the gate; any time after BL-02 merges)
1. Before applying, replace the plugin's licence with the GPL text (kept out of the diff because it is 35 KB):
   `cp LICENSE whynot-cut/LICENSE` (the repo-root `LICENSE` from BL-02, sha256 `3972dc97…6986`).
2. `git apply 1-executor-licence-plugin-json-package.patch`:
   - `whynot-cut/.claude-plugin/plugin.json`: `"license": "GPL-3.0-or-later"` (was `UNLICENSED`);
   - `package.py`: `SHIP_TOP` also ships the root `LICENSE` and `THIRD-PARTY-NOTICES.md`;
   - `test_structure.py` `TestLicence` (2 tests): the licence field, `whynot-cut/LICENSE` == root `LICENSE`, and
     the zip holds both files. Tested here with the patch applied: 2 OK.
3. Then run `claude plugin validate --strict` (Task 18 acceptance). Not run by me.

## 2-executor-test_structure-spdx-check-AFTER-apply.patch (executor, ONLY after `spdx_headers.py --apply`)
- Adds `TestSpdxHeaders`: no owned source file is missing the header, none is partial.
- It is RED before `--apply` (567 files missing on `release/3.0`). On a `git archive` snapshot, `--apply` then the
  same check came back clean (rc 0), and a second `--apply` wrote nothing.
- Gate order: `python tools/spdx_headers.py --apply .` (when the trees are quiet), review the diff, commit, then
  apply this patch.

## Not patched (other owners)
- `README.md`, the panel About screen (Adobe track), the installers: «© 2026 The Why Not AI» + "GPL-3.0-or-later"
  + a link to `TRADEMARKS.md` (Task 18). The NVIDIA §7 text (`docs/legal/DRAFT-gplv3-s7-nvidia.md`) goes next to
  `LICENSE` after its review.
- `whynot-cut/THIRD_PARTY_NOTICES.md` (the old Lucide-only file) can go once the root `THIRD-PARTY-NOTICES.md`
  ships. The generator keeps listing it as "ours" until then.
