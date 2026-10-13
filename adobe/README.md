# adobe/ - WhyNot Cut Adobe workspace (npm workspaces)

| Folder | What | Status |
|---|---|---|
| `premiere-uxp/` | Premiere Pro UXP: the **spike** plugin (measures which UXP APIs work) and, later, the WhyNot Cut panel plugin | spike: 4a; panel plugin: 4b (this table is current) |
| `panel-ui/` | Shared panel UI (Spectrum-free, brand tokens) hosted by the Premiere plugin and later After Effects | built (T6.5); mounted by the plugin (`premiere-uxp/src/shell.ts`) |
| `cep-bridge/` | The CEP shell of the WhyNot Cut bundle `ai.thewhynot.cut.bridge` (`CSXS/manifest.xml`, `index.html`, `js/bridge.js`, `jsx/host.jsx`): the one source; the JSX libraries stay in `whynot-cut/templates/`. `whynot-cut/engine/reel/lib/cep_bundle.py` (`source_dir`, `assemble`) builds a bundle folder from it; not an npm workspace, and a shipped plugin does not carry it | T6.3 Task 1: moved here byte-identical to the installed 3.1.1 |

Node v26 / npm 11. Everything is TypeScript, bundled with esbuild, tested with `node --test` (Node runs `.ts` natively).

```
cd adobe
npm install            # once
npm run check          # tsc --noEmit in every workspace
npm test               # node --test in every workspace
npm run package:spike  # -> <repo>/dist/uxp/WhyNotCut-Spike.ccx  (gitignored)
npm run package:plugin # -> <repo>/whynot-cut/adobe/WhyNotCut-Premiere-<version>.ccx  (*.ccx ignored there until a release)
npm run package        # both
```

`@adobe/premierepro` (26.5.0) is types only; at runtime Premiere provides `require("premierepro")`. No maintained UXP typings
package exists for Premiere, so the few UXP shapes we touch (`fs`, `os`, `uxp.host`) are typed locally in
`premiere-uxp/src/uxp-types.ts` (the spike imports them from there).

## The spike (`premiere-uxp/spike/`)

A panel "WhyNot Cut Spike" with **Run spike**, **Run, keep project open** and **Copy results**. Each probe runs in its own
try/catch with its own timer; a failing probe is recorded as `ok:false` with the error and stack, never thrown. The results
file is rewritten after every probe, so a hang still leaves partial results.

Probes, in order: `host_info`, `ws_loopback`, `create_project`, `import_fcp7_xml`, `sequence_settings`, `export_frame`,
`keyframes_motion_opacity_crop`, `effects_by_match_name`, `track_rename`, `markers`, `undo_transaction`, `save_close_open`.
Match names are discovered at runtime (component chain and filter lists are dumped into the results).
`keyframes_motion_opacity_crop` also keys a clip of the imported scratch sequence that has a non-zero in-point and start with three candidate time bases (0-relative, in-point-relative, start-relative) on three different params, so the results show which basis Premiere uses.

### Preparing a run (controller)

1. Create the folder `~/.whynot-cut/uxp-spike/` and copy `premiere-uxp/spike/config.example.json` there as `config.json`:

   | key | meaning |
   |---|---|
   | `xml_path` | an engine FCP7 XML, e.g. `whynot-test/PODCAST-TEST/output/projects/EP02TEST_R02/07_premiere/interchange/EP02TEST_R02_RE_EDIT_base.xml` |
   | `work_dir` | scratch folder for the spike project, frames and filter lists, e.g. `whynot-test/_uxp-spike` (created by the plugin) |
   | `still_png` | a PNG placed on the top video track (past the sequence end) for the keyframe / effect probes, e.g. `.../03_broll/typography/GFX_002.png` (1080x1920 RGBA). Optional: without it the probes use the first clip they find |
   | `ws_url` | optional `ws://127.0.0.1:<port>/...` of the reel serve (T6.2). Absent or `null` -> `ws_loopback` records "pending reel serve (T6.2)" |

   Use absolute paths with forward slashes (`D:/...`). **Safety:** `work_dir`, `xml_path` and `still_png` must all be under
   `.../Editing Plugin/whynot-test/` (case/slash-insensitive, no `..`) and never under `WhyNot Clients`, and `ws_url` must be
   `ws://127.0.0.1` or `ws://localhost`; otherwise the whole config is rejected and treated as missing. Without a valid config only
   the read-only probes (`host_info`, `ws_loopback`) run; the rest are `ok:null` "no config". The spike only ever touches the
   scratch project it creates itself in `work_dir` (never the project that is open in Premiere): if `create_project` fails or
   the project lands outside `work_dir`, every later probe fails without calling anything on any project.
