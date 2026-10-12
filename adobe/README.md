# adobe/ - WhyNot Cut Adobe workspace (npm workspaces)

| Folder | What | Status |
|---|---|---|
| `premiere-uxp/` | Premiere Pro UXP: the **spike** plugin (measures which UXP APIs work) and, later, the WhyNot Cut panel plugin | spike: 4a; panel plugin: 4b (this table is current) |
| `panel-ui/` | Shared panel UI (Spectrum-free, brand tokens) hosted by the Premiere plugin and later After Effects | built (T6.5); mounted by the plugin (`premiere-uxp/src/shell.ts`) |

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
Bump `version` in `spike/manifest.json` (and `SPIKE_VERSION` in `spike/src/spike.ts`) for every rebuild: UPIA replaces only a newer version.

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
| `plugin/manifest.json`, `plugin/index.html`, `plugin/index.css` | package files; the page links `tokens.css`, `panel.css` (copied from `panel-ui/styles/`) then `index.css` (shell-only: page background, the copy box) |
| `src/main.ts` | entry: builds the environment (`require` of `premierepro`/`uxp` with literal calls, `document`, `navigator`) and calls `startShell`; picks the data source at build time |
| `src/shell.ts` | `startShell(env)`: theme, data source, `UxpHost`, `mount(root, source, host)`; testable with fakes |
| `src/offline-source.ts` | `OfflineSource`: the placeholder `PanelDataSource` until the engine daemon exists (T6.2): engine "not running", Host pill from `uxp.host.version` (`Application.version` is empty), language from `uxp.host.uiLocale`, no pipeline data, every action `ok:false` with `how: "In your Claude session run `reel doctor`."` (the panel renders a backticked command as a left-to-right run) |
| `src/uxp-host.ts` | `createUxpHost`: `setPlayerPosition` (active sequence, `TickTime.createWithSeconds`), `openInSourceMonitor` (`SourceMonitor.openFilePath`), `revealPath` ("Reveal folder": `uxp.shell.openPath` on the native path, returns `"done"` -> "Opened." notice, else a visible, selected path box and `"shown"`), `copyText` ("Copy diagnostics": `navigator.clipboard`, `"done"` -> "Copied." notice, else a visible, selected box). The box is a normal outcome, not an error (permission or consent refused). Paths lose the `\\?\` prefix and use backslashes on Windows (`nativePath`) |
| `src/copy-fallback.ts` | the "copy this" box shown when the clipboard (or opening a folder) is not available |
| `src/theme.ts` | `uxp.host.getBackgroundColor()` -> `--twn-bg`; `{}` / missing / light colours keep the brand dark default |

None of the host adapter's calls edit the project, so none runs inside `lockedAccess`/`executeTransaction`; the build (T6.3) does.

Build and visual checks:

```
npm run build:plugin -w premiere-uxp            # build/plugin/
$env:WNC_MOCK=1; npm run build:plugin -w premiere-uxp   # PowerShell; or: node scripts/build.mjs plugin --mock
```

A mock build bundles `MockSource` (PODCAST-TEST data) for a look at the panel inside Premiere; `package-ccx.mjs` refuses to package one.
Install the `.ccx` like the spike (UPIA, Premiere closed); it appears as **Window > UXP Plugins > WhyNot Cut**. Bump the manifest
`version` (and `plugin.json`) for every re-install: UPIA only replaces a newer version.

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
| `src/i18n.ts` | EN + AR tables (AR is typed against EN's keys) |
| `src/monogram.ts` | header monogram = `premiere-uxp/icons/dark/icon-48.png` inlined as a data URI (a test fails on drift) |
| `styles/tokens.css`, `styles/panel.css` | Appendix D tokens + `--twn-focus`; flexbox only, no web-font loading, RTL by `direction` on `.twn-rtl` |

Shell contract: put `tokens.css` then `panel.css` on the page, give `mount()` an element (`asMountRoot(el)`), a data source and a
`PanelHost { setPlayerPosition, openInSourceMonitor, revealPath, copyText }`. The panel never touches a host API itself.
