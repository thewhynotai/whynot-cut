<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- © 2026 The Why Not AI (thewhynot.ai) -->

# R-9.1–9.4 Identity scan, RTL lint, still matrix, distinctiveness review

R-9.1's tool is built in Phase 4 (Task 19, R-T6) by the looks track (`tools/identity_scan.py`,
`tools/identity_hashes.json`); its `tools/release.py` gate and CI step go through the executor. R-9.2–9.4 run in
Phase 9 (executor + Adobe for panel strings).

## Source-R behaviour

- A publication scanner blocks personal paths, hardware strings, private plan paths, tokens (GitHub, cloud, AI API
  keys, payment, chat) and byte-order marks before a push (an opt-in pre-push hook and a CI job).
- A lint test enforces its Arabic rule: never split Arabic into characters for animation; no grapheme segmenter.
- It has no dedicated scene test suite and no look × scene still matrix.

## Our version

### R-9.1 Identity scan (`tools/identity_scan.py`)
Goal: none of Source-R's identity strings (its product name, author, handles, URLs, emails, copyright line, package
metadata, style names, Arabic labels, scene and file names) ever appears in our repo or our release files, while the
repo never contains those strings — **not even inside the check**.

- **Hash file** `tools/identity_hashes.json`: `{"format": 2, "mode": "keyed", "algo": "hmac-sha256", "key_id":
  "<8 hex>", "norm_version": N, "max_words": N, "tokens": [<hex>…], "first": [<hex>…], "first2": [<hex>…]}`. Each
  token is stored as `HMAC-SHA256(key, normalised token)`: a salted sha256 whose salt is **secret**. Multi-word tokens
  also store their joined form (no spaces), and every token its glued-split form (CamelCase / letter-digit), so
  `NameScene` and `myName` match a CamelCase token. `first` holds the hashes of each form's first word and `first2`
  of its first two words (two prefilters, so a common first word costs one extra hash, never a phrase search).
- **Why a secret key** (Addendum I: the repo becomes public under GPL): with a public salt, short names could be
  recovered by hashing a list of common names and comparing. The key therefore lives **outside the repo**: a key
  file in the evidence folder on the owner's PC, a copy in the agency Mac's private notes folder for releases built
  there (path given by `--key-file` or the `WNC_IDENTITY_KEY_FILE` variable on either machine), and, for CI, a GitHub
  Actions secret `WNC_IDENTITY_KEY` (Yunus adds it; steps are given to him). `key_id` is the
  first 8 hex of `sha256(key)` so a wrong key is detected.
