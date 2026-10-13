// WhyNot Cut Spike - panel entry. "Run spike" runs every probe (probes.ts), writes
// ~/.whynot-cut/uxp-spike/results-<ts>.json after each probe (so a hang keeps the partial results), and shows them.
// 0.1.5: the panel also watches ~/.whynot-cut/uxp-spike/run-request.json (autorun.ts) and runs the spike by itself.
// 0.1.6: a "Style guide" view (style-guide.ts; run-request mode "style_guide" opens it and leaves it open), live UXP UI
// measurements (ui-probes.ts -> `ui_probes`) and the C2.7 ecosystem probes (eco-probes.ts -> `eco_probes`).
// 0.1.7: a "CSS lab" view (css-lab.ts; run-request mode "css_lab" opens it, leaves it open and writes `lab`).
// 0.1.9: a style_guide request's "scroll" scrolls the guide to that offset at the end of the run; the done file records
// where its scroll region stands (`scroll`: scrollTop, scrollHeight, clientHeight).
import type { premierepro as Ppro } from "@adobe/premierepro";
import { createAutoRunner, type GuideScroll, type GuideView, type RunMode, type RunSummary } from "./autorun.ts";
import { createLabView, runCssLab, type LabResults, type LabView } from "./css-lab.ts";
import { realLabDom, realLabEnv } from "./lab-dom.ts";
import { createLifecycle, lifecycleWriter, setupLifecycle, type EcoCtx, type LifecycleEvent, type LifecycleSetup } from "./eco-probes.ts";
import { ensureDir, writeText } from "./fsutil.ts";
import { resolveHome, spikeDir } from "./home.ts";
import { buildProbes, errText, loadConfig, skipSaveCloseOpen, type Ctx } from "./probes.ts";
import { jsonSafe, runAll, type OpResult } from "./runner.ts";
import { runPostSections, runPreSections, sectionCounts, type ResultsDoc, type Sections } from "./sections.ts";
import { createStyleGuide, type StyleGuide } from "./style-guide.ts";
import { domStage, type UiCtx } from "./ui-probes.ts";
import { SPIKE_VERSION } from "./version.ts";
import type { UxpFs, UxpModule, UxpOs } from "../../src/uxp-types.ts";

declare const require: (id: string) => unknown;

function $(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`panel is missing #${id}`);
  return el;
}

