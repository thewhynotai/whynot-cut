// WhyNot Cut Spike - panel entry. "Run spike" runs every probe (probes.ts), writes
// ~/.whynot-cut/uxp-spike/results-<ts>.json after each probe (so a hang keeps the partial results), and shows them.
// 0.1.5: the panel also watches ~/.whynot-cut/uxp-spike/run-request.json (autorun.ts) and runs the spike by itself.
import type { premierepro as Ppro } from "@adobe/premierepro";
import { createAutoRunner, type RunMode, type RunSummary } from "./autorun.ts";
import { ensureDir, writeText } from "./fsutil.ts";
import { resolveHome, spikeDir } from "./home.ts";
import { buildProbes, errText, loadConfig, skipSaveCloseOpen, type Ctx } from "./probes.ts";
import { jsonSafe, runAll, type OpResult } from "./runner.ts";
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
  for (const id of ["run", "run-keep"]) ($(id) as HTMLButtonElement).disabled = on;
}

function hostModules() {
  const uxp = (tryRequire<UxpModule>("uxp") ?? {}) as UxpModule;
  const fs = (tryRequire<UxpFs>("fs") ?? {}) as UxpFs;
  const os = tryRequire<UxpOs>("os");
  const proc = tryRequire<{ env?: Record<string, string | undefined> }>("process") ?? (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
  const { home, via } = resolveHome({ ...(os?.homedir ? { osHomedir: () => os.homedir?.() ?? "" } : {}), env: proc?.env ?? {} });
  return { uxp, fs, os, home, via };
}

/** One run: the buttons call it with no autoId, the auto-runner with the request's id. Never throws. */
async function runSpike(keepOpen: boolean, autoId?: string): Promise<RunSummary> {
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
  try {
    const ppro = require("premierepro") as Ppro;
    const { uxp, fs, os, home, via } = hostModules();
    if (!home) throw new Error("cannot resolve the home folder (os.homedir() and USERPROFILE/HOME all unavailable)");
    const dir = spikeDir(home);
    await ensureDir(fs, dir);
    const { config, error } = await loadConfig(fs, dir);
    const ts = stamp();
    const ctx: Ctx = { ppro, fs, uxp, os, home, homeVia: via, stamp: ts, config, configError: error, expect: {}, notes: [] };
    const probes = buildProbes({ keepOpen });
    say(config ? `Running ${probes.length} probes (config: ${dir}/config.json)` : `Running without config - ${error}`);
    let premiere = "unknown";
    try {
      // Application.version resolves empty on 26.5.2; uxp.host.version is the reliable source
      premiere = uxp.host?.version || (await ppro.Application.version) || "unknown";
    } catch {
      premiere = uxp.host?.version || "unknown";
    }
    const resultsPath = `${dir}/results-${ts}.json`;
    const doc = (ops: OpResult[]) => ({
      spike: SPIKE_VERSION,
      premiere,
      uxp: uxp.versions?.uxp ?? null,
      at: new Date().toISOString(),
      home,
      home_via: via,
      results_file: resultsPath,
      config: config ?? null,
      config_error: error,
      kept_project_open: keepOpen,
      notes: ctx.notes,
      ...(autoId ? { auto_run_id: autoId } : {}),
      ops,
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
    const ops = await runAll(probes, ctx, (_done, all) => write(all));
    await write(ops);
    const pass = ops.filter((o) => o.ok === true).length;
    const fail = ops.filter((o) => o.ok === false).length;
    counts = { pass, fail, na: ops.length - pass - fail };
    const text = `${pass} pass, ${fail} fail, ${counts.na} n/a`;
    resultsFile = resultsPath;
    if (writeError) problem = `COULD NOT WRITE ${resultsPath}: ${writeError}`;
    say(writeError ? `Done: ${text}. ${problem} - use Copy results or select the text below.` : `Done: ${text}. Results: ${resultsPath}`);
  } catch (e) {
    problem = `Spike could not start: ${errText(e)}`;
    say(problem);
  } finally {
    if (owns) setRunning(false);
  }
  return { results_file: resultsFile, ok: problem === null, ...counts, ...(problem === null ? {} : { error: problem }) };
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
      run: (mode: RunMode, id: string) => runSpike(mode === "keep_open", id),
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

function applyTheme(): void {
  try {
    const uxp = tryRequire<UxpModule>("uxp");
    const bg = uxp?.host?.getBackgroundColor?.();
    if (typeof bg === "string") document.documentElement.style.setProperty("--twn-bg", bg);
  } catch {
    // keep the stylesheet default
  }
}

function boot(): void {
  applyTheme();
  $("version").textContent = `v${SPIKE_VERSION}`;
  $("run").addEventListener("click", () => void runSpike(false));
  $("run-keep").addEventListener("click", () => void runSpike(true));
  $("copy").addEventListener("click", () => void copyResults());
  startAutoRun();
}

boot();