2. `npm run package:spike`, then install `dist/uxp/WhyNotCut-Spike.ccx` with Adobe's installer agent (close Premiere first):
   `"C:\Program Files\Common Files\Adobe\Adobe Desktop Common\RemoteComponents\UPI\UnifiedPluginInstallerAgent\UnifiedPluginInstallerAgent.exe" /install "<path>\WhyNotCut-Spike.ccx"`
   (the exact folder may differ per machine; find it with `where /r "C:\Program Files\Common Files\Adobe" UnifiedPluginInstallerAgent.exe`).
3. Start Premiere, open **Window > UXP Plugins > WhyNot Cut Spike** (Premiere may ask to approve the plugin's file/network access:
   allow it), click **Run spike**.
4. Results: `~/.whynot-cut/uxp-spike/results-<yyyymmdd-hhmmss>.json` (shape `{premiere, uxp, at, ops:[{op, ok, ms, detail, error}]}`;
   `ok` is `true`, `false` or `null` for "pending/skipped"), plus `filters-<ts>.json` (every video filter match/display name) in `work_dir`.
5. To check undo labelling, use **Run, keep project open** (skips `save_close_open`) and then look at Edit > Undo: it must read
   "Undo WhyNot Cut build" and one Ctrl+Z must revert the track name, audio track name and marker together.

The spike manifest (only the spike, not the product plugin) also requests `clipboard: readAndWrite` so **Copy results** works;
without it `navigator.clipboard` throws. Nothing but the Copy handler touches the clipboard API. Premiere returns
`project.path` as `\\?\D:/...` (long-path prefix, mixed slashes); the safety checks strip `\\?\`, `//?/` and `\\?\UNC\` first.
Bump `version` in `spike/manifest.json` (and `SPIKE_VERSION` in `spike/src/version.ts`, the one source the page, the results
file and the link probe read) for every rebuild: UPIA replaces only a newer version.

### Hands-free runs (`run-request.json`) and the spike's views

The spike polls `~/.whynot-cut/uxp-spike/run-request.json` on load and every 5 s while its panel is open, so the controller
runs it without a click: write the request, wait for `run-done-<id>.json`, read it and the results file it names. A request
is `{"id": "<letters, digits, . _ ->", "mode": "<mode>", "requested_at": "<ISO time>"}`; it is claimed once (an id never
runs twice), ignored after 30 minutes, and a malformed one is moved aside with a `run-error-<stamp>.json` saying why.

| `mode` | What it runs | Stays on screen |
|---|---|---|
| `full` | `ui_probes` + `eco_probes`, every Premiere probe, then `openExternal` last | the main view |
| `keep_open` | the same without save/close/open and without `openExternal`: the scratch project stays open | the main view |
| `style_guide` | opens the **Style guide** (every `panel-ui` kit component, `kit/gallery.ts`), then `ui_probes` + `eco_probes`; no Premiere probe. Optional `"lang": "en" \| "ar"`, `"width": 280 \| 340 \| 480`, and (0.1.9) `"scroll": <px>`: after the run the guide's scroll region is scrolled to that offset, so the lower components (dialog, empty state, log drawer, frame grid, waveform, footer) can be captured without a mouse wheel. The done file records `scroll` `{requested, top, scroll_height, client_height}` (the region's `scrollTop` after the scroll, `scrollHeight`, `clientHeight`) | the style guide, until **Back** |
| `css_lab` | opens the **CSS lab** (the UXP CSS measurements behind the kit's rules, `docs/adobe/uxp-parity.md`), writes `lab`, then `ui_probes`; takes no view (it uses the panel's own width) | the CSS lab, until **Back** |

