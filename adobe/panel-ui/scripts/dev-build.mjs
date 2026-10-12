// npm run dev:build -> panel-ui/dev/out/{index.html,dev.js,fonts.css,fonts/,tokens.css,panel.css} (gitignored). Open dev/out/index.html.
import { build } from "esbuild";
import { copyFileSync, cpSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "dev", "out");
mkdirSync(out, { recursive: true });

await build({
  entryPoints: [join(root, "dev", "dev.ts")],
  outfile: join(out, "dev.js"),
  bundle: true,
  format: "iife",
  target: "es2022",
  sourcemap: true,
  logLevel: "info",
});
copyFileSync(join(root, "dev", "index.html"), join(out, "index.html"));
// the brand kit, as the plugin bundles it: brand/tokens.css (the one token source), fonts.css next to fonts/
copyFileSync(join(root, "..", "..", "brand", "tokens.css"), join(out, "tokens.css"));
copyFileSync(join(root, "styles", "fonts.css"), join(out, "fonts.css"));
cpSync(join(root, "fonts"), join(out, "fonts"), { recursive: true });
copyFileSync(join(root, "styles", "panel.css"), join(out, "panel.css"));
console.log(`dev harness: ${join(out, "index.html")}`);
