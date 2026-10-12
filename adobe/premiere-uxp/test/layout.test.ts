// Product code never reaches into the spike: what the plugin needs from it lives under src/.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));

test("no file under src/ imports from the spike folder (the UXP typings live in src/uxp-types.ts)", () => {
  assert.ok(existsSync(join(root, "src", "uxp-types.ts")), "src/uxp-types.ts is missing");
  assert.equal(existsSync(join(root, "spike", "src", "uxp-types.ts")), false, "the typings must not stay in the spike folder too");
  for (const f of readdirSync(join(root, "src")).filter((n) => n.endsWith(".ts"))) {
    const text = readFileSync(join(root, "src", f), "utf8");
    assert.ok(!/from\s+["'][^"']*spike\//.test(text), `src/${f} imports from the spike`);
  }
});

test("the spike imports the UXP typings from src/", () => {
  for (const f of ["fsutil.ts", "probes.ts", "spike.ts"]) {
    const text = readFileSync(join(root, "spike", "src", f), "utf8");
    assert.match(text, /from\s+["']\.\.\/\.\.\/src\/uxp-types\.ts["']/, f);
    assert.doesNotMatch(text, /from\s+["']\.\/uxp-types\.ts["']/, f);
  }
});
