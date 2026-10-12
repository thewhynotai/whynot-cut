// Dev harness: mounts the panel with MockSource in a browser. Query string: ?lang=ar&w=340&scenario=qc&offline=1
import { asMountRoot, mount } from "../src/mount.ts";
import type { PanelHost } from "../src/host.ts";
import { MockSource, SCENARIOS } from "../src/mock.ts";
import type { Scenario } from "../src/mock.ts";
import type { Language } from "../src/source.ts";

const q = new URLSearchParams(location.search);
const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;

let lang: Language = q.get("lang") === "ar" ? "ar" : "en";
let width = [280, 340, 480].includes(Number(q.get("w"))) ? Number(q.get("w")) : 340;
let height = [470, 640, 900].includes(Number(q.get("h"))) ? Number(q.get("h")) : 640;
const scenarioParam = q.get("scenario") as Scenario | null;
const scenario: Scenario = scenarioParam && SCENARIOS.includes(scenarioParam) ? scenarioParam : "showcase";

const source = new MockSource({ language: lang, scenario });

const calls = $("calls");
const log = (text: string) => {
  calls.textContent = `${new Date().toLocaleTimeString()}  ${text}\n${calls.textContent === "Host adapter calls appear here." ? "" : calls.textContent}`.split("\n").slice(0, 8).join("\n");
  calls.style.whiteSpace = "pre-wrap";
};
const host: PanelHost = {
  setPlayerPosition: (t) => log(`setPlayerPosition(${t})`),
  openInSourceMonitor: (p) => log(`openInSourceMonitor(${p})`),
  revealPath: (p) => log(`revealPath(${p})`),
  copyText: (t) => {
    log(`copyText(${t.length} chars)`);
    try {
      void navigator.clipboard?.writeText(t);
    } catch {
      /* the dev page may not be allowed to use the clipboard */
    }
  },
};

mount(asMountRoot($("root")), source, host);

function pressed(group: string, value: string): void {
  for (const b of Array.from($(group).querySelectorAll("button"))) b.setAttribute("aria-pressed", String(b.getAttribute("data-v") === value));
}
function applyWidth(): void {
  $("col").style.width = `${width}px`;
  pressed("width", String(width));
}
function applyHeight(): void {
  $("col").style.height = `${height}px`;
  pressed("height", String(height));
}
function applyLang(): void {
  pressed("lang", lang);
  document.documentElement.lang = lang;
}

$("lang").addEventListener("click", (e) => {
  const v = (e.target as HTMLElement).getAttribute("data-v");
  if (v === "en" || v === "ar") {
    lang = v;
    source.setLanguage(lang);
    applyLang();
  }
});
$("height").addEventListener("click", (e) => {
  const v = Number((e.target as HTMLElement).getAttribute("data-v"));
  if (v) {
    height = v;
    applyHeight();
  }
});
$("width").addEventListener("click", (e) => {
  const v = Number((e.target as HTMLElement).getAttribute("data-v"));
  if (v) {
    width = v;
    applyWidth();
  }
});
const sel = $<HTMLSelectElement>("scenario");
sel.value = scenario;
sel.addEventListener("change", () => source.setScenario(sel.value as Scenario));
$<HTMLInputElement>("offline").checked = q.get("offline") === "1";
$("offline").addEventListener("change", (e) => source.setEngine((e.target as HTMLInputElement).checked ? "offline" : "connected"));
if (q.get("offline") === "1") source.setEngine("offline");

let timer: ReturnType<typeof setInterval> | null = null;
$("progress").addEventListener("change", (e) => {
  if (timer) clearInterval(timer);
  timer = (e.target as HTMLInputElement).checked ? setInterval(() => source.advance(), 1500) : null;
});

applyLang();
applyWidth();
applyHeight();