To page through the style guide, send one request per offset (0, then about one panel height more each time, up to the
`scroll.scroll_height` the first done file reports) and capture the screen after each done file.

### Where the home folder comes from

`require("os").homedir()` first; then `process.env.USERPROFILE`, `HOME`, `HOMEDRIVE+HOMEPATH`. Which one worked is recorded as
`home_via` in the results. UXP `fs` calls use the promise API when present, else the `*Sync` twin.

## The plugin (`premiere-uxp/plugin/`, `premiere-uxp/src/`)

The WhyNot Cut panel for Premiere: manifest v5, id `ai.thewhynot.cut.dev` (dev id; the release id is decided at release),
panel `whynotCut`, `host {app: premierepro, minVersion: 26.5.0}`, permissions `localFileSystem: fullAccess`, the
loopback network domains, `clipboard: readAndWrite` and `launchProcess {schemes: ["file"], extensions: [".mp4", ".mov", ".prproj", ""]}` (owner decision 2026-10-12), panel 340x640 preferred / 280x320 minimum, the same icon set as the
spike. The manifest `version` must equal `whynot-cut/.claude-plugin/plugin.json` (a test enforces it).

| File | What |
|---|---|
| `plugin/manifest.json`, `plugin/index.html`, `plugin/index.css` | package files; the page links, in this order, `tokens.css` (copied from `brand/tokens.css`, the one token source), `panel.css` and `kit.css` (from `panel-ui/styles/`; `kit.css` after `panel.css`, scoped to `.kit-root`) then `index.css` (shell-only: page background, the copy box). No `fonts.css` link: Premiere UXP loads no `@font-face` (see Fonts below); the build still copies `fonts.css` + `panel-ui/fonts/` (bundled OFL fonts) into the plugin and the spike for CEP / Chromium and the font-bundle test |
| `src/main.ts` | entry: builds the environment (`require` of `premierepro`/`uxp` with literal calls, `document`, `navigator`) and calls `startShell`; picks the data source at build time |
| `src/shell.ts` | `startShell(env)`: data source, `UxpHost`, `mount(root, source, host)`; testable with fakes. It reads no host theme: the panel is always the website's black (`--twn-bg` `#000000`, Addendum B), never Premiere's grey |
| `src/offline-source.ts` | `OfflineSource`: the placeholder `PanelDataSource` until the engine daemon exists (T6.2): engine "not running", Host pill from `uxp.host.version` (`Application.version` is empty), language from `uxp.host.uiLocale`, no pipeline data, every action `ok:false` with a plain-words `how` ("Open your Claude session to start the engine, then wait a moment.", in Arabic for an Arabic UI). Never a command: the editor's screen shows sentences and one fix button; commands live in the log drawer and Copy diagnostics (Addendum C1.4) |
| `src/uxp-host.ts` | `createUxpHost`: `setPlayerPosition` (active sequence, `TickTime.createWithSeconds`), `openInSourceMonitor` (`SourceMonitor.openFilePath`), `revealPath` ("Reveal folder": `uxp.shell.openPath` on the native path, returns `"done"` -> "Opened." notice, else a visible, selected path box and `"shown"`), `copyText` ("Copy diagnostics": `navigator.clipboard`, `"done"` -> "Copied." notice, else a visible, selected box). The box is a normal outcome, not an error (permission or consent refused). Paths lose the `\\?\` prefix and use backslashes on Windows (`nativePath`) |
| `src/copy-fallback.ts` | the "copy this" box shown when the clipboard (or opening a folder) is not available |

None of the host adapter's calls edit the project, so none runs inside `lockedAccess`/`executeTransaction`; the build (T6.3) does.

Build and visual checks:

```
npm run build:plugin -w premiere-uxp            # build/plugin/
$env:WNC_MOCK=1; npm run build:plugin -w premiere-uxp   # PowerShell; or: node scripts/build.mjs plugin --mock
```

A mock build bundles `MockSource` (PODCAST-TEST data) for a look at the panel inside Premiere; `package-ccx.mjs` refuses to package one.
Install the `.ccx` like the spike (UPIA, Premiere closed); it appears as **Window > UXP Plugins > WhyNot Cut**. Bump the manifest
`version` (and `plugin.json`) for every re-install: UPIA only replaces a newer version.

**Dev install without a version bump (C2.6):** every `.ccx` carries `build.json {product, build, sha}` (manifest version, UTC
build id, `git rev-parse --short HEAD` + `-dirty`). A dev id (`*.dev`) is packaged as **"WhyNot Cut (dev)"** (name and panel
label); the source manifest keeps the release name "WhyNot Cut". From `adobe/`:
`npm run package:plugin && npm run dev-install -- ../whynot-cut/adobe/WhyNotCut-Premiere-<version>.ccx`. It starts Creative Cloud
if needed, runs UPIA `/remove <id>` (then `/remove <installed name>` when the id does not work), `/install`, and exits non-zero
unless the output says "Installation Successful", `/list all` lists the name and version under Premiere Pro, and the installed
folder's `build.json` (located through `%APPDATA%\Adobe\UXP\PluginsInfo\v1\premierepro.json`) equals the packaged one. The release
id `ai.thewhynot.cut` needs `--release`. Exit 2 = could not start (one sentence why), 1 = install not confirmed.

## Contract test (`premiere-uxp/test/contract.test.ts`)

ajv (2020 dialect + `ajv-formats`) loads every `whynot-cut/engine/reel/contract/*.schema.json`, compiles them (all added first, then
fetched by `$id`, `strictSchema` on), checks the request/result envelopes, validates every `request.json` / `result.json` under
`whynot-cut/tests/fixtures/contract/` (envelope + the action's `$defs/data`, or `$defs/readback` / `readback_failure`; other JSON there only has to
parse; zero fixtures pass while the folder does not exist) and validates what `MockSource` returns and what the panel's buttons send.

## Icons

`premiere-uxp/icons/{dark,light}/icon-{23,46,24,48}.png` (+ `@2x` siblings), generated once from `brand/logo.png` by
`premiere-uxp/scripts/make_icons.py` (engine venv Pillow: `~/.whynot-cut/venv/Scripts/python.exe adobe/premiere-uxp/scripts/make_icons.py`).
Panel chrome: the open "TWN" mark alone (white on dark, #1C0E47 on light). Plugin list: gradient tile #D95C9B -> #5400FB with the white mark.

## panel-ui (`panel-ui/`)

The shared WhyNot Cut panel: TypeScript + two CSS files, no UI framework. Premiere UXP (4b) and the After Effects CEP panel
compile it in; each shell passes a `PanelHost` adapter and a `PanelDataSource` (the engine daemon later, `MockSource` now).

```
cd adobe
npm test -w panel-ui          # node --test (strings, escaping, bdi, RTL, QC tiles, mount flows, schema conformance)
npm run check -w panel-ui     # tsc --noEmit
npm run dev:build -w panel-ui # -> panel-ui/dev/out/ (gitignored)
```

Open the dev harness over http (a `file://` page works too in most browsers):
`cd panel-ui/dev/out && python -m http.server 8765`, then `http://127.0.0.1:8765/index.html`. Query string:
`?lang=ar&w=340&scenario=showcase|approval|building|qc|idle&offline=1`. The toolbar has EN/AR, width 280/340/480, a state picker,
"Simulate build progress" and "Engine offline".

| File | What |
|---|---|
| `src/contract.ts` | v4 types; `PROTOCOL` and the action list come from `whynot-cut/engine/reel/contract/protocol.json` (a test and a compile-time check keep them equal) |
| `src/source.ts` | `PanelState`, `PanelDataSource` (what the daemon will implement) |
| `src/mock.ts` | `MockSource` + `sampleState()`: PODCAST-TEST (EN) and an Arabic client-name/path variant |
| `src/render.ts` | `render(state, strings, ui)` -> HTML string; `esc()`; every dynamic value escaped; commands/paths/timecodes in `<bdi dir="ltr">` |
| `src/mount.ts` | `mount(root, source, host)`: renders, subscribes, event delegation; the host-only things go through `src/host.ts` |
| `src/actions.ts` | the host requests the buttons send (checked against the v4 action schemas in tests) and the `rebuild` intent (`PanelDataSource.rebuild`: the daemon expands it into a full engine rebuild; the panel never sends `build_project`) |
| `i18n/en.json`, `i18n/ar.json`, `src/i18n.ts` | the ONE string table (identical keys; tests fail on a missing key or a hard-coded string in the render code); `i18n.ts` only loads and types it (AR is typed against EN's keys) |
| `src/monogram.ts` | header monogram = `premiere-uxp/icons/dark/icon-48.png` inlined as a data URI (a test fails on drift) |
| `../brand/tokens.css`, `styles/fonts.css`, `fonts/`, `styles/panel.css`, `styles/kit.css` | Addendum B brand tokens (always dark; copied at build time, never duplicated), `@font-face` for the bundled OFL fonts (CEP / Chromium only, see Fonts), the panel styles (colours only via tokens; flexbox only; RTL by `direction` on `.twn-rtl`), the component kit's styles (below) |
| `src/kit/` | the component kit (below) |
| `src/commands.ts` | the command detectors (below) |

Shell contract: put `tokens.css`, `panel.css`, then `kit.css` on the page (a CEP / Chromium page puts `fonts.css` first), give
`mount()` an element (`asMountRoot(el)`), a data source and a `PanelHost { setPlayerPosition, openInSourceMonitor, revealPath,
copyText }`. The panel never touches a host API itself.

### Fonts

Premiere UXP loads **no** `@font-face` in any form (spike 0.1.7 CSS lab: relative, `plugin:/`, `.woff`, a runtime `<style>`,
`FontFace`, a data URI). So every token stack in `brand/tokens.css` names the brand family first (Syne, Inter, IBM Plex Sans
Arabic, IBM Plex Mono), then Windows / macOS system fonts, then a generic family; the panel must look right with the system
fonts alone. The WhyNot Cut installer installs the brand fonts for the user, and then the same stacks pick them up. `fonts.css`
(with `fonts/` and each OFL licence) is linked only by CEP / Chromium pages (the dev harness); no UXP page links it, though
the bundles still carry it.

### The component kit (`src/kit/`, `styles/kit.css`; B-T1)

Pure functions that return escaped HTML, like `render.ts`: header, tabs, card, button, chip, step strip, progress, toast,
dialog, empty state, checklist, log drawer, frame grid, waveform frame, root + footer. `kit/gallery.ts` renders all of them
(the dev harness's `?scenario=kit` and the spike's Style guide). The UXP rules come from live Premiere renders and are tested
in `test/kit-uxp.test.ts`: no `<button>` (a control is `<div role="button" tabindex="0">`; Enter on keydown and Space on
keyup activate it, `kit/activate.ts`, wired by `mount.ts`), flexbox with physical margins (no `gap`, no `margin-inline`),
icons filled by `.kit-ink-*` classes, the main CTA marked by a solid 1 px ring (`--twn-cta-ring`), and the Arabic progress
fill pinned to the right physically. B-T2 moves `render.ts` onto the kit; `test/btn-debt.ts` pins the `<button` count in
`render.ts`, which may only go down, to 0.

### Commands never reach the editor's screen (`src/commands.ts`)

One module, two detectors (Addendum C1.4, C2.2). `looksLikeCommand` / `commandIn` is high recall: the guard tests run it over
our own strings (the string table, every source literal, the rendered panel; `test/no-commands-scan.ts`), where a false
alarm only means rewording a sentence. `containsRuntimeCommand` is high precision: `runtimeText()` runs it on engine and host
texts at run time (in `render.ts`, `mount.ts` and the kit's toast, progress and frame grid); "Claude Code" reads "Claude", and
a text that still holds a command is never cut up: the panel shows its own sentence ("The details are in the log.") and the
raw words go to the log drawer, token-scrubbed.
