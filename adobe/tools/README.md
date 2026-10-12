# adobe/tools — upstream reference for WhyNot Kalam / Hush / Tidy

`kalam/_upstream/`, `hush/_upstream/` and `tidy/_upstream/` are the owner-supplied original source of the three
editor tools (Addendum A §A1, `docs/superpowers/specs/addendum-a/ADDENDUM-A-kalam-hush-tidy.md`). They were copied
unchanged from the owner's `new plugin code/{kalam,hush,tidy}/`, minus macOS metadata (`._*`, `.DS_Store`) and caches
(`__pycache__`, `.pytest_cache`). The owner holds the rights (H12 confirmed).

Rules:

- **Read-only reference.** Never edit, format, rename or "fix" anything under `*/_upstream/`. It is the parity
  baseline: the upstream test suites are run against the ported modules to prove the behaviour did not change.
  `UPSTREAM-SHA256.txt` lists every file's sha256 (88 files: kalam 54, hush 12, tidy 22); a re-copy must match it.
- **Ported code lives elsewhere** (Addendum A §A2): panel tabs and pure logic in `adobe/panel-ui/tools/<tool>/`,
  host operations as `WNC_KALAM` / `WNC_HUSH` / `WNC_TIDY` / `WNC_AUDIO` in the signed bridge, engine services in
  `whynot-cut/engine/reel/` (Kalam engine package `engine/reel/kalam/`), with the product names WhyNot Kalam /
  WhyNot Hush / WhyNot Tidy (§A6b: no "Hoka", ids `ai.thewhynot.cut.<tool>`, data under `~/.whynot-cut/tools/<tool>/`).
- **Not shipped, not tested by the engine suite.** Nothing here is imported by `whynot-cut/`, discovered by
  `unittest discover -s whynot-cut/tests`, linted by `tools/jsx_lint.py` (it only reads `wnc_*.jsx`) or built by the
  `adobe/` npm workspaces. The upstream suites are run on purpose, in a temp copy, by the port's parity jobs.
- The upstream fixtures name a developer machine path and a demo speaker; they are reference data only and must not
  be copied into WhyNot Cut fixtures (see the portability audit, §1).

Portability audit and port plan: `docs/superpowers/specs/addendum-a/portability-audit.md`.
