# Client Intelligence (Stage 2)

`reel client-db` extracts machine-verifiable facts; Claude authors the semantic layer. Rebuild only when
`assets/` changes (the discovery fingerprints show changes).

## Script extracts (automatic)
- HEX colors from any document (RTF/MD/TXT/DOCX/PDF text) → `branding/brand-tokens.json.official_colors`
- Fonts (fontTools): family, weights, PostScript names, Arabic/Latin coverage, install status → `typography.json`
- Images: true dimensions after EXIF orientation, alpha actually used, RAW → JPEG derivative (sips on macOS, rawpy on Windows if installed), display derivatives → `asset-manifest.json`

## Claude authors (read the brief fully; never add facts)
| File | Content |
|---|---|
| `profile/client-profile.md` | identity, title, background, expertise, philosophy, values, positioning, core message, **Unavailable** list |
| `profile/client-identity.json` | same, structured; `verified_externally: false` unless proven |
| `profile/audience-profile.md` | audience derived from stated goals; mark observed vs stated |
| `profile/content-guidelines.md` | must / must-not / tone / CTA policy; mark *editorial* items |
| `assets/asset-classification.json` | after VIEWING every image (contact sheet): category headshot/portrait/lifestyle/logo/brand_graphic/background, description, use cases |
| `branding/brand-roles.json` | assign roles to official colors; any extra tints go under `derived` with method + `official:false`. No HEX codes in any document? `brand-tokens.json` → `measured_palettes` holds colours measured from brand images (posters, covers): after viewing the image, a role may use one, with `"source": "<image rel path>", "measured": true` — and the client is asked to confirm HEX codes |
| `branding/typography-roles.json` | map PostScript names to roles: headline/caption/term/body/small. `{"roles": {"headline": {"postscript_name": "…-Bold"}}}`; a role may also give just a style (`{"style": "Bold"}`). Every graphic draws a role in that weight (then brand.json `font_roles_fallback.weights`, then the house default); a weight the family lacks becomes the nearest one, never the first font file |
| `branding/branding-guidelines.md`, `visual-style.md`, `motion-design-rules.md` | official vs derived; observed reference styles |

Then re-run `reel client-db` so tokens/manifest merge the roles and classifications.

## Rules
- Brand files outrank references and generic templates. Report conflicts in `editing-rules.json.conflicts`.
- Missing font → report; never silently substitute.
- AI-generated likeness of the client requires explicit approval; never retouch the client's appearance.
