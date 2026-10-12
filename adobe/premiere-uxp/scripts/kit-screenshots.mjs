// Chromium evidence for the B-T1 style guide: the panel kit gallery (panel-ui dev harness, ?scenario=kit) in EN and AR
// at 280 / 340 / 480 px, as full-length PNGs, for comparison with the live Premiere screenshots of spike 0.1.6.
//   node scripts/kit-screenshots.mjs [--url http://127.0.0.1:8766/] [--out <repo>/docs/adobe/evidence/ui-kit] [--browser <chrome.exe>]
// Needs the harness served (npm run dev:build -w panel-ui, then any static server on adobe/panel-ui/dev/out) and an
// installed Chrome or Edge; it drives the browser headless over the DevTools protocol with Node's built-in WebSocket
// (no extra dependency). The column is captured at its full height: the frame's fixed 640 px height and the kit's own
// scroll region are lifted for the capture only, so every component is in the picture.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { root } from "./build.mjs";

const repo = join(root, "..", "..");
const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
};
const BASE = arg("--url", "http://127.0.0.1:8766/");
const OUT = arg("--out", join(repo, "docs", "adobe", "evidence", "ui-kit"));
const BROWSERS = [
  arg("--browser", ""),
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter((p) => p && existsSync(p));
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

if (!BROWSERS.length) {
  console.error("no Chrome / Edge found (pass --browser <path>)");
  process.exit(1);
}

const profile = mkdtempSync(join(tmpdir(), "wnc-kit-shots-"));
const browser = spawn(BROWSERS[0], ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--hide-scrollbars", "--force-device-scale-factor=1", "about:blank"], { stdio: "ignore" });

async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {
      // not up yet
    }
    await sleep(200);
  }
  throw new Error("the browser's DevTools endpoint did not come up");
}

function cdp(url) {
  const ws = new WebSocket(url);
  let id = 0;
  const pending = new Map();
  const events = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message));
      else resolve(msg.result);
    } else if (msg.method) events.push(msg);
  };
  const ready = new Promise((r) => (ws.onopen = r));
  return {
    ready,
    send: (method, params = {}) =>
      new Promise((resolve, reject) => {
        const n = ++id;
        pending.set(n, { resolve, reject });
        ws.send(JSON.stringify({ id: n, method, params }));
      }),
    events,
    close: () => ws.close(),
  };
}

const LIFT = `
  .bar, .calls { display: none !important; }
  .stage { padding: 0 !important; }
  .kitcol { height: auto !important; margin: 0 !important; border: 0 !important; }
  .kitcol .kit-root { height: auto !important; overflow: visible !important; }
  .kitcol .kit-scroll { overflow: visible !important; }
`;

try {
  const c = cdp(await target());
  await c.ready;
  await c.send("Page.enable");
  await c.send("Runtime.enable");
  mkdirSync(OUT, { recursive: true });
  const shots = [];
  for (const w of [280, 340, 480]) {
    await c.send("Emulation.setDeviceMetricsOverride", { width: w + 40, height: 900, deviceScaleFactor: 1, mobile: false });
    await c.send("Page.navigate", { url: `${BASE}?scenario=kit&w=${w}` });
    await sleep(1500);
    const evalJs = async (expr) => (await c.send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;
    await evalJs(`(async () => { const s = document.createElement("style"); s.textContent = ${JSON.stringify(LIFT)}; document.head.appendChild(s); await document.fonts.ready; return true; })()`);
    for (const lang of ["en", "ar"]) {
      const other = lang === "en" ? "kit-ar" : "kit-en";
      const rect = await evalJs(`(async () => {
        document.getElementById("kit-en").style.display = "";
        document.getElementById("kit-ar").style.display = "";
        document.getElementById(${JSON.stringify(other)}).style.display = "none";
        await document.fonts.ready;
        const r = document.getElementById(${JSON.stringify(`kit-${lang}`)}).getBoundingClientRect();
        return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height,
                 fonts: [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family + " " + f.weight) };
      })()`);
      const { data } = await c.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true, clip: { x: rect.x, y: rect.y, width: rect.width, height: rect.height, scale: 1 } });
      const file = join(OUT, `kit-${lang}-${w}.png`);
      writeFileSync(file, Buffer.from(data, "base64"));
      shots.push({ file, width: Math.round(rect.width), height: Math.round(rect.height), fonts_loaded: rect.fonts });
    }
  }
  c.close();
  for (const s of shots) console.log(`${s.file}  ${s.width}x${s.height}  fonts: ${[...new Set(s.fonts_loaded)].join(", ")}`);
} finally {
  browser.kill();
  await sleep(500);
  try {
    rmSync(profile, { recursive: true, force: true });
  } catch {
    // the browser may still hold the profile for a moment
  }
}