- **Without the key** (a contributor's machine, a fork): the scan prints one line "identity scan skipped: no key"
  and exits 0; the **release gate** (`tools/release.py`) and the owner's CI job on pushes to our branches run it with
  `--require-key`, where a missing key is a failure. **Pull requests from forks get no secret** (GitHub never passes
  secrets to them), so CI **skips** there instead of failing; a hit in a fork PR is caught by the required-key run on
  the push after the merge, before any release.
- **Backup**: the key and the plain list sit on one drive today. Both are backed up **together** (a copy of the
  evidence folder's `identity-key.hex` and the plain list) to a second place Yunus chooses (his own storage; a Yunus
  step). Losing the key alone means generating a new key and hash file from the plain list; losing both means the
  list must be rebuilt from the evidence report, so they are kept together.
- **Normaliser version**: the normaliser carries `NORM_VERSION`; the hash file records it as `norm_version`, and the
  scan refuses (exit 2, "regenerate the hash file") when they differ, so tuning the normaliser for the cut proposals
  can never make the scan pass silently. A fixed input/output test pins the normaliser's output.
- **Normalisation** (one function, shared by the generator, the scanner and the cut proposals; it lives in the
  engine as `engine/reel/lib/cut_proposals_norm.py`, standard library only, and `tools/identity_scan.py` loads that
  file): NFKC; case-fold; format characters
  (bidi marks, ZWJ/ZWNJ) removed; Arabic harakat and tatweel removed; أإآٱ→ا, ى→ي, ة→ه, ؤ→و, ئ→ي; every character that
  is not a letter or a digit becomes a space; whitespace collapsed. Text is first split into **segments at hard
  punctuation** (`, ; : ! ?` brackets, quotes, «», ، ؛, `|`, a `.` followed by a space or the end, a spaced dash), so
  an n-gram never joins two words across a comma or a sentence end; joiners inside a word (`- _ . / @` without spaces)
  fold to spaces inside the segment.
- **Scan**: for every text file (UTF-8, or UTF-16 with a BOM; binary files skipped by a NUL test on the first 8 KiB;
  files over 20 MB skipped by content) and **every path** (file and folder names; a name is reported once, where it
  first matches), normalise each line, then at each word whose hash is in `first`, hash the n-grams of
  1..`max_words` words and test them against `tokens`. A match also tries: CamelCase and letter/digit splits
  (`NameScene`, `name2`), an Arabic proclitic stripped (و ف ب ك ل ال وال بال لل), the line with `\uXXXX`, HTML entities
  and `%XX` decoded, and a phrase wrapped onto the next line (unless the line ends in hard punctuation or the next
  line is blank). An Arabic proclitic may leave the token's own ال (وال/بال/فال/كال/لل → ال + rest) and is tried per
  word; a remainder of 3 letters is accepted only inside a longer token, never as a whole token. A quote marker
  (`>` or `&gt;`) at a line's start does not break a wrapped phrase; `%XX` in file names is decoded too. Lines are
  counted on `\n` only. Word and pair hashes are cached, per-file and per-line prefilters skip what cannot match, and
  big trees are split over a few worker processes (a quarter of the CPU threads, at most 4; same result and order;
  one process if workers cannot start).
- **What is scanned**: by default the git-tracked + untracked-not-ignored files of the repo (`git ls-files -co
  --exclude-standard`) and their folders; with `--root <dir>` any folder (e.g. `dist/`, an **extracted** plugin zip)
  walked **without following junctions or symlinks**. A root that is not a folder, or a root with nothing to scan,
  is an error (exit 2), never "clean".
- **Report**: `path:line` and the hash prefix of the matched token, never the plain token. Any name part that matches
  is shown as `<name:hash>` (a token spread over several parts: `<path:hash>`) in every report, text and JSON, so no
  log carries a token. Unreadable files and folders that cannot be listed (locked, permission denied) are listed, never silently
  skipped (a file git lists but that was deleted from the working folder is simply skipped), and, with
  `--require-key`, fail the
  run. Exit 0 = clean (or skipped), 1 = hits, 2 = usage / key / IO error (an unexpected error is 2, never 1).
  `--json` for the release gate.
- **Generator** (`identity_scan.py make-hashes --plain <file> --key-file <file> --out tools/identity_hashes.json`):
  reads the plain list and the key from **outside the repo** (refuses either path inside the repo; `make-key` writes a
  new random 32-byte key to a path outside the repo), writes only keyed hashes; it never prints or writes plain tokens
  anywhere. The plain list lives in the evidence folder and is never committed, copied or
  quoted.
- **Speed**: the full repo scan takes < 10 s on this PC (measured, recorded in the task ledger).
- **Secret scan** (the `secrets` subcommand): generic credential patterns (GitHub, AWS AKIA/ASIA, Google, AI-API,
  Stripe, Slack incl. app tokens, Hugging Face, npm, GitLab, private-key and PGP private-key blocks) and BOMs in text
  files (not in PowerShell scripts, which need one), plus personal home paths: `<drive>:\Users\<name>\` (any case),
  `/Users/<name>/` and `/home/<name>/` (also inside `file://` URLs), where `<name>` is not a placeholder (`<…>`,
  `$…`, `%…%`, `{…}`, `you`, `user`, `name`, `runner`, `Public`, `All Users`, …). Reports `path:line` and the pattern
  name, never the secret value; with the identity key (`--key-file` or the environment) the paths it prints are
  redacted the same way as the identity scan's (without a key they are printed as they are, so `tools/release.py`
  runs the identity scan first and stops on its hits). Allowlist (`--allowlist`, default `tools/secret_allowlist.json`
  when it exists):
  entries `{path, pattern, reason}` (reason required), globs matched case-exactly, `*` within one folder, `**` across
  folders; `--require-readable` fails on unreadable files.
  - **Scope**: the release gate runs `secrets` over the **built release files** (`dist/`, the plugin zip, installer
    payloads), not the dev tree; on the dev tree it is report-only.
  - **Existing hits**: the dev tree already holds personal home paths in panel design files and tests; a cleanup
    follow-up (owned by each file's track, listed by the first report-only run) replaces them with placeholders or
    adds justified allowlist entries (`tools/secret_allowlist.json`, path + pattern + reason) before the first public
    release.
- **Tests** (`tests/test_identity_scan.py`): a planted fictional token with its own test key and hash fails in a
  temp tree (in text, in a file name, across case, Arabic variant and punctuation changes, in a joined form); a comma
  between the words does not match; the real tree passes; the generator refuses an in-repo plain list and writes no
  plain token; a missing key skips with exit 0 while `--require-key` fails; a wrong key is detected by `key_id`;
  binary files and links are skipped; the secret mode finds a planted fake token; the speed bound.
- **Gate**: `tools/release.py` runs the scan over the repo and over the built release files; any hit stops the
  release (executor hook). CI runs it on every push (executor).

### R-9.2 RTL lint
A lint over our JSX templates, motion plans and caption builders: no per-character text animators on Arabic layers
(only word or line based selectors), no pre-reversed Arabic strings, FSI/PDI isolation around Latin runs in our text
builder, no italic on Arabic; plus panel strings (Adobe) and skills text. Extends `tools/jsx_lint.py`. Tests plant
one violation of each rule (a per-character selector on an Arabic layer, a pre-reversed Arabic string, a Latin run
without isolation, an italic Arabic style) in a temp tree and expect exactly that finding; the real tree passes.

### R-9.3 Still matrix
Looks (3.0: 6) × wave-1 scenes (10) × AR/EN × 3 client brands, rendered by AE in local runs (heavy.sh / wnc-queue),
viewed by frame-inspectors with a recorded verdict per still (text, shaping, safe zone, keep-out, contrast).
QC reviews the **hardest passage first** (the densest scene, the longest Arabic line, the mixed AR/EN line), then the
full arc, and every QC record states **which evidence it used**: schema checks only, stills, sampled frames, full
playback, or the editor's acceptance. Technical success is never reported as creative acceptance.

### R-9.4 Distinctiveness review
The brand-systems-designer reviews the full matrix next to **Source-R's own preview images** in `WhyNot-Cut-3.0-Addendum/evidence/source-r-frames/` (staged by
the plan session: `S01`–`S12` per look, before/after and scene stills; images only, never copied into the repo, a
fixture or any page; builders and reviewers never fetch anything online; Source-R code is never run) and answers per
look and per scene: "recognisably ours, clearly better".
A "no" is a P1 defect with a fix list.

## Acceptance
Zero scan hits in the repo and in `dist/`; the lint passes; the matrix is viewed with a recorded verdict; the
distinctiveness verdict is "yes" for every 3.0 look and scene.
