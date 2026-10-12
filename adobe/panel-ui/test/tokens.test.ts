// B-T1 token test: brand/tokens.css is the ONE source of the brand values (Addendum B, verbatim), and every colour the
// panel kit paints comes from it (no colour literal in panel CSS, and any literal in panel TS is a token value).
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { ADOBE, PANEL_UI, REPO, TOKENS, canon, coloursIn, tokenMap, walk } from "./tokens-util.ts";

const read = (p: string) => readFileSync(p, "utf8");
const PANEL_CSS_FILES = () => [...walk(join(PANEL_UI, "styles"), (p) => p.endsWith(".css")), join(ADOBE, "premiere-uxp", "plugin", "index.css")];

test("brand/tokens.css carries every Addendum B value verbatim", () => {
  assert.ok(existsSync(TOKENS), "brand/tokens.css is the single token source");
  const css = read(TOKENS);
  const t = tokenMap(css);
  const want: Record<string, string> = {
    "--twn-bg": "#000000",
    "--twn-surface": "#121212",
    "--twn-glass": "rgba(255,255,255,.08)",
    "--twn-border": "rgba(255,255,255,.14)",
    "--twn-radius-card": "16px",
    "--twn-radius-pill": "999px",
    "--twn-primary": "#5400FB",
    "--twn-primary-text": "#9D6BFF",
    "--twn-accent": "#D95C9B",
    "--twn-deep": "#390796",
    "--twn-gradient": "linear-gradient(90deg,#D95C9B,#5400FB)",
    "--twn-ok": "#3DD68C",
    "--twn-warn": "#FFB020",
    "--twn-error": "#FF5C5C",
    "--twn-focus": "0 0 0 2px #9D6BFF",
    "--twn-on-primary": "#FFFFFF",
  };
  for (const [k, v] of Object.entries(want)) assert.equal(t.get(k), v, `${k} must be ${v} (Addendum B)`);
  // the type: Syne / Inter / IBM Plex Sans Arabic / IBM Plex Mono first in their stacks, each ending in a generic family
  // (so the panel degrades to the stack when a host ignores @font-face)
  const stacks: Record<string, [string, string]> = {
    "--twn-font-display": ['"Syne"', "sans-serif"],
    "--twn-font-ui": ['"Inter"', "sans-serif"],
    "--twn-font-ar": ['"IBM Plex Sans Arabic"', "sans-serif"],
    "--twn-font-mono": ['"IBM Plex Mono"', "monospace"],
  };
  for (const [k, [first, generic]] of Object.entries(stacks)) {
    const v = t.get(k) ?? "";
    assert.ok(v.startsWith(first), `${k} starts with ${first}: ${v}`);
    assert.ok(v.endsWith(generic), `${k} ends with ${generic}: ${v}`);
  }
  assert.match(t.get("--twn-font-mono") ?? "", /Consolas/, "the old mono stack stays as the fallback");
  for (const [k, v] of [["--twn-weight-light", "300"], ["--twn-weight-regular", "400"], ["--twn-weight-semibold", "600"], ["--twn-weight-bold", "700"]] as const) {
    assert.equal(t.get(k), v, k);
  }
  // the 2.77:1 trap: raw #5400FB is a fill token only, never the text token
  assert.notEqual(t.get("--twn-primary-text"), t.get("--twn-primary"));
  // always dark: no light-theme switch in the token source
  assert.doesNotMatch(css.replace(/\/\*[\s\S]*?\*\//g, ""), /prefers-color-scheme|\[data-theme/);
  // the token file only defines tokens (no @font-face, no @import, no url(): it is copied as-is into every bundle)
  assert.doesNotMatch(css.replace(/\/\*[\s\S]*?\*\//g, ""), /@font-face|@import|url\(/);
});

test("one source: no other tokens.css in the Adobe sources; the builds copy brand/tokens.css", () => {
  assert.ok(!existsSync(join(PANEL_UI, "styles", "tokens.css")), "panel-ui/styles/tokens.css must not exist (copied from brand/ at build time)");
  const copies = walk(ADOBE, (p) => p.endsWith("tokens.css")).map((p) => relative(REPO, p));
  assert.deepEqual(copies, [], `stray token files: ${copies.join(", ")}`);
  assert.match(read(join(ADOBE, "premiere-uxp", "scripts", "build.mjs")), /brand\/tokens\.css/);
  assert.match(read(join(PANEL_UI, "scripts", "dev-build.mjs")), /"brand", "tokens\.css"/);
});

/** CSS that still defines --twn-* tokens of its own, with the reason it may for now. Nothing else under adobe/ may. */
const TOKEN_DEFINITION_ALLOWED: Record<string, string> = {
  "adobe/premiere-uxp/spike/index.css": "the spike's own drift block; replaced in Task 3 (the style guide links brand/tokens.css)",
};

test("one source: no CSS under adobe/ defines a --twn-* token except the copied brand/tokens.css (spike drift block allow-listed until Task 3)", () => {
  const offenders: string[] = [];
  for (const f of walk(ADOBE, (p) => p.endsWith(".css"))) {
    const rel = relative(REPO, f).replace(/\\/g, "/");
    if (rel in TOKEN_DEFINITION_ALLOWED) continue;
    const css = read(f).replace(/\/\*[\s\S]*?\*\//g, "");
    const defs = [...css.matchAll(/(--twn-[a-z0-9-]+)\s*:/g)].map((m) => m[1]);
    if (defs.length) offenders.push(`${rel}: ${defs.join(", ")}`);
  }
  assert.deepEqual(offenders, []);
  // the allow-list stays honest: each entry exists and really defines tokens
  for (const rel of Object.keys(TOKEN_DEFINITION_ALLOWED)) {
    assert.match(read(join(REPO, rel)), /--twn-[a-z0-9-]+\s*:/, `${rel} no longer defines tokens: drop it from the allow-list`);
  }
});

test("every var(--twn-*) the kit uses is defined in brand/tokens.css", () => {
  const defined = tokenMap(read(TOKENS));
  for (const f of PANEL_CSS_FILES()) {
    for (const m of read(f).matchAll(/var\((--twn-[a-z0-9-]+)\)/g)) assert.ok(defined.has(m[1]!), `${relative(REPO, f)} uses undefined ${m[1]}`);
  }
  for (const [k, v] of defined) for (const m of v.matchAll(/var\((--twn-[a-z0-9-]+)\)/g)) assert.ok(defined.has(m[1]!), `${k} -> ${m[1]}`);
});

test("panel CSS has no colour literals: every colour is a var(--twn-*) token", () => {
  const files = PANEL_CSS_FILES();
  assert.ok(files.some((f) => f.endsWith("panel.css")));
  assert.ok(files.some((f) => f.endsWith("kit.css")), "the component kit's CSS is checked too");
  for (const f of files) {
    const css = read(f).replace(/\/\*[\s\S]*?\*\//g, "");
    assert.deepEqual(coloursIn(css), [], `${relative(REPO, f)} has colour literals; use the tokens`);
    assert.doesNotMatch(css, /:\s*(?:white|black)\s*[;}]/, `${relative(REPO, f)} uses a named colour`);
  }
});

test("every colour literal in panel-ui TS is a brand/tokens.css value", () => {
  const values = new Set<string>();
  for (const v of tokenMap(read(TOKENS)).values()) for (const c of coloursIn(v)) values.add(canon(c));
  const files = [...walk(join(PANEL_UI, "src"), (p) => p.endsWith(".ts")), ...walk(join(PANEL_UI, "dev"), (p) => p.endsWith(".ts"))];
  assert.ok(files.length > 5);
  const strays: string[] = [];
  for (const f of files) {
    // a base64 data URI (the monogram) is image bytes, not a colour
    const src = read(f).replace(/data:image\/png;base64,[A-Za-z0-9+/=]+/g, "");
    for (const c of coloursIn(src)) if (!values.has(canon(c))) strays.push(`${relative(REPO, f)}: ${c}`);
  }
  assert.deepEqual(strays, []);
});
