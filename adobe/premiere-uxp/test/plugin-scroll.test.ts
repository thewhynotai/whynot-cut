// The plugin's own page must not fight the panel's scroll region (UXP does not scroll the document).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const css = readFileSync(fileURLToPath(new URL("../plugin/index.css", import.meta.url)), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const block = (selector: string) => {
  const flat = css.replace(/\s+/g, " ");
  const want = selector.split(",").map((x) => x.trim());
  let from = 0;
  for (;;) {
    const open = flat.indexOf("{", from);
    assert.ok(open >= 0, `no rule for ${selector}`);
    const head = flat.slice(flat.lastIndexOf("}", open) + 1, open).split(",").map((x) => x.trim());
    if (head.join("|") === want.join("|")) return flat.slice(open + 1, flat.indexOf("}", open));
    from = open + 1;
  }
};

test("html/body are exactly the viewport and never scroll; #root is a full-height flex column", () => {
  const hb = block("html, body");
  assert.match(hb, /height: 100%/);
  assert.match(hb, /overflow: hidden/);
  assert.ok(!/min-height/.test(hb), "min-height lets the page grow instead of the panel scrolling");
  const root = block("#root");
  assert.match(root, /height: 100%/);
  assert.match(root, /display: flex/);
  assert.match(root, /flex-direction: column/);
  assert.ok(!/min-height: 100%/.test(root));
});