function stamp(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function tryRequire<T>(id: string): T | undefined {
  try {
    return require(id) as T;
  } catch {
    return undefined;
  }
}

function badge(ok: boolean | null): string {
  return ok === true ? "PASS" : ok === false ? "FAIL" : "N/A";
}

function renderOps(ops: OpResult[], planned: number): void {
  const list = $("ops");
  list.textContent = "";
  for (const o of ops) {
    const row = document.createElement("div");
    row.className = `op ${o.ok === true ? "pass" : o.ok === false ? "fail" : "na"}`;
    const head = document.createElement("div");
    head.className = "op-head";
    head.textContent = `${badge(o.ok)}  ${o.op}  (${o.ms} ms)`;
    row.appendChild(head);
    if (o.error) {
      const err = document.createElement("div");
      err.className = "op-err";
      err.textContent = o.error;
      row.appendChild(err);
    }
    list.appendChild(row);
  }
  $("progress").textContent = `${ops.length} / ${planned} probes`;
}

let lastJson = "";

async function copyResults(): Promise<void> {
  const status = $("status");
  if (!lastJson) {
    status.textContent = "Nothing to copy yet - run the spike first.";
    return;
  }
  const failures: string[] = [];
  // 1. async clipboard API (needs the manifest's clipboard permission; the getter itself throws without it)
  try {
    const nav = (globalThis as { navigator?: { clipboard?: { writeText?: (t: string) => Promise<void> } } }).navigator;
    const clip = nav?.clipboard;
    if (typeof clip?.writeText !== "function") throw new Error("navigator.clipboard.writeText is not available");
    await clip.writeText(lastJson);
    status.textContent = "Results copied to the clipboard.";
    return;
  } catch (e) {
    failures.push(`clipboard API: ${errText(e)}`);
  }
  // 2. fall back to selecting the textarea and execCommand("copy")
  try {
    const area = $("out") as HTMLTextAreaElement;
    area.focus();
    area.select();
    const ok = (document as unknown as { execCommand?: (c: string) => boolean }).execCommand?.("copy");
    if (!ok) throw new Error("execCommand copy returned false");
    status.textContent = "Results copied to the clipboard.";
    return;
  } catch (e) {
    failures.push(`execCommand: ${errText(e)}`);
  }
  status.textContent = `Copy failed (${failures.join("; ")}) - select the text below and copy it, or read the results file.`;
}

let running = false;

function setRunning(on: boolean): void {
  running = on;
  for (const id of ["run", "run-keep", "guide-open", "lab-open"]) ($(id) as HTMLButtonElement).disabled = on;
}

function hostModules() {
  const uxp = (tryRequire<UxpModule>("uxp") ?? {}) as UxpModule;
  const fs = (tryRequire<UxpFs>("fs") ?? {}) as UxpFs;
  const os = tryRequire<UxpOs>("os");
  const proc = tryRequire<{ env?: Record<string, string | undefined> }>("process") ?? (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
  const { home, via } = resolveHome({ ...(os?.homedir ? { osHomedir: () => os.homedir?.() ?? "" } : {}), env: proc?.env ?? {} });
  return { uxp, fs, os, home, via };
}

/** The manifest's one panel: the lifecycle (hide / show) recorder is registered once, at load (eco-probes.ts). */
const PANEL_ID = "whynotCutSpike";
let lifecycle = createLifecycle(() => Date.now());
let lifecycleSetup: LifecycleSetup | undefined;
let guide: StyleGuide | undefined;
let lab: LabView | undefined;

function ecoCtx(uxp: UxpModule, ppro: unknown, fs: UxpFs, home: string | null): EcoCtx {
  const g = globalThis as { WebSocket?: EcoCtx["WebSocket"]; fetch?: (url: string, init?: unknown) => Promise<{ status: number; statusText?: string }> };
  const f = g.fetch;
  return {
    uxp,
    ppro,
    fs,
    home,
    ...(g.WebSocket ? { WebSocket: g.WebSocket } : {}),
    ...(typeof f === "function" ? { fetch: (url: string, init?: unknown) => f.call(globalThis, url, init) } : {}),
    now: () => Date.now(),
    lifecycle,
    ...(lifecycleSetup ? { lifecycleSetup } : {}),
  };
}

function uiCtx(): UiCtx {
  return { stage: domStage(document, (el) => getComputedStyle(el), document.body) };
}

/**
 * One run: the buttons call it with no autoId, the auto-runner with the request's id. Never throws.
 *   full        - ui_probes + eco_probes (names, loopback, hide/show), every Premiere probe, then openExternal last
 *   keep_open   - the same without save/close/open and without openExternal: the scratch project stays open
 *   style_guide - opens the style guide (it stays open), ui_probes + eco_probes (no openExternal), no Premiere probe
 *   css_lab     - opens the CSS lab (it stays open), measures it into `lab`, then ui_probes; no eco / Premiere probe
 */
async function runSpike(mode: RunMode, autoId?: string, view?: GuideView): Promise<RunSummary> {
  const keepOpen = mode === "keep_open";
  const status = $("status");
  const say = (text: string) => void (status.textContent = autoId ? `Auto-run ${autoId} - ${text}` : text);
  // an auto-run already holds the lock (taken before its claim, see startAutoRun); a button press takes it here
  const owns = autoId === undefined;
  if (owns) {
    if (running) {
      say("Another run is in progress - wait for it to finish.");
      return { results_file: null, ok: false, pass: 0, fail: 0, na: 0, error: "another run is already in progress" };
    }
    setRunning(true);
  }
  skipSaveCloseOpen.value = keepOpen;
  let resultsFile: string | null = null;
  let counts = { pass: 0, fail: 0, na: 0 };
  let problem: string | null = null;
  let guideScroll: GuideScroll | undefined;
  try {
    // a literal require, so the bundle keeps it external (test/package.test.ts); the style guide works without it
    let ppro: Ppro | undefined;
    try {
      ppro = require("premierepro") as Ppro;
    } catch (e) {
      if (mode !== "style_guide" && mode !== "css_lab") throw e;
    }
    const { uxp, fs, os, home, via } = hostModules();
    if (!home) throw new Error("cannot resolve the home folder (os.homedir() and USERPROFILE/HOME all unavailable)");
    const dir = spikeDir(home);
    await ensureDir(fs, dir);
    const { config, error } = await loadConfig(fs, dir);
    const ts = stamp();
    const ctx: Ctx = { ppro: ppro as Ppro, fs, uxp, os, home, homeVia: via, stamp: ts, config, configError: error, expect: {}, notes: [] };
    const noPremiere = mode === "style_guide" || mode === "css_lab";
    const probes = noPremiere ? [] : buildProbes({ keepOpen });
    const sections: Sections = { ui_probes: {}, eco_probes: {} };
    if (mode === "style_guide") {
      lab?.hide(false);
      guide?.show(view ?? {});
    }
    if (mode === "css_lab") {
      guide?.hide();
      lab?.show();
    }
    let labResults: LabResults | null = null;
    let labError: string | null = null;
    say(mode === "style_guide" ? "Style guide open - measuring" : mode === "css_lab" ? "CSS lab open - measuring" : config ? `Running ${probes.length} probes (config: ${dir}/config.json)` : `Running without config - ${error}`);
    let premiere = "unknown";
    try {
      // Application.version resolves empty on 26.5.2; uxp.host.version is the reliable source
      premiere = uxp.host?.version || (await ppro?.Application.version) || "unknown";
    } catch {
      premiere = uxp.host?.version || "unknown";
    }
    const resultsPath = `${dir}/results-${ts}.json`;
    const doc = (ops: OpResult[]): ResultsDoc => ({
      spike: SPIKE_VERSION,
      premiere,
      uxp: uxp.versions?.uxp ?? null,
      at: new Date().toISOString(),
      home,
      home_via: via,
      results_file: resultsPath,
      config: config ?? null,
      config_error: error,
      mode,
      kept_project_open: keepOpen,
      notes: ctx.notes,
      ...(autoId ? { auto_run_id: autoId } : {}),
      ...(guide?.isOpen() ? { style_guide_view: guide.view() } : {}),
      ops,
      ...(mode === "css_lab" ? { lab: labResults, ...(labError ? { lab_error: labError } : {}) } : {}),
      ui_probes: sections.ui_probes,
      eco_probes: sections.eco_probes,
    });
    let writeError: string | null = null;
    const write = async (ops: OpResult[]) => {
      lastJson = JSON.stringify(jsonSafe(doc(ops)), null, 2);
      ($("out") as HTMLTextAreaElement).value = lastJson;
      renderOps(ops, probes.length);
      try {
        await writeText(fs, resultsPath, lastJson);
        writeError = null;
      } catch (e) {
        writeError = errText(e);
      }
    };
    renderOps([], probes.length);
    // 0. css_lab: measure the lab while it is the only view on screen (it stays open for the screenshots)
    if (mode === "css_lab") {
      try {
        labResults = await runCssLab(realLabDom($("lab-host")), realLabEnv(document, fs, uxp));
        lab?.caption(labResults.host_width_px);
      } catch (e) {
        labError = errText(e);
      }
      await write([]);
    }
    // 1. the UI measurements (a visible kit stage, removed after each probe) and the quick ecosystem probes
    const eco = ecoCtx(uxp, ppro, fs, home);
    await runPreSections(
      sections,
      uiCtx(),
      eco,
      async (label) => {
        say(label);
        await write([]);
      },
      { eco: mode !== "css_lab" },
    );
    // 2. the Premiere probes (none in style_guide mode)
    let ops: OpResult[] = [];
    if (probes.length) {
      ops = await runAll(probes, ctx, (_done, all) => write(all));
      await write(ops);
    }
    // 3. openExternal last, in "full" only; then the lifecycle events up to now
    await runPostSections(mode, sections, ecoCtx(uxp, ppro, fs, home), (label) => say(label));
    await write(ops);
    if (mode === "style_guide") {
      counts = sectionCounts(sections);
      // 0.1.9: last, so the probes' stages are gone and the screenshot that follows the done file sees this offset
      guideScroll = guide?.scrollTo(view?.scroll);
    } else if (mode === "css_lab") {
      const c = sectionCounts(sections);
      const l = labResults?.summary ?? { pass: 0, fail: 0, na: 0 };
      counts = { pass: c.pass + l.pass, fail: c.fail + l.fail, na: c.na + l.na };
    } else {
      const pass = ops.filter((o) => o.ok === true).length;
      const fail = ops.filter((o) => o.ok === false).length;
      counts = { pass, fail, na: ops.length - pass - fail };
    }
    const text = `${counts.pass} pass, ${counts.fail} fail, ${counts.na} n/a${mode === "style_guide" ? " (ui + eco probes)" : mode === "css_lab" ? ` (lab + ui probes${labError ? `; lab failed: ${labError}` : ""})` : ""}`;
    resultsFile = resultsPath;
    if (writeError) problem = `COULD NOT WRITE ${resultsPath}: ${writeError}`;
    say(writeError ? `Done: ${text}. ${problem} - use Copy results or select the text below.` : `Done: ${text}. Results: ${resultsPath}`);
  } catch (e) {
    problem = `Spike could not start: ${errText(e)}`;
    say(problem);
  } finally {
    if (owns) setRunning(false);
  }
  return { results_file: resultsFile, ok: problem === null, ...counts, ...(problem === null ? {} : { error: problem }), ...(guideScroll ? { scroll: guideScroll } : {}) };
}

/** 0.1.5: poll ~/.whynot-cut/uxp-spike/run-request.json (on load, then every 5 s) and run what it asks for. */
function startAutoRun(): void {
  const status = $("status");
  try {
    const { fs, home } = hostModules();
    if (!home) throw new Error("cannot resolve the home folder");
    const dir = spikeDir(home);
    const runner = createAutoRunner({
      fs,
      dir,
      now: () => Date.now(),
      isBusy: () => running,
      tryLock: () => {
        if (running) return false;
        setRunning(true);
        return true;
      },
      unlock: () => setRunning(false),
      run: (mode: RunMode, id: string, view?: GuideView) => runSpike(mode, id, view),
      setStatus: (text) => void (status.textContent = text),
      schedule: (fn, ms) => {
        const handle = setTimeout(fn, ms);
        return () => clearTimeout(handle);
      },
    });
    status.textContent = `Ready. Watching ${dir}/run-request.json every 5 s.`;
    void runner.start();
  } catch (e) {
    status.textContent = `Ready. Auto-run is off: ${errText(e)}`;
  }
}

/** 0.1.6: panel create / show / hide / destroy + visibilitychange, recorded from load on (and into lifecycle.json). */
function startLifecycle(): void {
  try {
    const { uxp, fs, home } = hostModules();
    const persist = home ? lifecycleWriter(fs, spikeDir(home)) : undefined;
    lifecycle = createLifecycle(() => Date.now(), persist ? (events: LifecycleEvent[]) => persist(events) : undefined);
    lifecycleSetup = setupLifecycle(uxp, PANEL_ID, lifecycle, document);
  } catch (e) {
    lifecycleSetup = { entrypoints_setup: "threw", error: errText(e), panel_id: PANEL_ID, listeners: [] };
  }
}

function startGuide(): void {
  guide = createStyleGuide({
    main: $("main-view"),
    guide: $("guide-view"),
    frame: $("guide-frame"),
    host: $("guide-host"),
    caption: $("guide-caption"),
    buttons: {
      lang: { en: $("guide-en"), ar: $("guide-ar") },
      width: { 280: $("guide-w280"), 340: $("guide-w340"), 480: $("guide-w480") },
      back: $("guide-back"),
    },
  });
  $("guide-open").addEventListener("click", () => void guide?.show());
}

function startLab(): void {
  lab = createLabView({ main: $("main-view"), guide: $("guide-view"), lab: $("lab-view"), host: $("lab-host"), caption: $("lab-caption"), back: $("lab-back") });
  // the button opens the lab and measures it, exactly like a css_lab run-request
  $("lab-open").addEventListener("click", () => void runSpike("css_lab"));
}

function boot(): void {
  // the lifecycle first: entrypoints.setup has to run while the plugin loads
  startLifecycle();
  $("version").textContent = `v${SPIKE_VERSION}`;
  $("run").addEventListener("click", () => void runSpike("full"));
  $("run-keep").addEventListener("click", () => void runSpike("keep_open"));
  $("copy").addEventListener("click", () => void copyResults());
  startGuide();
  startLab();
  startAutoRun();
}

boot();
