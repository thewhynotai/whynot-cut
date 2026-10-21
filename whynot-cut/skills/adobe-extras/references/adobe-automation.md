# After Effects & Photoshop Automation

## After Effects (configured integration)
- `reel ae-script` → `04_after_effects/scripts/build_<ID>_graphics.jsx` (self-contained: data + `templates/after_effects/nh_ae_lib.jsx`);
  like `ae-build`, it needs the editor's approval of the current plan.
  Arabic is embedded as `\uXXXX` escapes (immune to ExtendScript encoding guesses).
- `reel ae-build` → runs it in the installed AE (macOS `osascript … DoScriptFile`; Windows `AfterFX.exe -r <jsx>`), saves `04_after_effects/project/<ID>_NH_GFX.aep`.
  AE launches if closed; first launch may show dialogs — dismiss and re-run.
- `reel ae-render` → `aerender -project …aep` renders the queue (output module "High Quality with Alpha" = ProRes 4444 + alpha)
  to `04_after_effects/compositions/<EVENT_ID>.mov`; `reel premiere` then prefers these over PNG previews.
- Project structure: NH_BRAND/BRAND_CONTROLS (null "BRAND" with Color Controls: Brand Teal, Brand White, Brand Paper, Brand Ink —
  all fills/strokes/text colours link by expression), NH_COMPS (one comp per event), NH_CAPTIONS (CAPTIONS comp), NH_ASSETS.
- Text layers are live point text; shapes size themselves from `sourceRectAtTime` so edits re-flow.
- The script does **not** need "Allow Scripts to Write Files and Access Network" (no File.write).
- Manual fallback: AE › File › Scripts › Run Script File… → the JSX; then Render Queue › Render.

## Photoshop (configured integration)
- `reel ps-script` / `ps-build` → `05_photoshop/scripts/build_<ID>_psd.jsx`, run via `osascript … do javascript file` (macOS) or Photoshop COM `DoJavaScriptFile` (Windows).
- Jobs from `edit-decisions.json → global.photoshop_jobs`. Output `05_photoshop/layered-assets/<id>.psd` + `_preview.png`.
- Layers: Base, Client photo (copied from original — original file untouched), Brand band (group of strips), Headline/Subline (editable text), Logo.

## Failure handling
Every run writes `*-build-result.json` with stdout/stderr; a missing output = FAILED, never "done".
If AE/PS are unavailable, deliver the JSX (status SCRIPT_ONLY) + PNG previews and say so.
