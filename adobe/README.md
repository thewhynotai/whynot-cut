# adobe/ - WhyNot Cut Adobe workspace (npm workspaces)

| Folder | What | Status |
|---|---|---|
| `premiere-uxp/` | Premiere Pro UXP: the **spike** plugin (measures which UXP APIs work) and, later, the WhyNot Cut panel plugin | spike: Task 4a; panel: 4b |
| `panel-ui/` | Shared panel UI (Spectrum-free, brand tokens) hosted by the Premiere plugin and later After Effects | Task 3 |

Node v26 / npm 11. Everything is TypeScript, bundled with esbuild, tested with `node --test` (Node runs `.ts` natively).

```
cd adobe
npm install            # once
npm run check          # tsc --noEmit in every workspace
npm test               # node --test in every workspace
npm run package:spike  # -> <repo>/dist/uxp/WhyNotCut-Spike.ccx  (gitignored)
```

`@adobe/premierepro` (26.5.0) is types only; at runtime Premiere provides `require("premierepro")`. No maintained UXP typings
package exists for Premiere, so the few UXP shapes we touch (`fs`, `os`, `uxp.host`) are typed locally in
`premiere-uxp/spike/src/uxp-types.ts`.

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

## Icons

`premiere-uxp/icons/{dark,light}/icon-{23,46,24,48}.png` (+ `@2x` siblings), generated once from `brand/logo.png` by
`premiere-uxp/scripts/make_icons.py` (engine venv Pillow: `~/.whynot-cut/venv/Scripts/python.exe adobe/premiere-uxp/scripts/make_icons.py`).
Panel chrome: the open "TWN" mark alone (white on dark, #1C0E47 on light). Plugin list: gradient tile #D95C9B -> #5400FB with the white mark.
