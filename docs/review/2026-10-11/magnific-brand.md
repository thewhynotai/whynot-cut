# WhyNot Cut: Magnific MCP research and The Why Not AI brand extract

Research date: 2026-10-11. Researcher: Claude (subagent). Nothing in the plugin was changed.

Evidence labels used below:
- **[doc]**: read on an official page (URL given).
- **[live]**: observed directly today with a public, unauthenticated HTTP request (no tool call, no sign-in).
- **[3rd]**: third-party or search-snippet source, not verified against the primary page.
- **[derived]**: my own proposal or inference.

---

## PART 1: Magnific MCP

### 1.1 What it is, who runs it, and how auth works

- **Who runs it.** Magnific is the new name of **Freepik**. Freepik rebranded as Magnific on **28 April 2026** and brought its stock library and AI suite under one name. The name comes from Freepik's May 2024 acquisition of Magnific AI, the upscaler [3rd: relevantaudience.com, media-marketing.com, raxxo.shop]. Supporting signals: the MCP server's CORS header allows `X-Pikaso-Client` (Pikaso is Freepik's real-time tool) [live], and stock API examples still return `img.freepik.com` URLs and `freepik.com/profile/license/pdf/...` license links [doc].
- **What it does.** A remote MCP server at `https://mcp.magnific.com`. The docs say it lets an assistant "generate images and video, train consistent characters, upscale assets, and browse your generation history". It runs on the user's Magnific account and **spends the same credits as the web app** [doc: https://docs.magnific.com/modelcontextprotocol].
- **Transport.** Streamable HTTP. Nothing is installed locally [doc].
- **Auth.** OAuth 2.0 with the user's Magnific account. **No API key** [doc]. Live metadata [live]:
  - Protected resource: `https://mcp.magnific.com/.well-known/oauth-protected-resource`. It names the authorization server `https://auth.magnific.com/realms/mcp` (Keycloak) and the scopes `openid profile email mcp:custom-audience`. It also advertises `basic` and `offline_access`, so refresh tokens are available.
  - Authorization server metadata has a `registration_endpoint`, so **Dynamic Client Registration is supported**. Claude Code can therefore authorise without a pre-registered client ID or `--callback-port`. PKCE `S256` is supported.
  - An unauthenticated `POST /` returns `401 {"message":"Unauthenticated."}` with `WWW-Authenticate: Bearer error="invalid_token", resource_metadata=".../.well-known/oauth-protected-resource", scope="openid profile email mcp:custom-audience"`.
- **Claude Code (this machine).** The server is already configured at **user scope** in `~/.claude.json` as `"magnific": {"type":"http","url":"https://mcp.magnific.com"}`. To authorise:
  1. Run `/mcp`, select **magnific**, choose **Authenticate**, then sign in to Magnific in the browser and approve. The CLI equivalent is `claude mcp login magnific`.
  2. Claude Code stores the token securely and refreshes it automatically. After a 401 it refreshes and retries once. **Clear authentication** in `/mcp` revokes it [doc: https://code.claude.com/docs/en/mcp].
  3. The official add command is `claude mcp add --transport http magnific https://mcp.magnific.com` [doc].
- **claude.ai connectors.** Profile menu → **Customize** → **Connectors** → **Add connector** → **Add custom connector**. Set Name `Magnific` and URL `https://mcp.magnific.com`, then complete OAuth [doc]. When Claude Code is logged in with a claude.ai subscription, connectors appear in Claude Code automatically. A server added in Claude Code **takes precedence over a connector with the same URL**, and `/mcp` then lists the connector as hidden [doc: code.claude.com/docs/en/mcp]. On Team and Enterprise plans only admins can add connectors.

### 1.2 Exact tools exposed

Source: the "Available tools" list at https://docs.magnific.com/modelcontextprotocol. The page says the **live `tools/list` response is the source of truth**. **Input and output schemas are not published.** They can only be read after OAuth, by running `tools/list`, for example by asking Claude to describe the tools after `/mcp` authentication. The descriptions below are the docs' own one-liners.

| Group | Tool | Doc description | Spends credits? [derived] |
|---|---|---|---|
| Account | `account_balance` | current credit balance | no |
| | `project_report` | overview of project usage | no |
| Creations | `creations_search` | search your creations by query and filters | no |
| | `creations_get` | fetch a single creation by identifier | no |
| | `creations_show` | render creations inline in supported clients (MCP Apps UI, not rendered in the Claude Code terminal) | no |
| | `creations_wait` | wait for an in-progress creation to finish | no |
| | `creation_status` | poll the status of an in-progress creation | no |
| | `creations_request_upload` / `creations_upload` / `creations_finalize_upload` | upload an asset (3-step upload) | no (but the data leaves the machine) |
| | `creations_move` | move a creation between folders | no |
| Image | `images_generate` | generate images from text and optional references | **yes** |
| | `images_generate_svg` | generate SVG output | **yes** |
| | `images_to_svg` | convert raster to SVG | likely yes |
| | `images_upscale` | Magnific upscaler | **yes** |
| | `images_crop` | smart crop | likely yes |
| | `images_resize` | resize | likely low or none |
| | `images_remove_background` | alpha cutout | likely yes |
| | `images_models_list` / `images_models_show` | image model catalog | no |
| Video | `video_generate` | generate video | **yes (high)** |
| | `video_models_list` / `video_models_show` | video model catalog | no |
| Audio | `audio_tts` | text-to-speech | **yes** |
| | `audio_voices_list` / `audio_voices_show` | voice catalog | no |
| 3D | `models3d_generate` | generate a 3D model | **yes** |
| Custom references | `custom_references_create` | train a Soul character or style | **yes** |
| | `custom_references_list` | list trained references | no |
| Folders and Spaces | `folders_list` / `folders_get` / `folders_create` / `folders_rename` / `folders_delete` | (no descriptions) | no |
| | `spaces_list` / `spaces_view` | list or inspect Spaces | no |
| Discovery | `tools_show` | surface the picker UI for available tools | no |

**Async pattern.** Generation is asynchronous. The generate call returns a creation; then call `creation_status` to poll or `creations_wait` to block until done. Then `creations_get` returns the result, presumably with a download URL. **Not in the docs [derived]:** exact field names, URL lifetime, and whether results come back as image content. If an MCP tool does return PNG/JPEG/WebP content, Claude Code saves the original bytes to the session's `tool-results` folder [doc: code.claude.com/docs/en/mcp].

**Not exposed through MCP, according to the docs.** These exist only in the **REST API** (`https://api.magnific.com`, header `x-magnific-api-key`) [doc: https://docs.magnific.com/llms.txt]:
- **Stock search and download:** `GET /v1/resources` (photos, vectors, PSD), `GET /v1/icons`, `GET /v1/videos`, each with `/{id}` and `/{id}/download`.
- **Sound effects:** `POST /v1/ai/sound-effects` with `text` (≤2500 chars), `duration_seconds` 0.5–22, `loop`, `prompt_influence` 0–1 and `webhook_url`. It returns a `task_id`, which is polled with `GET /v1/ai/sound-effects/{task-id}`.
- **Music** (ElevenLabs): `POST /v1/ai/music-generation`.
- **Upscaler Creative vs Precision** as separate endpoints, plus Relight, Style Transfer, Image Expand, Audio Isolation (SAM Audio), and VFX.
- REST async works the same way: you get a `task_id`, then poll or pass a `webhook_url`. Webhooks are signed with HMAC-SHA256 over `webhook-id.webhook-timestamp.body` [doc: https://docs.magnific.com/webhooks].

Useful REST stock filters, if a REST path is ever added [doc]:
- **Videos** (`GET /v1/videos`): `term` (required), `order=relevance|recent|random`, and `filters[orientation]=vertical`, `filters[aspect_ratio]=9:16`, `filters[duration][from|to]`, `filters[category]=footage|motion_graphics`, `filters[fps]`, `filters[license][premium|free]`, `filters[ai-generated]`, `filters[topic]`.
- **Resources** (`GET /v1/resources`): `filters[people]`, `filters[orientation]`, `filters[content_type]`, `filters[license]`, `filters[ai-generated]`, `filters[vector]`, `filters[psd]`, and **`filters[color]` (includes purple and pink)**.
- Each search item includes `licenses: [{type, url}]`, where the URL is a license PDF. The manifest should store this.
- `Accept-Language` is supported, so search terms can be Arabic.

### 1.3 Pricing, credits, rate limits

- **Credits.** MCP tools draw on the same credit balance as the app. The cost depends on the model and resolution. Rates are on the pricing page [doc]. Per-operation credit costs **are not in the API docs**. The `/pricing` docs page links to separate tables [doc: https://docs.magnific.com/pricing].
- **Plans** [3rd, renderahouse.com, read 7 Sep 2026]: Premium $16/mo, Premium+ $37/mo, Pro $90/mo (annual billing $11 / $27.50 / $66.92). Yearly credit pools are 240k / 600k / 1.5M. **Precision upscale is about 90 credits per 2K image** [3rd]. Unused monthly credits do not roll over [3rd]. Treat all of these figures as approximate.
- **Stock downloads through the API** [doc]: on Premium, Premium+ and Pro they cost no credits but are capped at **100 downloads/day**. On Business and Enterprise there is no cap, but each download costs credits.
- **Rate limits** (REST) [doc: https://docs.magnific.com/ratelimits]: 50 hits/s per IP over 5 s, a 10 hits/s average over 2 min, and 30,000 requests/min per API key. No per-tool MCP limits are published.
- **Measuring spend [derived].** Call `account_balance` before and after each batch and write the difference into the manifest. This is the only reliable way, because per-tool costs are not machine-readable.

### 1.4 Licensing for commercial client work

The primary pages, `magnific.com/ai/docs/*` and `/legal/*`, **returned HTTP 403 (bot protection)** to both WebFetch and curl. The points below come from search-indexed snippets of those official pages. Verify them against https://www.magnific.com/legal/terms-of-use (including the `#api-services` section) and the license PDF shipped with each download.

**AI-generated output**
- Paid plans include a **commercial license**. The Free plan is personal use only, and some page versions add "with attribution" [3rd/doc-snippet: magnific.com/ai/docs/ai-content-and-copyright].
- One blog says the commercial right depends on having a paid subscription **at generation time**, so upgrading later does not cover earlier free-plan images [3rd, unverified].
- The user is responsible for making sure output does not infringe third-party rights. Magnific cannot guarantee copyright ownership in every jurisdiction.
- AI output is **excluded from standard indemnification**. Enterprise customers may get IP protection under an MSA, which excludes prompts that use trademarks or searchable IP.
- The Merchandise License does not apply to AI output.

**Stock**
- With Premium, Premium+ or Pro: **no attribution required**. With Free or Essential: credit is required (for video, in the credits or description).
- Social media use is allowed, including stock as the main element. Monetized YouTube use is allowed.
- Licenses are perpetual once downloaded. A license PDF comes with each download. Stock is indemnified for paid subscribers [3rd/doc-snippets: usage-rights-general-rules, enterprise-content-and-legal; freepik.com/ai/docs/personal-use].

**Redistribution inside project files**
- The usage rules say **never deliver editable files that contain Magnific/Freepik resources**. Deliver only the final product (render, PNG, PDF).
- Font files may not be redistributed.
- **Consequence for WhyNot Cut [derived]:** client reels (rendered MP4s) are fine. A Premiere or After Effects project folder, a MOGRT, a PSD thumbnail, or a handoff package **that contains Magnific stock or generated files must not be given to the client**. It may stay inside the agency. The handoff skill should strip those files, or list them as "agency-licensed, not transferable".

**Sensitive use**
- No defamatory, obscene or offensive use, and no use that harms the reputation of the people shown.
- People in stock may not be shown as **endorsing** products, services or causes without consent [3rd/doc-snippet]. This matters for doctors' reels: a stock model must not appear to be the patient, or to endorse the doctor.
- The AI guidelines flag violent content, copyrighted characters, sexual content and hate speech. Some models have their own extra restrictions.

### 1.5 Bundling in the WhyNot Cut plugin

Facts [doc: code.claude.com/docs/en/mcp, /plugins-reference, /sub-agents]:
- A plugin declares MCP servers in **`.mcp.json` at the plugin root**, or in `mcpServers` in `.claude-plugin/plugin.json` (inline map, `.json` path, or `.mcpb` bundle). These merge, and a later name replaces an earlier one. `${CLAUDE_PLUGIN_ROOT}` and `${user_config.KEY}` expand in `url` and `headers` for http servers.
- Plugin servers start automatically when the plugin is enabled. They appear in `/mcp` marked as plugin servers and can be toggled off there. The docs **do not describe OAuth specifically for plugin servers**. A remote server answering 401 is marked "needs authentication" and is authorised through `/mcp` like any other.
- **Tool naming for plugin-bundled servers:** `mcp__plugin_<plugin>_<server>__<tool>`, which here is **`mcp__plugin_whynot-cut_magnific__images_upscale`**. A hook matcher written as `mcp__magnific__.*` **never fires** for the plugin-bundled copy.
- **Dedupe:** "Claude Code matches plugins and connectors **by endpoint**". When a plugin server points at the same URL as a local, project or user server, it counts as a duplicate. **The higher-precedence definition wins**: local > project > user > plugin > claude.ai connector. **On this machine the user-scope `magnific` entry wins, so the tools are named `mcp__magnific__*`, not `mcp__plugin_whynot-cut_magnific__*`.** A claude.ai connector-only setup would use another prefix again. That prefix is probably `mcp__claude_ai_Magnific__*` [derived, unverified].
- **Agents:** `tools:` and `disallowedTools:` accept exact names and server-level patterns `mcp__<server>` or `mcp__<server>__*`. If **no** entry resolves, the agent fails to launch, but extra unresolved entries are tolerated. **Plugin agents ignore `mcpServers`, `hooks` and `permissionMode` frontmatter.** Background subagents keep every MCP tool, and their permission prompts surface in the main session.
- `claude plugin validate` checks plugin MCP entries (Claude Code v2.1.281+).
- Per-server `"timeout"` in ms overrides `MCP_TOOL_TIMEOUT`, which matters for `creations_wait` on video.

**Recommended snippet [derived]:** `whynot-cut/.mcp.json`

```json
{
  "mcpServers": {
    "magnific": {
      "type": "http",
      "url": "https://mcp.magnific.com",
      "timeout": 600000
    }
  }
}
```

Equivalent inline form in `plugin.json`: `"mcpServers": { "magnific": { "type": "http", "url": "https://mcp.magnific.com", "timeout": 600000 } }`. Leave `alwaysLoad` unset so the roughly 40 tools stay deferred behind tool search.

**Agent frontmatter.** Cover all prefixes, and keep spending tools out of agents that must not spend:

```yaml
# asset-scout (new agent) — read + spend, behind the approval gate
tools: Read, Write, Bash, Grep, mcp__magnific, mcp__plugin_whynot-cut_magnific
# every other agent — no Magnific at all
disallowedTools: mcp__magnific, mcp__plugin_whynot-cut_magnific
```

**Spend guard hook** (plugin `hooks/hooks.json`, PreToolUse) [derived]:
- Matcher: `^mcp__(plugin_whynot-cut_)?magnific__(images_generate|images_generate_svg|images_to_svg|images_upscale|images_remove_background|images_crop|video_generate|audio_tts|models3d_generate|custom_references_create|creations_upload|creations_request_upload|folders_delete)$`, plus the same names with the claude.ai prefix.
- Action: a script that checks `data/.../magnific-approvals.json` for an approved line item matching this call. If there is one, `allow` and log it. Otherwise return `permissionDecision: "ask"`. For `custom_references_create` on a person, or `folders_delete`, return `deny`.
- Read-only tools (`account_balance`, `creations_search`, `creations_get`, `*_list`, `*_show`, `creation_status`, `creations_wait`) can be allow-listed.

**Setup and degradation [derived]:**
- Add a "Magnific (optional)" step to `/whynot-cut:setup` and `/whynot-cut:start`: "run `/mcp` → magnific → Authenticate". `setup-doctor` reports the state: authorised, not authorised, or absent.
- If the tools are missing, the pipeline must continue and list the missing material in the handoff. It must never block on Magnific.
- Decide whether to bundle at all. Bundling makes every editor see an unauthenticated "magnific" in `/mcp`. Not bundling relies on per-machine setup. **Recommendation: bundle it** (dedupe makes it harmless where it is already configured), with the guards above.

### 1.6 How a video-editing assistant should use it, with rules

The owner's requirement is "only when it needs material, and it must be related to the content". **Proposed usage map [derived]:**

| Need (pipeline stage) | Tool | Notes |
|---|---|---|
| Client logo or photo too small or blurry for 1080×1920 or a 4K comp (client-researcher, motion-designer) | `images_upscale` | Highest value and lowest risk. Use precision-style, low-creativity settings. **Never on faces**, because creative upscaling invents facial detail. |
| Client logo needed as vectors for AE motion mode | `images_to_svg` | Check the paths visually against the original. Keep the original as the master. |
| Cut-out of a client product or object for a scene | `images_remove_background` | Client-supplied images only, with client consent. Not people's faces unless the client profile explicitly allows cut-outs of the client's own portrait. |
| Icons and illustrations for motion-mode scenes (counters, steps, timelines) | `images_generate_svg` | Prompt from the scene's concept word, in the brand palette. **No text inside the icon**, because generated Arabic lettering is unreliable. All text comes from our own caption and graphics engine. |
| Thumbnail backgrounds (publish-writer) | `images_generate` | Abstract or scene backgrounds only. No people and no text. The client's own photo stays the hero. |
| Concept B-roll stills for a topic the speaker names ("blood sugar", "sleep", "Ramadan fasting") | `images_generate`, or REST stock | Must pass the relevance and sensitivity checks below. Prefer stock (REST) for realism. Medical illustrations need medical-reviewer sign-off. |
| Short abstract or background loops for motion scenes | `video_generate` | Expensive. Off by default. Explicit per-clip approval only. |
| SFX (whooshes, pops) | **none**; keep the local synthesis already in motion-designer | Magnific SFX and music are REST only. |
| Voice | **no `audio_tts` on client content** | Never imitate a client's voice. Allowed only for internal scratch or guide VO. |
| Reuse | `creations_search` / `creations_get` | Always check before generating anything new. |

**Rules for a skill or policy file [derived]:**

1. **Need first, then the cheapest source.** Order: client `assets/` → client database → previous Magnific creations (`creations_search`) and the local cache → stock (REST, if enabled) → generation. A Magnific call is allowed only for an `asset_need` written by story-editor or motion-designer in the plan.
2. **Relevance check.** Each `asset_need` must cite the transcript segment id, timecode and exact phrase, plus the topic from the topic map. The prompt or search term is derived from that phrase. A second agent (story-editor or graphic-checker) scores relevance 0–2, and only a 2 proceeds. No decorative filler, no generic "business people" shots, and nothing that contradicts or exaggerates what the speaker says.
3. **Brand fit.** Inject the client reel-profile palette and mood into prompts. Use stock `filters[color]` where possible. After download, check the dominant colours against the palette (ΔE threshold). Reject images that contain logos, watermarks, text, competitor brands or off-brand styles.
4. **Medical and religious sensitivity.** Every Magnific asset on a health or religious clip goes through the existing medical-reviewer or claim-checker before it is placed. Medical: no clinical or anatomical imagery that could mislead, no before/after shots, no identifiable patients, no implied endorsement by stock people, no pills or doses that the speaker didn't name. Religious: no AI-generated Quran or hadith calligraphy, no depictions of prophets or companions, no invented mosque inscriptions. Respect regional modesty norms (clothing, alcohol, pork, gambling, mixed-gender intimacy) according to the client profile.
5. **People and faces.** Never generate, upscale-enhance, alter or animate the face or likeness of a real, identifiable person. No `custom_references_create` (Soul character) on real people, and no talking-head or avatar generation. Generic generated people are allowed only if the profile allows it. Stock people searches should default to `filters[people]=exclude`.
6. **Spend cap.** Default auto-spend is **0**. The per-reel budget is a userConfig value, for example `magnific_max_credits_per_reel` defaulting to 300 credits, with `video_generate` blocked unless the editor says "allow video". Record `account_balance` before and after each batch. Stop and report if the budget would be exceeded or the balance falls below a floor.
7. **Editor approval before spend, once per reel.** This is batched, not per asset, to fit the owner's "decide and continue" preference. The approval table lists asset, purpose, transcript anchor, tool and model, estimated credits and licence type. The PreToolUse hook enforces it.
8. **License manifest for every asset.** Write to `data/<clip>/magnific-manifest.json` with these fields:
   - Identity: `asset_id`, `local_path`, `sha256`, `source` (`mcp-creation` or `stock-rest`), `creation_id` or `stock_id`
   - Generation: `tool`, `model`, `prompt`, `reference_inputs`
   - Cost and plan: `credits_before` / `credits_after`, `plan_at_generation`, `created_at`
   - Licence: `license_type` (`ai-generated-paid` or `stock-premium`), `license_url` or the PDF path, `attribution_required` and `attribution_text`
   - Use and review: `used_in` (reel id plus timecodes), `relevance_anchor`, `sensitivity_review`, `approved_by`, `transferable_to_client: false`
9. **Cache and dedupe.** Key = hash(tool + model + normalised prompt + inputs). Keep a per-client cache under the client `data/` folder (client sources stay read-only under the existing hooks). Keep a shared, non-client-specific cache, for icons and abstract backgrounds, in `${CLAUDE_PLUGIN_DATA}/magnific-cache/`. Record the cache hit in the manifest.
10. **Privacy on upload.** `creations_upload` sends files to Magnific's servers. Upload only client brand assets the client has approved for third-party processing. Never upload raw footage, patient data or unreleased episodes.
11. **Handoff.** Renders only. The handoff skill lists Magnific assets as agency-licensed and excludes them from any editable package that leaves the agency.
12. **Graceful absence.** If Magnific is not authorised or the tools are missing, continue the pipeline and list "material not sourced" with the needs and anchors, so the editor can source it by hand.

---

## PART 2: The Why Not AI brand (https://thewhynot.ai/)

**Method.** I downloaded the raw HTML of the home page and 11 inner pages with curl. There was no blocking. The site is built on **Framer**: the page head carries `<meta name="generator" content="Framer 65a4904">`, assets are served from `framerusercontent.com`, and the CSS is inline. I parsed CSS tokens, `@font-face` rules, Framer font selectors (base64-encoded `GF;Syne-600`, etc.) and inline SVGs. I rendered the logo with headless Chrome and viewed the PNG assets.

The sitemap lists: `/`, `/about`, `/packages`, `/starter-package`, `/growth-package`, `/scale-package`, `/personal-brand-strategy`, `/media-production`, `/online-courses-management`, `/linkedin-ghostwriting`, `/content-system`, `/ai-training-workshops`, `/success-stories`, `/el-modeeer`, `/el-khabeer-maa-el-modeeer`, `/dr-sherif-khaled`, `/dr-sherine-helmy`, `/contact`, `/privacy-policy`, `/terms-of-service`. There is **no brand, press or media-kit page**.

### 2.1 Logo

- **Main logo: inline SVG only. There is no standalone file URL.** In the nav and footer it is `<svg viewBox="0 0 109 32">` using `<use href="#svg-166424251_49236">`.
  - **Composition:** a **"TWN" monogram** set in a tilted, outlined frame or speech bubble with a small tail. Inside the frame is a **fingerprint-heart icon** labelled "AI" within viewfinder corner brackets. Next to it is a **wordmark "THE / WHY NOT"** in heavy, blocky, slightly irregular display capitals.
  - **Colours:** white wordmark and frame (17 `fill="white"` paths). Icon gradients run **#D95C9B → #390796** (47 linear gradients). There is one **#7C0505** detail.
  - It is a **white-on-dark logo. No dark or mono version is published.**
  - Local copies made for reference: `scratchpad/twn-dl/logo.svg` (extracted symbol) and `scratchpad/twn-dl/logo.png` (render on black).
- **Wordmark text:** "THE WHY NOT". The brand name in copy is "The Why Not AI (TWN)".
- **Favicon:** https://framerusercontent.com/images/67epArCOrh4mKe6bXS5yz5OCyh8.png (64×64 PNG, the same file for light and dark). The stacked "THE WHY NOT" lockup sits in its frame on a gradient tile.
- **Apple touch icon:** https://framerusercontent.com/images/o3lvRLmLuszUmu8NvgPeuldonDg.png (180×180). The tile gradient runs from dark navy/indigo (top-left) through violet to pink (bottom-right).
- **OpenGraph/Twitter image:** https://framerusercontent.com/images/TDZXxrksuO13AAlXvJAI4hh9I.png (1200×630). It has a black background with a violet planet-arc glow and a faint grid. The headline is in wide caps, with "THE WHY NOT" and "UNDERSTAND AND TRUST." in a pink→violet gradient and the rest in white. The body text is in Inter.
- **Not available:** `/favicon.ico` (404), `/manifest.json` (404), `/site.webmanifest` (404). There is no Arabic logo.

### 2.2 Colour palette (from CSS tokens and usage counts on the home page)

| Role | HEX | Evidence |
|---|---|---|
| Primary: Electric Violet | **#5400FB** (also written `rgb(83,0,251)`) | Framer token `--token-a7021740…`; highlighted words in headings; gradient end |
| Accent: Orchid Pink | **#D95C9B** | Token `--token-5c5006e0…`; ~113 uses; section eyebrow labels ("The TWN Method", "Trusted By"), "Learn More" links, gradient start, logo gradient |
| Deep Violet | **#390796** | Logo gradient stop |
| Indigo shades | **#1C0E47**, **#3C19A5**, **#4422A9**, #4800D8 (about page) | Decorative SVG gradient stops; one `background-color:#3c19a5` block |
| Background | **#000000** | `html body { background: rgb(0,0,0) }` |
| Card / surface | **#121212** | Token `--token-b2d0d162…` |
| Glass surface | `rgba(255,255,255,0.08)`; gradient `#ffffff03 → #ffffff1a` | Token `--token-66cf77ff…`; cards and buttons |
| Text | **#FFFFFF**; body `rgba(255,255,255,0.8)` | Token `--token-f597b2ac…` / `--token-262ecc22…` |
| Borders | `rgba(255,255,255,0.5)` on the nav pill (40 px radius, 5 px backdrop blur); `0.3` / `0.25` elsewhere | Nav |
| Brand gradient | `linear-gradient(270deg, #5300FB 0%, #D95C9B 100%)` and `linear-gradient(90deg, #D95C9B, #5400FB)` | Buttons and highlights |
| Not brand | #0099FF | Framer's default link colour |
| Logo-only detail | #7C0505 | One path in the logo |

**Contrast (WCAG) [computed]:**
- #5400FB on black is **2.77:1, which fails even for large text**. The site uses it for highlighted heading words.
- #D95C9B on black is 5.95:1 (passes).
- White on #5400FB is 7.58:1, and white on #390796 is 12.77:1 (both pass).
- White on #D95C9B is 3.53:1 (large text only).
- #D95C9B on white is 3.53:1 (large text only).

### 2.3 Fonts

- **Syne** (Google Fonts, **OFL-1.1**, by Bonjour Monde) is used for **all headings, nav, labels and buttons**. It is the dominant font on every page. Weights in use: 500 (143 uses), 600 (244), **700 (505)**; Framer selectors `GF;Syne-500/600/700`. Sizes: 14 px labels, 20, 24, 32 px section titles, 40, 48, and 64 px hero.
- **Inter** (OFL) is used for **body copy**: mostly **Light 300** (744 uses), with SemiBold 600, Medium 500 and ExtraBold accents.
- **No Arabic font is loaded.** Arabic glyphs fall back to the visitor's system font.

### 2.4 Taglines and copy

The brand's own lines from its site:
- Hero: "Monetize Your Presence", "Personal Branding That Sounds Like You.", "Understand and Trust."
- Footer slogan: **"Clarity first. Consistency follows."**
- Section lines: "The TWN Method"; "From guessing what to post to being known for what you do"; "Built for Real Work, Not Noise"; "About Clarity, Not Hype"; "Built for Leaders Across Egypt, Saudi Arabia, and the UAE"; "Ready to Stop Guessing and Start Being Known?"
- A "Why Not" series: "Why Not Begin? / Why Not Grow? / Why Not Stand Out? / Why Not Now?"
- About page: "A Boutique, Strategy-Led Personal Branding Agency"; "No handoffs. No templates. Just experienced people doing focused work."
- Meta and OG description: a strategy-led personal branding agency for founders, executives and experts in Egypt, KSA and the UAE. Its stance on AI: "using AI where it helps, and human judgment where it matters".

**Tone of voice:** confident, direct and calm. Short declarative sentences and fragments, anti-hype, centred on clarity and credibility. Senior and boutique rather than playful, with light wordplay in the "Why Not …?" series. Its line on AI: AI assists, and humans decide and protect the client's voice.

### 2.5 Arabic content, social links, other

- **Arabic:** the site is English-only (`<html lang="en">`, no `dir="rtl"`). Arabic appears only as client show titles on case-study pages: "حديث العقل والروح", "سلسلة رمضان", "همسات تربوية" and "وتزودوا بالتقوى" on `/dr-sherine-helmy`; "المدير" and "الشباب" on `/el-khabeer-maa-el-modeeer`.
- **Social and contact:**
  - Facebook: https://www.facebook.com/TheWhyNotAI
  - Instagram: https://www.instagram.com/thewhynot.ai/
  - LinkedIn: https://www.linkedin.com/company/thewhynot-ai/
  - Email: mailto:info@thewhynot.ai
  - Booking via WhatsApp: https://wa.link/eywgzn
  - No YouTube, TikTok or X link was found.
  - Partner: https://elmodeeer.com/ ("An Exclusive Strategic Investor").
- **Site issues spotted, for the owner:**
  1. Every FAQ answer ends with the template credit link `https://framer.link/isaacdsign`, a leftover from the Framer template.
  2. The violet-on-black heading highlights fail contrast (2.77:1).
  3. There is no `favicon.ico` or web manifest.

### 2.6 Suggested brand kit [derived]

#### (a) Premiere Pro / After Effects panel UI (WhyNot Cut Bridge, CEP/UXP)

Adobe panels sit on the host's dark grey, around #232323 by default. Read `appSkinInfo.panelBackgroundColor` (CEP) or the UXP theme, and keep the brand to accents so the panel does not look like a foreign app.

```css
:root {
  /* surfaces (fallbacks when host colour unavailable) */
  --twn-bg:            #161616;   /* or host panel bg */
  --twn-surface:       #1F1F1F;   /* ≈ #121212 + 8% white glass */
  --twn-surface-2:     #2A2A2A;
  --twn-border:        rgba(255,255,255,.14);
  /* text */
  --twn-text:          #FFFFFF;
  --twn-text-muted:    #B3B3B3;   /* ≈ site's white 80% on dark */
  /* brand */
  --twn-primary:       #5400FB;   /* button fill, white label = 7.6:1 */
  --twn-primary-hover: #6A1FFF;
  --twn-primary-text:  #9D6BFF;   /* violet for TEXT/links on dark = 6.0:1 (raw #5400FB fails) */
  --twn-accent:        #D95C9B;   /* eyebrow labels, active tab underline = 5.3:1 on #121212 */
  --twn-deep:          #390796;   /* selected row / badges, white text 12.8:1 */
  --twn-gradient:      linear-gradient(90deg, #D95C9B 0%, #5400FB 100%); /* header hairline, progress bar only */
  --twn-focus:         0 0 0 2px #9D6BFF;
  /* status */
  --twn-ok:            #3DD68C;
  --twn-warn:          #FFB020;
  --twn-error:         #FF5C5C;
  /* type */
  --twn-font-display:  "Syne", "Inter", sans-serif;            /* panel title / wordmark only, 600–700 */
  --twn-font-ui:       "Inter", system-ui, sans-serif;         /* 11–12 px UI, 400/600 */
  --twn-font-ar:       "IBM Plex Sans Arabic", "Noto Sans Arabic", sans-serif;
  --twn-radius:        8px;  /* pills 999px echo the site's 40px nav pill */
}
```

- **Header:** the 24 px favicon monogram, then "WhyNot Cut" in Syne 600 at 13–14 px, then a 2 px `--twn-gradient` hairline underneath.
- **Primary button:** violet fill with white Inter 600. **Secondary button:** glass `--twn-surface` with a `--twn-border` outline.
- **Section labels:** Syne 600, 10–11 px, uppercase, `--twn-accent`. This echoes the site's pink eyebrow labels.
- **Arabic UI strings:** wrap in `dir="rtl" lang="ar"` using `--twn-font-ar`. Isolate commands and timecodes with `<bdi dir="ltr">`.
- **Bundle these fonts** (all OFL): Syne, Inter, IBM Plex Sans Arabic. Include each OFL text in `THIRD_PARTY_NOTICES.md`.

#### (b) Arabic RTL PDF user guide

- **Font pairing** (all OFL, all on Google Fonts):
  - **Arabic headings: Alexandria** (variable, Thin–Black). Its wide geometric shapes are the closest Arabic match to Syne's wide display, and it was co-designed by Egyptian designer Mohamed Gaber. **Alternative: Cairo** ExtraBold/Black.
  - **Arabic body: IBM Plex Sans Arabic** Regular or Light at 11–12 pt, line-height 1.7. It pairs naturally with Inter, which has a similar grotesque rhythm. **Alternative for a softer on-screen read: Tajawal** Regular/Medium.
  - **Latin inside Arabic text:** Inter for running text; Syne 700 only for English brand words or English headings.
  - **Commands and paths:** IBM Plex Mono, always set as LTR-isolated runs, for example `/whynot-cut:edit` or `D:\WhyNot Clients`.
- **Palette on white pages** (print-safe, body text passes AA):

| Use | HEX | Contrast on white |
|---|---|---|
| Headings / table headers | **#1C0E47** (Midnight Indigo) | 17.5:1 |
| Primary accent text, links, step numbers | **#5400FB** | 7.6:1 |
| Secondary accent text (warnings, "important") | **#B23A78** (darkened Orchid) | 5.6:1 |
| Decorative bars, large display ≥24 pt, icons | **#D95C9B** | 3.5:1 (decorative or large only) |
| Deep violet panels (white text) | **#390796** | white 12.8:1 |
| Tip callout background / rule | **#F1EAFF** / #5400FB rule on the **right** edge (RTL) | — |
| Warning callout background / rule | **#FCEAF3** / #B23A78 | — |
| Body text / muted | **#1A1A1A** / **#5C5C66** | — |
| Paper | **#FFFFFF** (or #FAFAFC) | — |

- **Cover and section dividers:** #000000 or #1C0E47 background with the site's violet glow and the `#D95C9B → #5400FB` gradient. White logo, title in Alexandria Black, subtitle in IBM Plex Sans Arabic Light.
- **Logo on white pages:** needs a **dark variant** that does not exist yet. Swap the white fills for #1C0E47 and keep the gradient icon. The owner should approve it before use.
- **RTL details:**
  - Mirror layouts: callout rules and bullets on the right, and page numbers in the outer corner of an RTL spread.
  - Keep Western digits (0–9) for timecodes, versions and commands. Arabic-Indic digits are allowed in prose if the editor prefers.
  - Never let commands, file paths or English UI labels break bidi: wrap them as isolated LTR runs.
- **Rendering:** use an engine with HarfBuzz shaping and proper bidi, such as headless Chrome print or WeasyPrint. Do not use plain ReportLab, which lacks shaping. Embed and subset the fonts.

---

## Sources

**Magnific**
- https://docs.magnific.com/modelcontextprotocol (and `.md`): MCP endpoint, OAuth, client setup, tool list, credits FAQ
- https://docs.magnific.com/llms.txt: API index (stock, SFX, music, upscaler variants, relight, webhooks)
- https://docs.magnific.com/pricing, https://docs.magnific.com/ratelimits, https://docs.magnific.com/webhooks
- https://docs.magnific.com/api-reference/videos/get-all-videos-by-order, …/resources/get-all-resources, …/icons/icons-api, …/sound-effects/post-sound-effects (OpenAPI excerpts)
- https://mcp.magnific.com/.well-known/oauth-protected-resource and …/oauth-authorization-server [live]
- Licensing (official pages, 403 to fetch; read via search snippets): https://www.magnific.com/ai/docs/ai-content-and-copyright, https://www.magnific.com/ai/docs/usage-rights-general-rules, https://www.magnific.com/ai/docs/enterprise-content-and-legal, https://www.magnific.com/ai/docs/legal-and-compliance, https://www.magnific.com/legal/terms-of-use#api-services, https://www.freepik.com/ai/docs/personal-use, https://cn.freepik.com/ai/docs/licenses-attribution
- Rebrand and pricing [3rd]: https://www.relevantaudience.com/ai/magnific-how-freepik-rebrand-changes-creative-work/, https://www.media-marketing.com/en/news/magnific-is-no-longer-selling-ai-tools-but-trying-to-redefine-how-creative-work-gets-made/, https://raxxo.shop/blogs/lab/freepik-just-rebranded-as-magnific-what-changes-for-solo-creators, https://www.renderahouse.com/blog/magnific-ai-pricing, https://www.myarchitectai.com/blog/magnific-ai-pricing

**Claude Code**
- https://code.claude.com/docs/en/mcp: HTTP servers, OAuth via `/mcp`, plugin-provided servers, tool naming `mcp__plugin_<plugin>_<server>__<tool>`, endpoint dedupe and precedence, connectors, timeouts, tool search
- https://code.claude.com/docs/en/plugins-reference: `mcpServers` shapes, `.mcp.json`, variables, userConfig, validate
- https://code.claude.com/docs/en/sub-agents: `tools`/`disallowedTools` server-level patterns; plugin agents ignore `mcpServers`, `hooks` and `permissionMode`

**Brand**
- https://thewhynot.ai/ and the inner pages in https://thewhynot.ai/sitemap.xml (raw HTML, CSS tokens, inline SVG)
- Favicon, touch icon and OG image URLs as listed in §2.1
- Fonts: https://fontsource.org/fonts/syne/about, https://fontsource.org/fonts/alexandria/about; IBM Plex Sans Arabic, Cairo and Tajawal on Google Fonts (OFL)
