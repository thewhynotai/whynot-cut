<!-- Verbatim copy of BACKLOG.md section BL-22 (D:\ClaudeData\claude-api-lane\BACKLOG.md), taken 2026-10-21 03:45.
     BACKLOG.md stays the source if they differ. The "Design (master, binding)" block below is the master's, written
     for this card. -->
### BL-22 [Stage 2]: AE build warnings reach NEEDS-YOU (ADOBE-G4 d991323, executor ruling 2026-10-20)
- Today: a missing logo or image in an AE build gives one plain EN/AR ae-build warning (d991323); the agent text reports every warning word for word. No NEEDS-YOU line.
- Later: needs_you project producer (04_after_effects/ae-build-result.json or ae-assets.json, written even for ae-script), a new `assets` kind (KINDS, HEAD, needs-you.schema.json), ae_builder writes needs_you rows with client-relative refs and an empty list when clean.

### Design (master, binding)
- **The producer file is `04_after_effects/ae-assets.json`, NOT `ae-build-result.json`.** Reasons (read on release/3.0
  @ 4fb97dd): `ae_builder.execute()` rewrites `ae-build-result.json` from the run result only (a `needs_you` key put
  there by `generate()` would be lost), it is never written by `ae-script`, and `qc.py` (lines ~147, ~258-263) treats
  its mere existence as "AE extras were built". A new file written by `generate()` (which both `ae-script` and
  `ae-build` call) avoids all three.
- **One new pure module, `whynot-cut/engine/reel/lib/ae_assets_needs.py`** (the name `asset_needs.py` is reserved for
  BL-05):
  - `rows(missing, client_root, project_rel) -> list[dict]`: `missing` is the list of `(role, path)` pairs that
    `generate()` already computes (role `logo` | `image`). Each pair gives ONE producer row
    `{kind: "assets", text, text_ar, why, why_ar, ref}`: the same plain EN and Egyptian-Arabic sense as the d991323
    warning lines (what is missing, what After Effects does about it, what the editor does), `ref` client-relative
    with `/`. A path outside the client folder never becomes a bare file name as `ref` (that would point at a wrong
    file in the client root): its `ref` is the producer file itself (`<project_rel>/04_after_effects/ae-assets.json`)
    and only the file NAME appears in the text. Dedupe on (role, path), stable order.
  - `write(paths, missing) -> Path`: writes `04_after_effects/ae-assets.json` =
    `{"schema_version": 1, "needs_you": rows(...)}` with the engine's atomic `write_json`; an EMPTY list when nothing
    is missing (so a fixed file clears the line on the next build). No timestamps (NEEDS-YOU is byte-identical while
    nothing changed).
- **New NEEDS-YOU kind `assets`** (HEAD AR «ملفات ناقصة في الأفتر إفكتس», EN "Files missing from After Effects";
  the builder may improve the wording in the patch and say why), placed after `logo` in KINDS.
- **Wiring is patches only:** `needs_you.py` (KINDS, HEAD, `PROJECT_PRODUCERS` + the docstring line),
  `schemas/needs-you.schema.json` (the `kind` enum), `ae_builder.generate()` (collect the `(role, path)` pairs it
  already loops over and call `ae_assets_needs.write`). The existing warning lines stay exactly as they are.
